from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .config import DISCOVERED_CSV, PRESS_CSV, PRESS_PROGRESS, PRESS_SEED
from .search_tickets_web import (
    CINEMA_RE,
    CUMULATIVE_RE,
    EVENT_RE,
    PROMO_RE,
    REVENUE_RE,
    SOCIAL_SOURCE_RE,
    STRICT_PERIOD_RE,
    STREAMING_RE,
    SearchItem,
    _fetch_items,
    _has_alias,
    _parse_number,
    _published_ts,
    _title_aliases,
)
from .utils import (
    append_jsonl,
    clean_text,
    ensure_parent,
    normalize_title,
    polite_delay,
    read_jsonl,
    split_titles,
    write_jsonl,
)

# Press revenue is a fallback only: it never overwrites revenue_bovn.
# Every press row is marked to_review_revenue=needs_review, even when
# the automated search is confident, because a press figure is evidence,
# not a BoVN exact total. Keep source, snippet, published date and
# scope with the number so a human can verify it.

PRESS_COLUMNS = [
    "movie_name",
    "release_year",
    "release_date",
    "source_url_bovn",
    "revenue_bovn",
    "revenue_press",
    "revenue_press_display",
    "revenue_press_is_lower_bound",
    "revenue_press_basis",
    "revenue_press_status",
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
    "to_review_revenue",
]

FINAL_TOTAL_RE = re.compile(
    r"tổng doanh thu|tong doanh thu|tổng kết|tong ket|khép lại|khep lai|"
    r"cả năm|ca nam|top\s+\d+.*năm|năm\s+\d{4}",
    re.IGNORECASE,
)
FOREIGN_REVENUE_RE = re.compile(
    r"yên|yen|usd|đô la|do la|toàn cầu|toan cau|nhật bản|nhat ban",
    re.IGNORECASE,
)
VIETNAM_RE = re.compile(
    r"việt nam|viet nam|phòng vé việt|phong ve viet|rạp việt|rap viet",
    re.IGNORECASE,
)
LOWER_BOUND_RE = re.compile(r"hơn|hon|vượt|vuot|trên|tren|gần|gan", re.IGNORECASE)
# A figure that is only a target about to be reached, not revenue already
# earned: "chuẩn bị cán mốc 200 tỷ", "tiến gần cột mốc", "dự kiến đạt".
PROJECTION_RE = re.compile(
    r"chuẩn bị|chuan bi|sắp|sap|tiến gần|tien gan|dự kiến|du kien|"
    r"hướng tới|huong toi|dự đoán|du doan|kỳ vọng|ky vong|dự báo|du bao",
    re.IGNORECASE,
)
_SUBTITLE_STOPWORDS = {
    "nobita", "va", "vao", "trong", "cua", "phim", "dien", "anh", "movie", "the",
}


def _subtitle(title: str | None) -> str | None:
    """The part after the first colon, e.g. 'Nobita Và Bản Giao Hưởng Địa Cầu'.

    split_titles does not split on ':', so do it here. The subtitle is
    what distinguishes one film in a franchise from the next.
    """
    if not title:
        return None
    if ":" not in title:
        return None
    sub = title.split(":", 1)[1].strip()
    return sub or None


def _subtitle_tokens(record: dict[str, Any]) -> set[str]:
    title = clean_text(record.get("movie_name")) or ""
    text = _subtitle(title) or ""
    return {
        tok
        for tok in normalize_title(text).split()
        if tok not in _SUBTITLE_STOPWORDS
    }


def _specific_aliases(record: dict[str, Any]) -> list[str]:
    """Aliases that actually identify this film, not just its franchise.

    A short title like "Phim Điện Ảnh Doraemon" or "Doraemon" matches
    every Doraemon article, so it must not be enough on its own: an
    alias only counts as specific when it carries a number (45, 28,
    2021) or a subtitle token ("bản giao hưởng", "vùng đất lý tưởng").
    Without this, a search for Doraemon 2021 returns Doraemon Movie 45
    articles and records 200 tỷ for the wrong film.
    """
    subtitle_tokens = _subtitle_tokens(record)
    specific: list[str] = []
    subtitle_alias = normalize_title(_subtitle(clean_text(record.get("movie_name"))))
    candidates_aliases = _title_aliases(record) + [
        normalize_title(_short_title(record)),
        subtitle_alias,
    ]
    for alias in candidates_aliases:
        tokens = alias.split()
        if any(re.search(r"\d", tok) for tok in tokens):
            specific.append(alias)
        elif subtitle_tokens and any(tok in subtitle_tokens for tok in tokens):
            specific.append(alias)
    return sorted(set(specific), key=len, reverse=True)


