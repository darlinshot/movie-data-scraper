from __future__ import annotations

import argparse
import asyncio
import json

from .full_export import build_full_export
from .pipeline import (
    collect_doanhthuphim,
    match_and_enrich,
    rematch_unmatched,
    run_full,
    write_outputs,
)
from .search_tickets_web import run_web_ticket_search


def main() -> None:
    parser = argparse.ArgumentParser(description="Vietnamese box office data collector")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_test = sub.add_parser("test", help="Collect and match a small sample")
    p_test.add_argument("--limit", type=int, default=5)
    p_test.add_argument("--no-resume", action="store_true")

    p_full = sub.add_parser("full", help="Run full collection")
    p_full.add_argument("--no-resume", action="store_true")

    p_dtp = sub.add_parser("collect-dtp", help="Collect only DoanhThuPhim records")
    p_dtp.add_argument("--limit", type=int, default=None)
    p_dtp.add_argument("--no-resume", action="store_true")

    sub.add_parser("rematch", help="Retry matching for not_found/needs_review records")

    p_web = sub.add_parser(
        "tickets-web", help="Search public web sources for cumulative ticket counts"
    )
    p_web.add_argument("--limit", type=int, default=None, help="Only process the first N movies")
    p_web.add_argument("--no-resume", action="store_true", help="Ignore saved progress")
    p_web.add_argument(
        "--backend",
        choices=["bing", "google", "both"],
        default="both",
        help="RSS search backend (default: both, Bing first)",
    )
    p_web.add_argument("--max-queries", type=int, default=3, help="Queries per backend")

    sub.add_parser("export-full", help="Build the consolidated data/full_export.csv")

    args = parser.parse_args()

    if args.cmd == "test":
        async def _run():
            dtp = await collect_doanhthuphim(limit=args.limit, resume=not args.no_resume)
            merged = await match_and_enrich(dtp, limit=args.limit, resume=not args.no_resume)
            write_outputs(merged)
            print(json.dumps([
                {
                    "movie_name": r.get("movie_name"),
                    "original_title": r.get("original_title"),
                    "release_year": r.get("release_year"),
                    "genre": r.get("genre"),
                    "director": r.get("director"),
                    "revenue_doanhthuphim": r.get("revenue_doanhthuphim"),
                    "revenue_bovn": r.get("revenue_bovn"),
                    "tickets_sold": r.get("tickets_sold"),
                    "screening_count": r.get("screening_count"),
                    "source_url_doanhthuphim": r.get("source_url_doanhthuphim"),
                    "source_url_bovn": r.get("source_url_bovn"),
                    "match_status": r.get("match_status"),
                    "collection_status": r.get("collection_status"),
                }
                for r in merged
            ], ensure_ascii=False, indent=2))
        asyncio.run(_run())
    elif args.cmd == "full":
        asyncio.run(run_full(resume=not args.no_resume))
    elif args.cmd == "collect-dtp":
        async def _run():
            dtp = await collect_doanhthuphim(limit=args.limit, resume=not args.no_resume)
            print(json.dumps(dtp, ensure_ascii=False, indent=2))
        asyncio.run(_run())
    elif args.cmd == "rematch":
        asyncio.run(rematch_unmatched())
    elif args.cmd == "export-full":
        frame = build_full_export()
        print(f"wrote {len(frame)} rows to data/full_export.csv")
    elif args.cmd == "tickets-web":
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
