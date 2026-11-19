from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
from playwright.async_api import Page

from .config import BOVN_DISCOVERED, DISCOVERED_CSV
from .scrape_boxofficevietnam import fetch_movie_detail, search_movie
from .utils import append_jsonl, clean_text, normalize_title, polite_delay, read_jsonl

DISCOVERED_COLUMNS = [
    "movie_name",
    "release_year",
    "release_date",
    "genre",
    "director",
    "revenue_bovn",
    "tickets_sold",
    "screening_count",
    "source_url_bovn",
    "discovery_query",
    "detail_status",
    "match_status",
    "collection_status",
]

_DATE_DMY = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_DATE_YMD = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")


def parse_release_date(text: str | None) -> tuple[str | None, str | None]:
    """Parse a release date from BoVN search context / title.

    Returns (release_date_iso, release_year). Both may be None when the
    text carries no date. Never invents a date: a bare year in a title
    only yields the year, not a full date.
    """
    if not text:
        return None, None
    m = _DATE_DMY.search(text)
    if m:
        day, month, year = m.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}", year
    m = _DATE_YMD.search(text)
    if m:
        year, month, day = m.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}", year
    m = _YEAR.search(text)
    if m:
        return None, m.group(1)
    return None, None


def load_seed_queries(path: str | Path) -> list[str]:
    queries: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        queries.append(line)
    return queries


def _is_502_detail(detail: dict[str, Any]) -> bool:
    title = (detail.get("bov_title") or "").lower()
    return "bad gateway" in title or "502" in title


_GENERIC_QUERY_WORDS = {"movie", "phim", "dien", "anh"}


def query_matches(query: str, title: str | None) -> bool:
    """Check a BoVN search hit really matches the query.

    BoVN search pages also list unrelated movies (latest / sidebar
    links), and search_movie returns every /movie/ link on the page,
    so without this filter a query like "Vô Hạn Thành" would also
    collect unrelated 2026 releases. A hit must contain every
    non-generic query token, or the whole normalized query.
    """
    if not title:
        return False
    q_norm = normalize_title(query)
    t_norm = normalize_title(title)
    if q_norm and q_norm in t_norm:
        return True
    q_tokens = [t for t in q_norm.split() if t not in _GENERIC_QUERY_WORDS]
    if not q_tokens:
        return False
    t_tokens = set(t_norm.split())
    return all(tok in t_tokens for tok in q_tokens)


async def discover_bovn(
    page: Page,
    queries: list[str],
    try_detail: bool = True,
    resume: bool = True,
) -> list[dict[str, Any]]:
    """Discover movies on Box Office Vietnam via its own search.

    This is a discovery source, not a match step: DoanhThuPhim only
    lists 92 films in total, so theatrical releases outside that list
    (notably anime) can only be found by searching BoVN directly.
    Revenue is only filled when the BoVN detail page actually loads;
    a 502 / error page leaves revenue empty and is recorded as such,
    never invented. Search-result context may carry a release date,
    which is parsed and stored with its source text.
    """
    seen: dict[str, dict[str, Any]] = {}
    if resume:
        for row in read_jsonl(BOVN_DISCOVERED):
            url = row.get("source_url_bovn")
            if url:
                seen[str(url)] = row
    out: list[dict[str, Any]] = list(seen.values())

    for query in queries:
        candidates = await search_movie(page, query)
        for cand in candidates:
            href = cand.get("href")
            if not href:
                continue
            if href in seen:
                continue
            title = clean_text(cand.get("title")) or ""
            if not query_matches(query, title):
                continue
            context = clean_text(cand.get("context")) or ""
            release_date, release_year = parse_release_date(context)
            if not release_year:
                _, release_year = parse_release_date(title)
            rec: dict[str, Any] = {
                "movie_name": title,
                "release_year": release_year,
                "release_date": release_date,
                "genre": None,
                "director": None,
                "revenue_bovn": None,
                "tickets_sold": None,
                "screening_count": None,
                "source_url_bovn": href,
                "discovery_query": query,
                "discovery_source": "boxofficevietnam_search",
                "bovn_search_context": context,
                "detail_status": None,
                "match_status": "bovn_discovered",
                "collection_status": "bovn_search_found",
            }
            if try_detail:
                try:
                    detail = await fetch_movie_detail(page, href)
                except Exception as exc:  # noqa: BLE001
                    detail = {}
                    rec["detail_status"] = f"bovn_detail_error:{exc.__class__.__name__}"
                    rec["collection_status"] = "bovn_detail_error_no_revenue"
                else:
                    if _is_502_detail(detail):
                        rec["detail_status"] = "bovn_detail_502"
                        rec["collection_status"] = "bovn_detail_502_no_revenue"
                    elif detail.get("revenue_bovn"):
                        rec["revenue_bovn"] = clean_text(detail.get("revenue_bovn"))
                        rec["tickets_sold"] = clean_text(detail.get("tickets_sold"))
                        rec["screening_count"] = clean_text(detail.get("screening_count"))
                        rec["detail_status"] = "bovn_detail_ok"
                        rec["collection_status"] = "bovn_detail_ok"
                        if not rec["release_date"] and detail.get("release_info"):
                            rd, ry = parse_release_date(detail.get("release_info"))
                            rec["release_date"] = rec["release_date"] or rd
                            rec["release_year"] = rec["release_year"] or ry
                    else:
                        rec["detail_status"] = "bovn_detail_no_revenue"
                        rec["collection_status"] = "bovn_detail_no_revenue"
                await polite_delay()
            seen[href] = rec
            out.append(rec)
            append_jsonl(BOVN_DISCOVERED, rec)
        await polite_delay()
    return out


def write_discovered_csv(records: list[dict[str, Any]], path: Path = DISCOVERED_CSV) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{c: r.get(c) for c in DISCOVERED_COLUMNS} for r in records]
    pd.DataFrame(rows, columns=DISCOVERED_COLUMNS).to_csv(
        path, index=False, encoding="utf-8-sig"
    )
    return path
