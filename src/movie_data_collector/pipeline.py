from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import pandas as pd
from playwright.async_api import async_playwright

from .config import (
    BOV_PROGRESS,
    DATA_DIR,
    DTP_PROGRESS,
    LOG_CSV,
    MOVIES_CSV,
    STATE_DIR,
    UNMATCHED_CSV,
)
from .matching import choose_best_match, score_pair
from .scrape_boxofficevietnam import fetch_movie_detail as fetch_bov_detail
from .scrape_boxofficevietnam import search_movie as search_bov_movie
from .scrape_doanhthuphim import collect_movie_list, fetch_movie_detail as fetch_dtp_detail
from .scrape_doanhthuphim import load_progress_urls
from .utils import append_jsonl, clean_text, polite_delay, read_jsonl, split_titles, write_jsonl


OUTPUT_COLUMNS = [
    "movie_name",
    "title_bovn",
    "original_title",
    "release_year",
    "genre",
    "director",
    "revenue_doanhthuphim",
    "revenue_bovn",
    "tickets_sold",
    "screening_count",
    "source_url_doanhthuphim",
    "source_url_bovn",
    "match_status",
    "collection_status",
]


def _query_variants(rec: dict[str, Any]) -> list[str]:
    """Generate polite search variants to handle subtitles/English titles."""
    names: list[str] = []
    for v in [rec.get("movie_name"), rec.get("original_title")]:
        if isinstance(v, str) and v.strip():
            names.append(v.strip())

    variants: list[str] = []

    def add(v: str | None) -> None:
        if not v:
            return
        v = re.sub(r"\s+", " ", v).strip(" -–—:·|")
        if not v:
            return
        key = v.lower()
        if key not in {x.lower() for x in variants}:
            variants.append(v)

    digit_words = {
        "0": "không",
        "1": "một",
        "2": "hai",
        "3": "ba",
        "4": "bốn",
        "5": "năm",
        "6": "sáu",
        "7": "bảy",
        "8": "tám",
        "9": "chín",
    }

    for name in names:
        add(name)
        # "Heo 5 Móng" vs "Heo Năm Móng"
        if re.search(r"\b[0-9]\b", name):
            add(re.sub(r"\b([0-9])\b", lambda m: digit_words.get(m.group(1), m.group(1)), name))
        # main title before a subtitle/colon (helps "Avengers: Hồi Kết (Endgame)")
        if ":" in name:
            add(name.split(":", 1)[0])
        # alternate titles in parentheses / after separators
        a, b = split_titles(name)
        add(a)
        add(b)
        # without parenthetical content
        add(re.sub(r"\([^)]*\)", "", name))
    return variants[:6]


