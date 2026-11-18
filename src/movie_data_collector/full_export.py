from __future__ import annotations

import argparse
import re
from typing import Any

import pandas as pd

from .config import FULL_EXPORT_CSV, MOVIES_CSV, TICKETS_WEB_CSV
from .utils import clean_text, ensure_parent, parse_money_vnd

FULL_EXPORT_COLUMNS = [
    "movie_name",
    "original_title",
    "release_year",
    "genre",
    "director",
    "revenue",
    "tickets_sold",
    "screening_count",
    "to_review_director",
    "to_review_revenue",
    "to_review_tickets_sold",
    "to_review_screening_count",
    "to_review_match",
]

REVENUE_CONFLICT_THRESHOLD = 0.10


def _join_notes(notes: list[str | None]) -> str | None:
    values = [note for note in notes if note]
    return " | ".join(values) if values else None


def _shorten(text: str | None, limit: int = 240) -> str | None:
    value = clean_text(text)
    if not value:
        return None
    value = re.sub(r"\s+", " ", value)
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _source_note(label: str, url: str | None) -> str | None:
    url = clean_text(url)
    return f"{label}: {url}" if url else None


def _revenue_review(movie: dict[str, Any], dtp_num: int | None, bov_num: int | None) -> str | None:
    notes: list[str | None] = []
    dtp_raw = clean_text(movie.get("revenue_doanhthuphim"))
    bov_raw = clean_text(movie.get("revenue_bovn"))

    if not dtp_raw and not bov_raw:
        notes.append(
            _source_note("missing revenue", movie.get("source_url_doanhthuphim"))
        )
        return _join_notes(notes)

    if dtp_num and bov_num:
        difference = abs(dtp_num - bov_num) / max(dtp_num, bov_num)
        if difference > REVENUE_CONFLICT_THRESHOLD:
            notes.append(f"conflict: DTP {dtp_raw} ({movie.get('source_url_doanhthuphim')})")
            notes.append(f"BOV {bov_raw} ({movie.get('source_url_bovn')})")

    if movie.get("match_status") == "needs_review":
        notes.append(
            _source_note("uncertain BOV match", movie.get("source_url_bovn"))
        )

    return _join_notes(notes)


def build_full_export(
    movies_csv=None,
    tickets_csv=None,
    output_csv=None,
) -> pd.DataFrame:
    """Merge the box-office export with web ticket evidence into one review-friendly CSV."""
    movies = pd.read_csv(movies_csv or MOVIES_CSV, dtype=str, keep_default_na=False)
    tickets = pd.read_csv(tickets_csv or TICKETS_WEB_CSV, dtype=str, keep_default_na=False)

    ticket_by_key: dict[str, dict[str, Any]] = {}
    for row in tickets.to_dict("records"):
        key = clean_text(row.get("source_url_doanhthuphim")) or clean_text(row.get("movie_name"))
        if key:
            ticket_by_key[key] = row

    rows: list[dict[str, Any]] = []
    for movie in movies.to_dict("records"):
        key = clean_text(movie.get("source_url_doanhthuphim")) or clean_text(movie.get("movie_name"))
        web = ticket_by_key.get(key, {})

        dtp_raw = clean_text(movie.get("revenue_doanhthuphim"))
        bov_raw = clean_text(movie.get("revenue_bovn"))
        dtp_num = parse_money_vnd(dtp_raw)
        bov_num = parse_money_vnd(bov_raw)
        revenue = bov_raw or dtp_raw

        tickets_value = clean_text(movie.get("tickets_sold"))
        if not tickets_value and web.get("ticket_status") == "found":
            tickets_value = web.get("tickets_sold_web")

        review_tickets: list[str | None] = []
        if web.get("ticket_status") == "needs_review":
            review_tickets.append(
                _source_note("unconfirmed ticket figure", web.get("source_url"))
            )
            review_tickets.append(f"candidate: {_shorten(web.get('tickets_display'), 80)}")
            review_tickets.append(f"evidence: {_shorten(web.get('snippet'))}")

        review_match: str | None = None
        if movie.get("match_status") == "needs_review":
            review_match = _join_notes(
                [
                    _source_note("DTP", movie.get("source_url_doanhthuphim")),
                    _source_note("BOV", movie.get("source_url_bovn")),
                ]
            )

        rows.append(
            {
                "movie_name": clean_text(movie.get("movie_name")),
                "original_title": clean_text(movie.get("original_title")),
                "release_year": clean_text(movie.get("release_year")),
                "genre": clean_text(movie.get("genre")),
                "director": clean_text(movie.get("director")),
                "revenue": revenue,
                "tickets_sold": clean_text(tickets_value),
                "screening_count": clean_text(movie.get("screening_count")),
                "to_review_director": _source_note(
                    "missing director", movie.get("source_url_doanhthuphim")
                )
                if not clean_text(movie.get("director"))
                else None,
                "to_review_revenue": _revenue_review(movie, dtp_num, bov_num),
                "to_review_tickets_sold": _join_notes(review_tickets),
                "to_review_screening_count": None,
                "to_review_match": review_match,
            }
        )

    frame = pd.DataFrame(rows, columns=FULL_EXPORT_COLUMNS)
    target = output_csv or FULL_EXPORT_CSV
    ensure_parent(target)
    frame.to_csv(target, index=False, encoding="utf-8-sig")
    return frame


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build data/full_export.csv")
    parser.add_argument("--movies-csv", default=None)
    parser.add_argument("--tickets-csv", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    frame = build_full_export(args.movies_csv, args.tickets_csv, args.output)
    print(f"wrote {len(frame)} rows to {args.output or FULL_EXPORT_CSV}")


if __name__ == "__main__":
    main()
