from __future__ import annotations

import argparse
import asyncio
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import pandas as pd

from .config import (
    MOVIES_CSV,
    REQUEST_DELAY_MAX,
    REQUEST_DELAY_MIN,
    RETRY_BACKOFF,
    RETRY_COUNT,
    TICKETS_WEB_CSV,
    WEB_TICKETS_PROGRESS,
)
from .utils import (
    append_jsonl,
    clean_text,
    ensure_parent,
    normalize_title,
    parse_money_vnd,
    polite_delay,
    read_jsonl,
    split_titles,
    with_retry,
    write_jsonl,
)

USER_AGENT = "movie-data-collector/1.0 (public RSS search; personal use)"

# News RSS endpoints only expose headlines/snippets. We keep the evidence text and
# URL so every extracted number can be verified manually.
RSS_ENDPOINTS = {
    "bing": "https://www.bing.com/news/search",
    "google": "https://news.google.com/rss/search",
}

NUMBER_RE = r"\d{1,3}(?:[.\u00a0\s]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
UNIT_RE = (
    r"(?:lượt\s+)?"
    r"(?:vé|khán\s+giả|khán\s*giả|người\s+xem|lượt\s+xem|lượt\s+khách|"
    r"admissions?|tickets?)"
)
TICKET_RE = re.compile(
    rf"(?P<num>{NUMBER_RE})\s*"
    rf"(?P<scale>triệu|million|nghìn|ngàn|nghin|k)?\s*"
    rf"(?P<unit>{UNIT_RE})",
    re.IGNORECASE,
)

CUMULATIVE_RE = re.compile(
    r"đến nay|den nay|tính đến|tinh den|tính tới|tinh toi|tổng|tong|"
    r"lũy kế|luy ke|cộng dồn|cong don|đã bán|da ban|bán được|ban duoc|"
    r"ghi nhận|ghi nhan|cán mốc|can moc|vượt mốc|vuot moc|đạt|dat|đón|don|"
    r"hơn|hon|gần|gan|kỷ lục|ky luc|to date|so far|cumulative|total|sold",
    re.IGNORECASE,
)

STRICT_PERIOD_RE = re.compile(
    r"hôm nay|hom nay|ngày đầu|ngay dau|ngày chiếu đầu|ngay chieu dau|"
    r"sau\s+(?:\d+|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười)\s+(?:ngày|ngay|tuần|tuan)|"
    r"cuối tuần|cuoi tuan|tuần đầu|tuan dau|tuần qua|tuan qua|trong ngày|trong ngay|"
    r"suất chiếu sớm|suat chieu som|đặt trước|dat truoc|pre-?sale|opening|weekend|daily|"
    r"bán sớm|ban som|đặt sớm|dat som|chưa ra rạp|chua ra rap|"
    r"trước ngày ra rạp|truoc ngay ra rap|trước giờ khởi chiếu|truoc gio khoi chieu|"
    r"chỉ sau|chi sau|sau vài ngày|vài ngày công chiếu|mới công chiếu",
    re.IGNORECASE,
)

STREAMING_RE = re.compile(
    r"tv360|truyền hình|truyen hinh|trực tuyến|truc tuyen|online|netflix|"
    r"streaming|lượt xem trực tiếp",
    re.IGNORECASE,
)
CINEMA_RE = re.compile(r"rạp|rap|cinema|phòng vé|phong ve|khán giả|khan gia", re.IGNORECASE)
REVENUE_RE = re.compile(
    rf"(?P<num>{NUMBER_RE})\s*(?P<scale>tỷ|ty|triệu|trieu)\s*(?:đồng|dong)?",
    re.IGNORECASE,
)
PROMO_RE = re.compile(
    r"miễn phí|mien phi|free|giveaway|tặng vé|tang ve|quà tặng|qua tang|"
    r"rút thăm|rut tham|đăng ký|dang ky|vnpay|app ngân hàng|app ngan hang",
    re.IGNORECASE,
)
SOCIAL_SOURCE_RE = re.compile(r"facebook|instagram|tiktok|youtube", re.IGNORECASE)
EVENT_RE = re.compile(
    r"showcase|buổi chiếu trước|chiếu trước|chieu truoc|chiếu thử|chieu thu|"
    r"sự kiện|su kien|buổi ra mắt|buoi ra mat",
    re.IGNORECASE,
)