async def _search_candidates(page, rec: dict[str, Any]) -> list[dict[str, Any]]:
    """Search BOV with the main title first, then fall back to variants."""
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in _query_variants(rec):
        candidates = await search_bov_movie(page, query)
        for c in candidates:
            href = c.get("href")
            if href and href not in seen:
                seen.add(href)
                collected.append(c)
        if any(score_pair(rec, c) >= 90 for c in collected):
            break
    return collected


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _dtp_to_base_record(list_item: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    name = detail.get("detail_title") or list_item.get("movie_name")
    orig = detail.get("original_title")
    if not orig:
        a, b = split_titles(name)
        # keep original_name from site; store alternate in original_title if clearly different
        if b and b != a:
            orig = b
    rec = {
        "movie_name": clean_text(name),
        "original_title": clean_text(orig),
        "release_year": clean_text(detail.get("release_year") or list_item.get("release_date_text")),
        "genre": clean_text(detail.get("genre")),
        "director": clean_text(detail.get("director")),
        "revenue_doanhthuphim": clean_text(detail.get("revenue_doanhthuphim_detail") or list_item.get("revenue_doanhthuphim")),
        "revenue_bovn": None,
        "tickets_sold": None,
        "screening_count": None,
        "source_url_doanhthuphim": clean_text(list_item.get("source_url_doanhthuphim")),
        "source_url_bovn": None,
        "match_status": "pending",
        "collection_status": "dtp_collected",
    }
    return rec


async def collect_doanhthuphim(limit: int | None = None, resume: bool = True) -> list[dict[str, Any]]:
    _ensure_dirs()
    processed = load_progress_urls() if resume else set()
    out: list[dict[str, Any]] = read_jsonl(DTP_PROGRESS) if resume else []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        items = await collect_movie_list(page)
        if limit is not None:
            items = items[:limit]
        total = len(items)
        for idx, item in enumerate(items, start=1):
            url = item.get("source_url_doanhthuphim")
            if resume and url and url in processed:
                continue
            print(f"[dtp {idx}/{total}] {item.get('movie_name_guess') or url}")
            try:
                detail = await fetch_dtp_detail(page, url)
                rec = _dtp_to_base_record(item, detail)
            except Exception as exc:  # noqa: BLE001
                detail = {}
                rec = _dtp_to_base_record(item, detail)
                rec["collection_status"] = f"dtp_detail_error:{exc.__class__.__name__}"
            rec["_dtp_raw"] = {k: v for k, v in item.items() if k != "raw" or isinstance(v, (str, int, float, list, dict, type(None)))}
            rec["_dtp_detail_raw"] = (detail or {}).get("raw_fields")
            append_jsonl(DTP_PROGRESS, rec)
            out.append(rec)
            await polite_delay()
        await browser.close()
    return out


def load_bov_progress() -> dict[str, dict[str, Any]]:
    out = {}
    for r in read_jsonl(BOV_PROGRESS):
        key = r.get("source_url_doanhthuphim") or r.get("movie_name")
        if key:
            out[str(key)] = r
    return out


async def match_and_enrich(dtp_records: list[dict[str, Any]], limit: int | None = None, resume: bool = True) -> list[dict[str, Any]]:
    _ensure_dirs()
    progress = load_bov_progress() if resume else {}
    results: list[dict[str, Any]] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        count = 0
        total = len(dtp_records)
        for idx, rec in enumerate(dtp_records, start=1):
            key = rec.get("source_url_doanhthuphim") or rec.get("movie_name")
            if limit is not None and count >= limit:
                break
            if resume and key and key in progress:
                results.append(progress[key])
                count += 1
                continue
            merged = dict(rec)
            query = rec.get("movie_name") or ""
            print(f"[bov {idx}/{total}] {query}")
            try:
                candidates = await _search_candidates(page, rec)
                match = choose_best_match(rec, candidates)
            except Exception as exc:  # noqa: BLE001
                candidates = []
                from .matching import MatchResult
                match = MatchResult("not_found", 0.0, None, f"search_error:{exc.__class__.__name__}")
                merged["collection_status"] = f"bov_search_error:{exc.__class__.__name__}"
            merged["match_score"] = round(match.score, 2)
            merged["match_reason"] = match.reason
            if match.status in {"matched", "needs_review"} and match.candidate:
                bov_url = match.candidate.get("href")
                merged["source_url_bovn"] = bov_url
                try:
                    bov_detail = await fetch_bov_detail(page, bov_url) if bov_url else {}
                except Exception as e:  # noqa: BLE001
                    bov_detail = {}
                    merged["collection_status"] = f"bov_detail_error:{e.__class__.__name__}"
                merged["revenue_bovn"] = clean_text(bov_detail.get("revenue_bovn")) or merged.get("revenue_bovn")
                merged["tickets_sold"] = clean_text(bov_detail.get("tickets_sold"))
                merged["screening_count"] = clean_text(bov_detail.get("screening_count"))
                merged["bov_title"] = clean_text(bov_detail.get("bov_title"))
                merged["title_bovn"] = clean_text(match.candidate.get("title")) or clean_text(bov_detail.get("bov_title"))
                merged["bov_release_info"] = clean_text(bov_detail.get("release_info"))
                # preserve original names from both sites
                if not merged.get("original_title") and merged.get("bov_title"):
                    # keep BOV title as reference if DTP didn't provide explicit original title
                    merged["original_title_from_bovn"] = merged.get("bov_title")
                merged["match_status"] = match.status
                if "collection_status" not in merged or merged["collection_status"] == "dtp_collected":
                    merged["collection_status"] = "matched" if match.status == "matched" else "needs_review"
                merged["_bov_candidate"] = match.candidate
                merged["_bov_detail_raw"] = bov_detail.get("raw_fields")
            else:
                merged["match_status"] = "not_found"
                if not str(merged.get("collection_status") or "").startswith("bov_"):
                    merged["collection_status"] = "not_found"
                merged["source_url_bovn"] = None
            append_jsonl(BOV_PROGRESS, merged)
            results.append(merged)
            count += 1
            await polite_delay()
        await browser.close()
    return results


def _record_key(rec: dict[str, Any]) -> str:
    return str(rec.get("source_url_doanhthuphim") or rec.get("movie_name") or "")


async def rematch_unmatched() -> list[dict[str, Any]]:
    """Retry matching for records currently marked not_found/needs_review."""
    _ensure_dirs()
    dtp_records = read_jsonl(DTP_PROGRESS)
    progress = load_bov_progress()
    targets: list[dict[str, Any]] = []
    for rec in dtp_records:
        merged = progress.get(_record_key(rec), rec)
        if merged.get("match_status") in {"not_found", "needs_review"}:
            targets.append(rec)
    if not targets:
        print("[rematch] nothing to retry")
        return [progress.get(_record_key(r), r) for r in dtp_records]

    print(f"[rematch] retrying {len(targets)} records")
    new_results = await match_and_enrich(targets, resume=False)
    for rec in new_results:
        progress[_record_key(rec)] = rec
    ordered = [progress.get(_record_key(r), r) for r in dtp_records]
    write_jsonl(BOV_PROGRESS, ordered)
    write_outputs(ordered)
    return ordered


def _bovn_title(rec: dict[str, Any]) -> str | None:
    cand = rec.get("_bov_candidate") or {}
    t = cand.get("title") or rec.get("title_bovn") or rec.get("bov_title")
    if not t:
        return None
    t = re.sub(r"^Doanh số phòng vé phim\s+", "", str(t))
    t = re.sub(r"\s*-\s*Box Office Vietnam\s*$", "", t)
    return clean_text(t)


def write_outputs(records: list[dict[str, Any]]) -> None:
    _ensure_dirs()
    # normalize to columns
    rows = []
    log_rows = []
    for r in records:
        row = {c: r.get(c) for c in OUTPUT_COLUMNS}
        row["title_bovn"] = _bovn_title(r)
        rows.append(row)
        log_rows.append({
            "movie_name": r.get("movie_name"),
            "title_bovn": _bovn_title(r),
            "source_url_doanhthuphim": r.get("source_url_doanhthuphim"),
            "source_url_bovn": r.get("source_url_bovn"),
            "match_status": r.get("match_status"),
            "collection_status": r.get("collection_status"),
            "match_score": r.get("match_score"),
            "match_reason": r.get("match_reason"),
        })
    df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    df.to_csv(MOVIES_CSV, index=False, encoding="utf-8-sig")
    unmatched = df[df["match_status"].isin(["not_found", "needs_review"]) | df["source_url_bovn"].isna()]
    unmatched.to_csv(UNMATCHED_CSV, index=False, encoding="utf-8-sig")
    pd.DataFrame(log_rows).to_csv(LOG_CSV, index=False, encoding="utf-8-sig")


async def run_full(resume: bool = True, limit: int | None = None) -> list[dict[str, Any]]:
    dtp = await collect_doanhthuphim(limit=limit, resume=resume)
    merged = await match_and_enrich(dtp, limit=limit, resume=resume)
    write_outputs(merged)
    return merged
