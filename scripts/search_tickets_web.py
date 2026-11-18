#!/usr/bin/env python3
"""Standalone wrapper for the web ticket-count search.

Examples:
    .venv/bin/python scripts/search_tickets_web.py --limit 5 --no-resume
    .venv/bin/python scripts/search_tickets_web.py --backend both
"""

from movie_data_collector.search_tickets_web import main

if __name__ == "__main__":
    main()
