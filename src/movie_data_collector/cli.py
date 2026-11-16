from __future__ import annotations

import argparse
import asyncio
import json

from .pipeline import (
    collect_doanhthuphim,
    match_and_enrich,
    rematch_unmatched,
    run_full,
    write_outputs,
)


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


if __name__ == "__main__":
    main()
