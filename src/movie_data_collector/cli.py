from __future__ import annotations

import argparse
import asyncio
import json

from playwright.async_api import async_playwright

from .config import (
    CHECKPOINT2_CORE_CSV,
    CONSOLIDATED_CHECKPOINT2_CSV,
    DISCOVERED_CSV,
    PRESS_CSV,
)
from .consolidate_checkpoint2 import build_consolidated_csv
from .discover_bovn import discover_bovn, load_seed_queries, write_discovered_csv
from .full_export import build_full_export
from .pipeline import (
    collect_doanhthuphim,
    match_and_enrich,
    rematch_unmatched,
    run_full,
    write_outputs,
)
from .press_revenue import run_press_revenue
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

    p_disc = sub.add_parser(
        "discover-bovn",
        help="Discover movies on Box Office Vietnam via search "
        "(for theatrical releases missing from DoanhThuPhim, e.g. anime)",
    )
    p_disc.add_argument("--seed-file", type=str, default=None)
    p_disc.add_argument("--query", action="append", default=[])
    p_disc.add_argument("--limit", type=int, default=None, help="Only use the first N queries")
    p_disc.add_argument("--no-detail", action="store_true", help="Skip BoVN detail pages")
    p_disc.add_argument("--no-resume", action="store_true")

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

    p_press = sub.add_parser(
        "press-revenue",
        help="Search public news RSS for cumulative press revenue figures "
        "for discovered movies with no BoVN revenue (fallback only, "
        "always marked needs_review, never overwrites revenue_bovn)",
    )
    p_press.add_argument("--limit", type=int, default=None, help="Only process the first N movies")
    p_press.add_argument("--no-resume", action="store_true", help="Ignore saved progress")
    p_press.add_argument(
        "--backend",
        choices=["bing", "google", "both"],
        default="both",
        help="RSS search backend (default: both, Bing first)",
    )
    p_press.add_argument("--max-queries", type=int, default=3, help="Queries per backend")

    sub.add_parser("export-full", help="Build the consolidated data/full_export.csv")

    p_consolidate = sub.add_parser(
        "consolidate-checkpoint2",
        help="Merge checkpoint 2 with BoVN discovery and press fallback, "
        "backfilling only missing name/director/revenue",
    )
    p_consolidate.add_argument("--checkpoint", default=str(CHECKPOINT2_CORE_CSV))
    p_consolidate.add_argument("--discovered", default=str(DISCOVERED_CSV))
    p_consolidate.add_argument("--press", default=str(PRESS_CSV))
    p_consolidate.add_argument("--output", default=str(CONSOLIDATED_CHECKPOINT2_CSV))

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
    elif args.cmd == "discover-bovn":
        queries = list(args.query or [])
        if args.seed_file:
            queries += load_seed_queries(args.seed_file)
        if not queries:
            parser.error("discover-bovn needs --seed-file or at least one --query")
        if args.limit is not None:
            queries = queries[: args.limit]

        async def _run_discover():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                recs = await discover_bovn(
                    page,
                    queries,
                    try_detail=not args.no_detail,
                    resume=not args.no_resume,
                )
                await browser.close()
            return recs

        recs = asyncio.run(_run_discover())
        path = write_discovered_csv(recs)
        print(f"wrote {len(recs)} rows to {path}")
        print(json.dumps([
            {
                "movie_name": r.get("movie_name"),
                "release_year": r.get("release_year"),
                "release_date": r.get("release_date"),
                "revenue_bovn": r.get("revenue_bovn"),
                "source_url_bovn": r.get("source_url_bovn"),
                "discovery_query": r.get("discovery_query"),
                "detail_status": r.get("detail_status"),
                "collection_status": r.get("collection_status"),
            }
            for r in recs
        ], ensure_ascii=False, indent=2))
    elif args.cmd == "export-full":
        frame = build_full_export()
        print(f"wrote {len(frame)} rows to data/full_export.csv")
    elif args.cmd == "consolidate-checkpoint2":
        frame = build_consolidated_csv(
            checkpoint_csv=args.checkpoint,
            discovered_csv=args.discovered,
            press_csv=args.press,
            output_csv=args.output,
        )
        print(f"wrote {len(frame)} rows to {args.output}")
    elif args.cmd == "press-revenue":
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