def _specific_tokens(record: dict[str, Any]) -> set[str]:
    """Tokens that identify this film in a snippet: subtitle tokens plus
    any number token from the title (45, 28, 2021)."""
    title = clean_text(record.get("movie_name")) or ""
    tokens = _subtitle_tokens(record)
    tokens |= {
        tok for tok in normalize_title(title).split() if re.search(r"\d", tok)
    }
    return tokens


@dataclass
class RevenueCandidate:
    revenue: int
    display: str
    context: str
    cumulative_cue: str | None
    period_cue: str | None
    projection_cue: str | None
    is_lower_bound: bool
    is_final_total: bool
    score: float
    streaming: bool
    published_ts: float
    title: str
    url: str
    source: str | None
    backend: str
    query: str


def _short_title(record: dict[str, Any]) -> str:
    title = clean_text(record.get("movie_name")) or ""
    first, _second = split_titles(title)
    short = first or title
    if ":" in short:
        short = short.split(":", 1)[0].strip()
    # Drop a parenthetical year, e.g. "Doraemon Movie 45 (2026)" -> "Doraemon Movie 45",
    # so short headlines that omit the year still match the title.
    short = re.sub(r"\([^)]*\)", "", short).strip()
    return short or title


def _build_queries(record: dict[str, Any], max_queries: int) -> list[str]:
    title = clean_text(record.get("movie_name"))
    if not title:
        return []
    title = title.replace('"', " ").strip()
    subtitle = (_subtitle(title) or "").replace('"', " ").strip()
    franchise = _short_title(record).replace('"', " ").strip()
    # RSS search is recall-poor on long quoted titles, especially for
    # older films, so query by keyword + quoted subtitle phrase instead
    # of the full title. Precision comes from the specific-token filter
    # in _extract_candidates, not from the query.
    queries = [f'"{title}" doanh thu']
    if subtitle:
        queries.append(f'{franchise} "{subtitle}" doanh thu')
        queries.append(f'"{subtitle}" doanh thu tỷ')
    else:
        queries.append(f'"{franchise}" doanh thu tỷ')
        queries.append(f'"{franchise}" phòng vé Việt Nam')
    seen: set[str] = set()
    unique: list[str] = []
    for query in queries:
        key = query.lower()
        if key not in seen:
            seen.add(key)
            unique.append(query)
    return unique[:max_queries]


def _extract_candidates(
    item: SearchItem,
    aliases: list[str],
    director: str | None,
    specific_aliases: list[str] | None = None,
    specific_tokens: set[str] | None = None,
) -> list[RevenueCandidate]:
    text = f"{item.title}. {item.description}"
    if not _has_alias(aliases, text, director):
        return []
    # The article must match a specific alias, not just the franchise
    # short title (see _specific_aliases). A generic match alone means
    # the article is probably about another film in the same franchise.
    specific = specific_aliases if specific_aliases is not None else aliases
    if not _has_alias(specific, text, director):
        return []
    # The article must be about this movie's Vietnamese box office,
    # not a worldwide / Japan total that happens to mention the title.
    if not (CINEMA_RE.search(text) or "doanh thu" in normalize_title(text)):
        return []

    candidates: list[RevenueCandidate] = []
    for match in REVENUE_RE.finditer(text):
        revenue = _parse_number(match.group("num"), match.group("scale"))
        if revenue is None or revenue < 1_000_000_000:
            continue
        start = max(0, match.start() - 110)
        end = min(len(text), match.end() + 110)
        context = text[start:end]
        display = text[match.start() : match.end()]

        # The number's own context must identify this film, not just
        # the article as a whole: an article can list several films
        # in one franchise, and the figure next to another film's name
        # must not be recorded for this one.
        if specific_tokens is not None:
            context_tokens = set(normalize_title(context).split())
            if not (specific_tokens & context_tokens):
                continue

        if PROMO_RE.search(context) or EVENT_RE.search(context):
            continue
        if SOCIAL_SOURCE_RE.search(item.source or ""):
            continue
        # Foreign-currency / worldwide figure in the same context.
        if FOREIGN_REVENUE_RE.search(context) and not VIETNAM_RE.search(context):
            continue
        # Skip a figure that is clearly about another market in the snippet.
        if re.search(r"yên|yen|usd", context, re.IGNORECASE):
            continue

        streaming = bool(STREAMING_RE.search(context)) and not bool(
            CINEMA_RE.search(context)
        )
        cumulative_match = CUMULATIVE_RE.search(context)
        period_match = STRICT_PERIOD_RE.search(context)
        projection_match = PROJECTION_RE.search(context)
        cumulative_cue = cumulative_match.group(0) if cumulative_match else None
        period_cue = period_match.group(0) if period_match else None
        projection_cue = projection_match.group(0) if projection_match else None
        is_final = bool(FINAL_TOTAL_RE.search(context))
        prefix = text[max(0, match.start() - 25) : match.start()]
        is_lower_bound = bool(LOWER_BOUND_RE.search(prefix)) or bool(
            LOWER_BOUND_RE.search(context[:25])
        )
        if projection_cue:
            is_lower_bound = False

        score = 40.0
        if any(alias in normalize_title(item.title) for alias in aliases):
            score += 15.0
        if cumulative_cue:
            score += 15.0
        if is_final:
            score += 10.0
        if period_cue:
            score -= 30.0
        if projection_cue:
            score -= 30.0
        if streaming:
            score -= 45.0
        if re.search(r"đặt trước|dat truoc|pre-?sale", context, re.IGNORECASE):
            score -= 25.0
        if score < 20.0:
            continue

        candidates.append(
            RevenueCandidate(
                revenue=revenue,
                display=display,
                context=context,
                cumulative_cue=cumulative_cue,
                period_cue=period_cue,
                projection_cue=projection_cue,
                is_lower_bound=is_lower_bound,
                is_final_total=is_final,
                score=round(score, 2),
                streaming=streaming,
                published_ts=_published_ts(item.published),
                title=item.title,
                url=item.url,
                source=item.source,
                backend=item.backend,
                query=item.query,
            )
        )
    return candidates