WEB_COLUMNS = [
    "movie_name",
    "title_bovn",
    "source_url_doanhthuphim",
    "tickets_sold_web",
    "tickets_display",
    "tickets_basis",
    "ticket_status",
    "confidence",
    "source_title",
    "source_url",
    "source_name",
    "published",
    "snippet",
    "search_backend",
    "matched_query",
    "search_queries",
    "candidate_count",
    "error",
    "collected_at",
]


@dataclass
class SearchItem:
    title: str
    url: str
    description: str
    published: str | None
    source: str | None
    backend: str
    query: str


@dataclass
class TicketCandidate:
    tickets: int
    display: str
    context: str
    cumulative_cue: str | None
    period_cue: str | None
    score: float
    streaming: bool
    weak_unit: bool
    stale_revenue: bool
    published_ts: float
    title: str
    url: str
    source: str | None
    backend: str
    query: str


def _clean_xml_text(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        return urllib.parse.urlparse(url).netloc or None
    except ValueError:
        return None


def _resolve_bing_link(link: str) -> str:
    """Bing RSS links wrap the publisher URL in an apiclick redirect."""
    try:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
        return query.get("url", [link])[0]
    except (ValueError, IndexError):
        return link


def _fetch_feed(query: str, backend: str) -> list[SearchItem]:
    if backend not in RSS_ENDPOINTS:
        raise ValueError(f"Unknown search backend: {backend}")

    params = {"q": query}
    if backend == "bing":
        params.update({"format": "RSS", "setmkt": "vi-VN"})
    else:
        params.update({"hl": "vi", "gl": "VN", "ceid": "VN:vi"})

    url = RSS_ENDPOINTS[backend] + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()
    root = ET.fromstring(payload)

    items: list[SearchItem] = []
    for node in root.findall(".//item"):
        title = _clean_xml_text(node.findtext("title"))
        description = _clean_xml_text(node.findtext("description"))
        link = _clean_xml_text(node.findtext("link"))
        published = _clean_xml_text(node.findtext("pubDate")) or None

        source: str | None = None
        for child in node:
            tag = child.tag.lower()
            if tag.endswith("source") and child.text:
                source = _clean_xml_text(child.text)
                break
        if backend == "bing":
            link = _resolve_bing_link(link)
            source = source or _domain_from_url(link)

        if title and link:
            items.append(
                SearchItem(
                    title=title,
                    url=link,
                    description=description,
                    published=published,
                    source=source,
                    backend=backend,
                    query=query,
                )
            )
    return items


async def _fetch_items(query: str, backend: str) -> list[SearchItem]:
    def op() -> Any:
        return asyncio.to_thread(_fetch_feed, query, backend)

    return await with_retry(
        op,
        retries=RETRY_COUNT,
        base_backoff=RETRY_BACKOFF,
        label=f"{backend} rss: {query[:50]}",
    )


def _title_aliases(record: dict[str, Any]) -> list[str]:
    raw_names: list[str] = []
    for key in ("movie_name", "original_title", "title_bovn", "bov_title"):
        value = clean_text(record.get(key))
        if value and value not in raw_names:
            raw_names.append(value)

    variants: list[str] = list(raw_names)
    for raw in raw_names:
        first, second = split_titles(raw)
        if first:
            variants.append(first)
        if second:
            variants.append(second)
        variants.append(re.sub(r"\([^)]*\)", "", raw))
        if ":" in raw:
            variants.append(raw.split(":", 1)[0])
            # Short title without year, e.g. 'Doraemon Movie 45 (2026): ...'
            # -> 'Doraemon Movie 45', so short headlines still match.
            variants.append(re.sub(r"\([^)]*\)", "", raw.split(":", 1)[0]).strip())

    aliases: set[str] = set()
    for variant in variants:
        normalized = normalize_title(variant)
        if len(normalized) >= 3:
            aliases.add(normalized)
    return sorted(aliases, key=len, reverse=True)


def _has_alias(aliases: list[str], text: str, director: str | None) -> bool:
    normalized = normalize_title(text)
    director_norm = normalize_title(director) if director else ""
    for alias in aliases:
        if alias in normalized and (len(alias) >= 4 or (director_norm and director_norm in normalized)):
            return True
    return False


def _parse_number(num_text: str, scale: str | None) -> int | None:
    value = num_text.replace("\u00a0", " ").replace(" ", "").strip()
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", value):
        number = float(value.replace(".", "").replace(",", ""))
    elif re.fullmatch(r"\d+[.,]\d{1,2}", value):
        number = float(value.replace(",", "."))
    else:
        number = float(value.replace(".", "").replace(",", ""))

    scale_norm = (scale or "").lower()
    if scale_norm in {"tỷ", "ty"}:
        multiplier = 1_000_000_000
    elif scale_norm in {"triệu", "trieu", "million"}:
        multiplier = 1_000_000
    elif scale_norm in {"nghìn", "ngàn", "nghin", "k"}:
        multiplier = 1_000
    else:
        multiplier = 1
    return int(round(number * multiplier))


def _published_ts(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _is_stale_revenue(context: str, known_revenue_vnd: int | None) -> bool:
    """True when the evidence cites a much smaller revenue than the final total."""
    if not known_revenue_vnd:
        return False
    amounts = [
        _parse_number(match.group("num"), match.group("scale"))
        for match in REVENUE_RE.finditer(context)
    ]
    cited = [amount for amount in amounts if amount]
    if not cited:
        return False
    return max(cited) < known_revenue_vnd * 0.85


def _extract_candidates(
    item: SearchItem,
    aliases: list[str],
    director: str | None,
    known_revenue_vnd: int | None = None,
) -> list[TicketCandidate]:
    text = _clean_xml_text(f"{item.title}. {item.description}")
    if not _has_alias(aliases, text, director):
        return []

    candidates: list[TicketCandidate] = []
    for match in TICKET_RE.finditer(text):
        tickets = _parse_number(match.group("num"), match.group("scale"))
        if tickets is None or tickets < 1_000:
            continue

        start = max(0, match.start() - 110)
        end = min(len(text), match.end() + 110)
        context = text[start:end]
        display = text[match.start() : match.end()]

        if (
            PROMO_RE.search(context)
            or EVENT_RE.search(context)
            or SOCIAL_SOURCE_RE.search(item.source or "")
        ):
            continue

        unit_norm = normalize_title(match.group("unit"))
        weak_unit = "luot xem" in unit_norm
        streaming = bool(STREAMING_RE.search(context)) and not bool(CINEMA_RE.search(context))
        if weak_unit and not CINEMA_RE.search(context):
            continue

        cumulative_match = CUMULATIVE_RE.search(context)
        period_match = STRICT_PERIOD_RE.search(context)
        cumulative_cue = cumulative_match.group(0) if cumulative_match else None
        period_cue = period_match.group(0) if period_match else None
        stale_revenue = _is_stale_revenue(context, known_revenue_vnd)

        score = 40.0
        if any(alias in normalize_title(item.title) for alias in aliases):
            score += 15.0
        if cumulative_cue:
            score += 15.0
        if period_cue:
            score -= 30.0
        if streaming:
            score -= 45.0
        if weak_unit:
            score -= 25.0
        if re.search(r"đặt trước|dat truoc|pre-?sale", context, re.IGNORECASE):
            score -= 25.0
        if stale_revenue:
            score -= 30.0

        if score < 20.0:
            continue

        candidates.append(
            TicketCandidate(
                tickets=tickets,
                display=display,
                context=context,
                cumulative_cue=cumulative_cue,
                period_cue=period_cue,
                score=round(score, 2),
                streaming=streaming,
                weak_unit=weak_unit,
                stale_revenue=stale_revenue,
                published_ts=_published_ts(item.published),
                title=item.title,
                url=item.url,
                source=item.source,
                backend=item.backend,
                query=item.query,
            )
        )
    return candidates


def _is_confident(candidate: TicketCandidate) -> bool:
    return (
        candidate.score >= 55.0
        and candidate.tickets >= 10_000
        and not candidate.period_cue
        and not candidate.streaming
        and not candidate.weak_unit
        and not candidate.stale_revenue
    )


def _choose(candidates: list[TicketCandidate]) -> tuple[TicketCandidate | None, str]:
    if not candidates:
        return None, "not_found"
    ranked = sorted(
        candidates,
        key=lambda c: (c.score, c.tickets, c.published_ts),
        reverse=True,
    )
    best = ranked[0]
    if _is_confident(best):
        return best, "found"
    return best, "needs_review"


def _build_queries(record: dict[str, Any], max_queries: int) -> list[str]:
    title = clean_text(record.get("movie_name"))
    if not title:
        return []
    title = title.replace('"', " ").strip()
    director = clean_text(record.get("director"))
    original = clean_text(record.get("original_title"))

    queries = [
        f'"{title}" lượt khán giả',
        f'"{title}" lượt vé',
    ]
    if director:
        queries.append(f'"{title}" {director} khán giả')
    if original:
        queries.append(f'"{original}" tickets sold')

    seen: set[str] = set()
    unique: list[str] = []
    for query in queries:
        key = query.lower()
        if key not in seen:
            seen.add(key)
            unique.append(query)
    return unique[:max_queries]


def _blank_result(
    record: dict[str, Any],
    queries: list[str],
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "movie_name": clean_text(record.get("movie_name")),
        "title_bovn": clean_text(record.get("title_bovn") or record.get("bov_title")),
        "source_url_doanhthuphim": clean_text(record.get("source_url_doanhthuphim")),
        "tickets_sold_web": None,
        "tickets_display": None,
        "tickets_basis": None,
        "ticket_status": status,
        "confidence": None,
        "source_title": None,
        "source_url": None,
        "source_name": None,
        "published": None,
        "snippet": None,
        "search_backend": None,
        "matched_query": None,
        "search_queries": " | ".join(queries),
        "candidate_count": 0,
        "error": error,
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


async def search_movie_tickets(
    record: dict[str, Any],
    backends: tuple[str, ...] = ("bing", "google"),
    max_queries: int = 3,
) -> dict[str, Any]:
    """Search public news RSS feeds for a cumulative ticket count."""
    queries = _build_queries(record, max_queries)
    if not queries:
        return _blank_result(record, queries, "not_found", "missing_movie_name")

    aliases = _title_aliases(record)
    director = clean_text(record.get("director"))
    known_revenue_vnd = parse_money_vnd(clean_text(record.get("revenue_doanhthuphim")))
    candidates: list[TicketCandidate] = []
    errors: list[str] = []
    seen_items: set[str] = set()

    for backend in backends:
        for query in queries:
            try:
                items = await _fetch_items(query, backend)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{backend}:{exc.__class__.__name__}")
                continue

            for item in items:
                key = f"{backend}|{item.url}|{item.title}"
                if key in seen_items:
                    continue
                seen_items.add(key)
                candidates.extend(_extract_candidates(item, aliases, director, known_revenue_vnd))

            if any(_is_confident(candidate) for candidate in candidates):
                break
        if any(_is_confident(candidate) for candidate in candidates):
            break
        await polite_delay(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)

    # Deduplicate the same number from the same article.
    unique: dict[tuple[str, str], TicketCandidate] = {}
    for candidate in candidates:
        unique[(candidate.url, candidate.display)] = candidate
    candidates = list(unique.values())

    best, status = _choose(candidates)
    if best is None:
        if len(errors) == len(backends) * len(queries):
            return _blank_result(record, queries, "search_error", "; ".join(errors))
        return _blank_result(record, queries, "not_found", "; ".join(errors) if errors else None)

    return {
        "movie_name": clean_text(record.get("movie_name")),
        "title_bovn": clean_text(record.get("title_bovn") or record.get("bov_title")),
        "source_url_doanhthuphim": clean_text(record.get("source_url_doanhthuphim")),
        "tickets_sold_web": best.tickets,
        "tickets_display": best.display,
        "tickets_basis": "cumulative" if status == "found" else "partial_or_uncertain",
        "ticket_status": status,
        "confidence": best.score,
        "source_title": best.title,
        "source_url": best.url,
        "source_name": best.source,
        "published": datetime.fromtimestamp(best.published_ts, tz=timezone.utc).isoformat()
        if best.published_ts
        else None,
        "snippet": best.context,
        "search_backend": best.backend,
        "matched_query": best.query,
        "search_queries": " | ".join(queries),
        "candidate_count": len(candidates),
        "error": "; ".join(errors) if errors else None,
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def write_web_tickets_csv(rows: list[dict[str, Any]], path=None) -> None:
    target = path or TICKETS_WEB_CSV
    ensure_parent(target)
    frame = pd.DataFrame(rows)
    for column in WEB_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    frame = frame[WEB_COLUMNS]
    if "tickets_sold_web" in frame.columns:
        frame["tickets_sold_web"] = pd.to_numeric(frame["tickets_sold_web"]).astype("Int64")
    frame.to_csv(target, index=False, encoding="utf-8-sig")


def _record_key(record: dict[str, Any]) -> str:
    return str(record.get("source_url_doanhthuphim") or record.get("movie_name") or "")


async def run_web_ticket_search(
    limit: int | None = None,
    resume: bool = True,
    backends: tuple[str, ...] = ("bing", "google"),
    max_queries: int = 3,
    input_csv=None,
    output_csv=None,
    progress_path=None,
) -> list[dict[str, Any]]:
    """Collect web ticket evidence for every movie in the consolidated CSV."""
    source_csv = input_csv or MOVIES_CSV
    target_csv = output_csv or TICKETS_WEB_CSV
    state_path = progress_path or WEB_TICKETS_PROGRESS
    ensure_parent(target_csv)
    ensure_parent(state_path)

    frame = pd.read_csv(source_csv, dtype=str).where(pd.notna, None)
    records = frame.to_dict("records")
    if limit is not None:
        records = records[:limit]

    if not resume:
        write_jsonl(state_path, [])

    progress = {_record_key(row): row for row in read_jsonl(state_path)}
    results: list[dict[str, Any]] = []
    total = len(records)

    for index, record in enumerate(records, start=1):
        key = _record_key(record)
        if resume and key in progress:
            results.append(progress[key])
            continue

        print(f"[tickets-web {index}/{total}] {record.get('movie_name')}")
        result = await search_movie_tickets(record, backends=backends, max_queries=max_queries)
        append_jsonl(state_path, result)
        results.append(result)

    write_web_tickets_csv(results, target_csv)
    return results


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Search public news feeds for cumulative ticket counts"
    )
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N movies")
    parser.add_argument("--no-resume", action="store_true", help="Ignore saved progress")
    parser.add_argument(
        "--backend",
        choices=["bing", "google", "both"],
        default="both",
        help="RSS search backend (default: both, Bing first)",
    )
    parser.add_argument("--max-queries", type=int, default=3, help="Queries per backend")
    args = parser.parse_args(argv)

    backends = ("bing", "google") if args.backend == "both" else (args.backend,)
    results = asyncio.run(
        run_web_ticket_search(
            limit=args.limit,
            resume=not args.no_resume,
            backends=backends,
            max_queries=args.max_queries,
        )
    )
    print(
        json.dumps(
            [
                {
                    "movie_name": r["movie_name"],
                    "tickets_sold_web": r["tickets_sold_web"],
                    "tickets_display": r["tickets_display"],
                    "ticket_status": r["ticket_status"],
                    "source_url": r["source_url"],
                }
                for r in results
            ],
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