def _is_confident(candidate: RevenueCandidate) -> bool:
    return (
        candidate.score >= 55.0
        and candidate.revenue >= 1_000_000_000
        and not candidate.period_cue
        and not candidate.projection_cue
        and not candidate.streaming
    )


def _choose(candidates: list[RevenueCandidate]) -> tuple[RevenueCandidate | None, str]:
    if not candidates:
        return None, "not_found"
    ranked = sorted(
        candidates,
        key=lambda c: (c.score, c.revenue, c.published_ts),
        reverse=True,
    )
    best = ranked[0]
    if _is_confident(best):
        return best, "found"
    return best, "needs_review"


def _blank_result(
    record: dict[str, Any],
    queries: list[str],
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "movie_name": clean_text(record.get("movie_name")),
        "release_year": clean_text(record.get("release_year")),
        "release_date": clean_text(record.get("release_date")),
        "source_url_bovn": clean_text(record.get("source_url_bovn")),
        "revenue_bovn": clean_text(record.get("revenue_bovn")),
        "revenue_press": None,
        "revenue_press_display": None,
        "revenue_press_is_lower_bound": None,
        "revenue_press_basis": None,
        "revenue_press_status": status,
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
        "to_review_revenue": "needs_review",
    }


async def search_press_revenue(
    record: dict[str, Any],
    backends: tuple[str, ...] = ("bing", "google"),
    max_queries: int = 3,
) -> dict[str, Any]:
    """Search public news RSS feeds for a cumulative press revenue figure."""
    queries = _build_queries(record, max_queries)
    if not queries:
        return _blank_result(record, queries, "not_found", "missing_movie_name")

    aliases = _title_aliases(record)
    short_alias = normalize_title(_short_title(record))
    if short_alias and short_alias not in aliases:
        aliases = aliases + [short_alias]
    specific_aliases = _specific_aliases(record)
    specific_tokens = _specific_tokens(record)
    director = clean_text(record.get("director"))
    candidates: list[RevenueCandidate] = []
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
                candidates.extend(
                    _extract_candidates(
                        item, aliases, director, specific_aliases, specific_tokens
                    )
                )
            if any(_is_confident(c) for c in candidates):
                break
        if any(_is_confident(c) for c in candidates):
            break
        await polite_delay(0.8, 1.8)

    unique: dict[tuple[str, str], RevenueCandidate] = {}
    for candidate in candidates:
        unique[(candidate.url, candidate.display)] = candidate
    candidates = list(unique.values())

    best, status = _choose(candidates)
    if best is None:
        if len(errors) == len(backends) * len(queries):
            return _blank_result(record, queries, "search_error", "; ".join(errors))
        return _blank_result(
            record, queries, "not_found", "; ".join(errors) if errors else None
        )

    basis = "cumulative"
    if best.projection_cue:
        basis = "projected"
    elif best.period_cue:
        basis = "cumulative_as_of_published"
    elif best.is_lower_bound:
        basis = "cumulative_lower_bound"

    return {
        "movie_name": clean_text(record.get("movie_name")),
        "release_year": clean_text(record.get("release_year")),
        "release_date": clean_text(record.get("release_date")),
        "source_url_bovn": clean_text(record.get("source_url_bovn")),
        "revenue_bovn": clean_text(record.get("revenue_bovn")),
        "revenue_press": best.revenue,
        "revenue_press_display": best.display,
        "revenue_press_is_lower_bound": best.is_lower_bound,
        "revenue_press_basis": basis,
        "revenue_press_status": status,
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
        "to_review_revenue": "needs_review",
    }


def write_press_csv(rows: list[dict[str, Any]], path: Path = PRESS_CSV) -> Path:
    ensure_parent(path)
    frame = pd.DataFrame(rows)
    for column in PRESS_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    frame = frame[PRESS_COLUMNS]
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def load_press_seed(path: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """Load manually verified press figures, keyed by BoVN URL.

    RSS search is recall-poor for older films, so the figures a human
    verified from press articles live here as data, with source URL,
    published date and snippet for every number. A seed entry is still
    fallback evidence, not a BoVN total: it is always marked
    to_review_revenue=needs_review. RSS search is only used for films
    with no seed entry.
    """
    seed_path = Path(path) if path else PRESS_SEED
    if not seed_path.exists():
        return {}
    try:
        data = json.loads(seed_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in data if isinstance(data, list) else []:
        url = row.get("source_url_bovn")
        if url:
            out[str(url)] = row
    return out


def _seed_result(record: dict[str, Any], seed: dict[str, Any]) -> dict[str, Any]:
    return {
        "movie_name": clean_text(record.get("movie_name")),
        "release_year": clean_text(record.get("release_year")),
        "release_date": clean_text(record.get("release_date")),
        "source_url_bovn": clean_text(record.get("source_url_bovn")),
        "revenue_bovn": clean_text(record.get("revenue_bovn")),
        "revenue_press": seed.get("revenue_press"),
        "revenue_press_display": seed.get("revenue_press_display"),
        "revenue_press_is_lower_bound": seed.get("revenue_press_is_lower_bound"),
        "revenue_press_basis": seed.get("revenue_press_basis"),
        "revenue_press_status": "found",
        "confidence": seed.get("confidence"),
        "source_title": seed.get("source_title"),
        "source_url": seed.get("source_url"),
        "source_name": seed.get("source_name"),
        "published": seed.get("published"),
        "snippet": seed.get("snippet"),
        "search_backend": "seed",
        "matched_query": "seed",
        "search_queries": "seed",
        "candidate_count": 1,
        "error": seed.get("note"),
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "to_review_revenue": "needs_review",
    }


def _record_key(record: dict[str, Any]) -> str:
    return str(record.get("source_url_bovn") or record.get("movie_name") or "")


def _norm_record(record: dict[str, Any]) -> dict[str, Any]:
    """Replace pandas NaN with None.

    pd.read_csv(dtype=str).where(pd.notna, None) still leaves float NaN
    in object columns, and NaN is truthy, so a naive `not r.get(...)`
    check would treat an empty revenue_bovn as present and skip the row.
    """
    return {
        key: (None if isinstance(value, float) and value != value else value)
        for key, value in record.items()
    }


async def run_press_revenue(
    limit: int | None = None,
    resume: bool = True,
    backends: tuple[str, ...] = ("bing", "google"),
    max_queries: int = 3,
    input_csv: Path | str | None = None,
    output_csv: Path | str | None = None,
    progress_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Collect press revenue evidence for discovered movies with no BoVN revenue."""
    source_csv = Path(input_csv) if input_csv else DISCOVERED_CSV
    target_csv = Path(output_csv) if output_csv else PRESS_CSV
    state_path = Path(progress_path) if progress_path else PRESS_PROGRESS
    ensure_parent(target_csv)
    ensure_parent(state_path)

    frame = pd.read_csv(source_csv, dtype=str).where(pd.notna, None)
    records = [
        _norm_record(r)
        for r in frame.to_dict("records")
        if not _norm_record(r).get("revenue_bovn")
    ]
    if limit is not None:
        records = records[:limit]

    if not resume:
        write_jsonl(state_path, [])

    progress = {_record_key(row): row for row in read_jsonl(state_path)}
    seed = load_press_seed()
    results: list[dict[str, Any]] = []
    total = len(records)

    for index, record in enumerate(records, start=1):
        key = _record_key(record)
        if resume and key in progress:
            results.append(progress[key])
            continue
        print(f"[press-revenue {index}/{total}] {record.get('movie_name')}")
        if key in seed:
            result = _seed_result(record, seed[key])
        else:
            result = await search_press_revenue(
                record, backends=backends, max_queries=max_queries
            )
        append_jsonl(state_path, result)
        results.append(result)

    write_press_csv(results, target_csv)
    return results


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Search public news feeds for cumulative press revenue figures"
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
        run_press_revenue(
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
                    "revenue_press": r["revenue_press"],
                    "revenue_press_display": r["revenue_press_display"],
                    "revenue_press_status": r["revenue_press_status"],
                    "confidence": r["confidence"],
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
