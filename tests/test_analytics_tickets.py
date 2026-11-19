"""Standard-library tests for the analytics ticket transformation layer."""

from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYTICS_DIR = PROJECT_ROOT / "src" / "movie_data_collector" / "analytics"


def _load_module(path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


clean = _load_module(ANALYTICS_DIR / "clean.py", "analytics_clean_for_ticket_tests")
ids = _load_module(ANALYTICS_DIR / "ids.py", "analytics_ids_for_ticket_tests")
tickets = _load_module(ANALYTICS_DIR / "tickets.py", "analytics_tickets_under_test")


FILM_A_URL = "https://doanhthuphim.vn/phim/film-a"
FILM_B_URL = "https://doanhthuphim.vn/phim/film-b"


def _mapped_movie(movie_id: str, url: str, title: str) -> Any:
    return ids.MappedMovie(
        movie_id=movie_id,
        source_url_dtp=url,
        canonical_title=title,
        release_year=2024,
        director_raw="Synthetic Director",
        url_history=(),
        status="active",
        created_at="2026-01-01T00:00:00Z",
        last_seen_at="2026-01-01T00:00:00Z",
    )


def _ticket_row(
    *,
    dtp_url: str = FILM_A_URL,
    source_url: str = "https://example.com/story",
    source_title: str = "Synthetic headline",
    tickets_display: str = "1 triệu vé",
    tickets_sold_web: str = "1000000",
    ticket_status: str = "found",
    source_name: str = "Example News",
    snippet: str = "Synthetic snippet",
) -> dict[str, str]:
    return {
        "movie_name": "Synthetic Film",
        "title_bovn": "Synthetic Film",
        "source_url_doanhthuphim": dtp_url,
        "tickets_sold_web": tickets_sold_web,
        "tickets_display": tickets_display,
        "tickets_basis": "cumulative",
        "ticket_status": ticket_status,
        "confidence": "70.0",
        "source_title": source_title,
        "source_url": source_url,
        "source_name": source_name,
        "published": "2026-01-01T00:00:00Z",
        "snippet": snippet,
        "search_backend": "bing",
        "matched_query": "synthetic",
        "search_queries": "synthetic",
        "candidate_count": "1",
        "error": "",
        "collected_at": "2026-01-01T00:00:00Z",
    }


def _empty_ticket_row(dtp_url: str = FILM_A_URL) -> dict[str, str]:
    return {
        "movie_name": "Synthetic Film",
        "title_bovn": "Synthetic Film",
        "source_url_doanhthuphim": dtp_url,
        "tickets_sold_web": "",
        "tickets_display": "",
        "tickets_basis": "",
        "ticket_status": "not_found",
        "confidence": "",
        "source_title": "",
        "source_url": "",
        "source_name": "",
        "published": "",
        "snippet": "",
        "search_backend": "",
        "matched_query": "",
        "search_queries": "synthetic",
        "candidate_count": "0",
        "error": "",
        "collected_at": "2026-01-01T00:00:00Z",
    }


def _case(
    ticket_rows: tuple[dict[str, str], ...],
    movies: tuple[tuple[str, str, str], ...] = (("M0001", FILM_A_URL, "Film A"),),
) -> SimpleNamespace:
    raw_inputs = clean.RawInputs(
        movies=(),
        collection_log=(),
        tickets_sold_web=ticket_rows,
        boxoffice_matches=(),
    )
    cleaned_inputs = clean.clean_raw_inputs(raw_inputs)
    mapped = tuple(_mapped_movie(*movie) for movie in movies)
    mapping = ids.MovieIdMapping(
        schema_version="1.0",
        generated_at="2026-01-01T00:00:00Z",
        source_anchor="source_url_doanhthuphim",
        id_prefix="M",
        movies=mapped,
    )
    assignment = ids.IdAssignmentResult(
        movie_ids_by_url={url: movie_id for movie_id, url, _ in movies},
        updated_mapping=mapping,
        summary=ids.AssignmentSummary(),
    )
    return SimpleNamespace(
        raw_inputs=raw_inputs,
        cleaned_inputs=cleaned_inputs,
        id_assignment=assignment,
    )


def _process(case: SimpleNamespace) -> Any:
    return tickets.process_tickets(
        case.raw_inputs, case.cleaned_inputs, case.id_assignment
    )


class TicketLinkTests(unittest.TestCase):
    def test_exact_dtp_url_join(self) -> None:
        case = _case(
            (
                _ticket_row(
                    dtp_url=FILM_B_URL,
                    source_title="Film B headline",
                    source_url="https://example.com/b",
                ),
                _ticket_row(
                    dtp_url=FILM_A_URL,
                    source_title="Film A headline",
                    source_url="https://example.com/a",
                ),
            ),
            (
                ("M0001", FILM_A_URL, "Film A"),
                ("M0002", FILM_B_URL, "Film B"),
            ),
        )
        result = _process(case)
        self.assertEqual(
            {c.movie_id for c in result.deduplicated_candidates}, {"M0001", "M0002"}
        )
        by_url = {c.source_url_doanhthuphim: c.movie_id for c in result.deduplicated_candidates}
        self.assertEqual(by_url[FILM_A_URL], "M0001")
        self.assertEqual(by_url[FILM_B_URL], "M0002")

    def test_unresolved_dtp_url_is_rejected(self) -> None:
        unknown_url = "https://doanhthuphim.vn/phim/unknown"
        case = _case((_ticket_row(dtp_url=unknown_url),))
        with self.assertRaises(tickets.TicketLinkUnresolvedError) as caught:
            _process(case)
        message = str(caught.exception)
        self.assertIn("TICKET_LINK_UNRESOLVED", message)
        self.assertIn(unknown_url, message)

    def test_title_mismatch_does_not_affect_exact_url_join(self) -> None:
        case = _case(
            (
                _ticket_row(
                    source_title="Completely unrelated headline",
                    source_url="https://example.com/unrelated",
                ),
            )
        )
        result = _process(case)
        self.assertEqual(len(result.deduplicated_candidates), 1)
        self.assertEqual(result.deduplicated_candidates[0].movie_id, "M0001")

    def test_empty_search_rows_are_not_candidates(self) -> None:
        case = _case((_empty_ticket_row(),))
        result = _process(case)
        self.assertEqual(result.linked_candidates, ())
        self.assertEqual(result.deduplicated_candidates, ())


class TicketDeduplicationTests(unittest.TestCase):
    def test_primary_key_duplicates_collapse(self) -> None:
        case = _case(
            (
                _ticket_row(
                    source_url="https://EXAMPLE.com/story/?utm_source=a",
                    source_title="Same   Title",
                    tickets_display="1 triệu",
                    tickets_sold_web="1000000",
                    ticket_status="found",
                    source_name="First Source",
                ),
                _ticket_row(
                    source_url="https://example.com/story",
                    source_title="same title",
                    tickets_display="1 triệu",
                    tickets_sold_web="1000000",
                    ticket_status="found",
                    source_name="Second Source",
                ),
            )
        )
        result = _process(case)
        self.assertEqual(len(result.linked_candidates), 2)
        self.assertEqual(len(result.deduplicated_candidates), 1)
        self.assertEqual(
            result.deduplicated_candidates[0].source_url_normalized,
            "https://example.com/story",
        )
        self.assertEqual(
            result.deduplicated_candidates[0].raw["source_name"], "First Source"
        )
        self.assertEqual(result.summaries["M0001"]["ticket_candidate_count"], 1)

    def test_different_ticket_observations_are_preserved(self) -> None:
        case = _case(
            (
                _ticket_row(
                    source_url="https://example.com/story",
                    source_title="Same Title",
                    tickets_display="1 triệu",
                    tickets_sold_web="1000000",
                    ticket_status="found",
                ),
                _ticket_row(
                    source_url="https://example.com/story",
                    source_title="same title",
                    tickets_display="2 triệu",
                    tickets_sold_web="2000000",
                    ticket_status="needs_review",
                ),
            )
        )
        result = _process(case)
        self.assertEqual(len(result.deduplicated_candidates), 2)
        self.assertEqual(
            {
                (c.tickets_display, c.ticket_status)
                for c in result.deduplicated_candidates
            },
            {("1 triệu", "found"), ("2 triệu", "needs_review")},
        )
        summary = result.summaries["M0001"]
        self.assertEqual(summary["ticket_candidate_count"], 2)
        self.assertEqual(summary["ticket_found_count"], 1)
        self.assertEqual(summary["ticket_needs_review_count"], 1)
        self.assertIsNone(summary["ticket_verified_admissions"])

    def test_url_normalization_evidence_sorting_and_deduplication(self) -> None:
        case = _case(
            (
                _ticket_row(
                    source_url="https://z.example.com/z/?utm_source=x",
                    source_title="Z headline",
                    tickets_display="3 triệu",
                    ticket_status="found",
                ),
                _ticket_row(
                    source_url="https://a.example.com/a",
                    source_title="A headline",
                    tickets_display="4 triệu",
                    ticket_status="found",
                ),
                _ticket_row(
                    source_url="https://a.example.com/a/?utm_source=y",
                    source_title="a headline",
                    tickets_display="4 triệu",
                    ticket_status="found",
                ),
            )
        )
        result = _process(case)
        self.assertEqual(len(result.deduplicated_candidates), 2)
        self.assertEqual(
            result.summaries["M0001"]["ticket_evidence_urls"],
            "https://a.example.com/a|https://z.example.com/z/?utm_source=x",
        )
        normalized = {c.source_url_normalized for c in result.deduplicated_candidates}
        self.assertEqual(
            normalized, {"https://a.example.com/a", "https://z.example.com/z"}
        )

    def test_google_news_rss_url_is_preserved(self) -> None:
        google_url = "https://news.google.com/rss/articles/abc?oc=5#frag"
        case = _case(
            (
                _ticket_row(
                    source_url=google_url,
                    source_title="Google News headline",
                    ticket_status="needs_review",
                    tickets_display="5 triệu",
                ),
            )
        )
        result = _process(case)
        candidate = result.deduplicated_candidates[0]
        self.assertEqual(candidate.source_url_normalized, google_url)
        self.assertEqual(result.summaries["M0001"]["ticket_evidence_urls"], google_url)


class TicketAggregationTests(unittest.TestCase):
    def test_context_quarantine_for_line_49(self) -> None:
        google_url = "https://news.google.com/rss/articles/tai?oc=5"
        rows = [_empty_ticket_row() for _ in range(47)]
        rows.append(
            _ticket_row(
                source_url=google_url,
                source_title="Mỹ Tâm 'công khai' với Mai Tài Phến",
                tickets_display="4.000 khán giả",
                tickets_sold_web="4000",
                ticket_status="needs_review",
            )
        )
        result = _process(_case(tuple(rows)))
        summary = result.summaries["M0001"]
        self.assertEqual(summary["ticket_candidate_count"], 1)
        self.assertEqual(summary["ticket_needs_review_count"], 1)
        self.assertEqual(
            summary["ticket_context_status"], "event_attendance_quarantined"
        )
        self.assertEqual(summary["ticket_evidence_urls"], google_url)
        self.assertIsNone(summary["ticket_verified_admissions"])

    def test_cinema_context_for_other_candidates(self) -> None:
        case = _case(
            (
                _ticket_row(
                    source_url="https://example.com/cinema",
                    ticket_status="found",
                ),
            )
        )
        summary = _process(case).summaries["M0001"]
        self.assertEqual(
            summary["ticket_context_status"], "cinema_candidate_unverified"
        )
        self.assertEqual(summary["ticket_data_status"], "unverified_candidates")

    def test_no_candidate_behavior_and_exact_fields(self) -> None:
        case = _case(
            (_empty_ticket_row(),),
            (
                ("M0001", FILM_A_URL, "Film A"),
                ("M0002", FILM_B_URL, "Film B"),
            ),
        )
        result = _process(case)
        self.assertEqual(tuple(result.summaries), ("M0001", "M0002"))
        expected = {
            "ticket_candidate_count": 0,
            "ticket_found_count": 0,
            "ticket_needs_review_count": 0,
            "ticket_verified_admissions": None,
            "ticket_data_status": "no_candidates",
            "ticket_context_status": "no_candidate",
            "ticket_evidence_urls": None,
        }
        for movie_id in ("M0001", "M0002"):
            with self.subTest(movie_id=movie_id):
                self.assertEqual(result.summaries[movie_id], expected)
                self.assertEqual(
                    tuple(result.summaries[movie_id]),
                    tuple(tickets.schema.GROUP_D_TICKET_COLUMNS),
                )

    def test_no_ticket_summation_or_verified_admissions(self) -> None:
        case = _case(
            (
                _ticket_row(
                    source_url="https://example.com/one",
                    source_title="One",
                    tickets_sold_web="8100000",
                    tickets_display="8,1 triệu",
                    ticket_status="found",
                ),
                _ticket_row(
                    source_url="https://example.com/two",
                    source_title="Two",
                    tickets_sold_web="3500000",
                    tickets_display="3,5 triệu",
                    ticket_status="needs_review",
                ),
            )
        )
        result = _process(case)
        summary = result.summaries["M0001"]
        self.assertIsNone(summary["ticket_verified_admissions"])
        self.assertEqual(summary["ticket_candidate_count"], 2)
        self.assertEqual(summary["ticket_found_count"], 1)
        self.assertEqual(summary["ticket_needs_review_count"], 1)
        self.assertEqual(
            set(tickets.ticket_field_names())
            & {"tickets_sold_web", "tickets_display", "tickets_total"},
            set(),
        )

    def test_raw_candidate_evidence_is_preserved(self) -> None:
        case = _case(
            (
                _ticket_row(
                    source_url="https://example.com/preserve",
                    source_title="Preserved headline",
                    tickets_display="8,1 triệu lượt",
                    tickets_sold_web="8100000",
                    ticket_status="found",
                    source_name="Kenh14",
                    snippet="Preserved snippet",
                ),
            )
        )
        candidate = _process(case).deduplicated_candidates[0]
        self.assertEqual(candidate.raw["source_name"], "Kenh14")
        self.assertEqual(candidate.raw["source_title"], "Preserved headline")
        self.assertEqual(candidate.raw["tickets_display"], "8,1 triệu lượt")
        self.assertEqual(candidate.raw["tickets_sold_web"], "8100000")
        self.assertEqual(candidate.raw["snippet"], "Preserved snippet")
        self.assertEqual(candidate.source_url_raw, "https://example.com/preserve")
        self.assertEqual(candidate.ticket_status, "found")


class TicketFieldApplicationTests(unittest.TestCase):
    def test_apply_ticket_fields_preserves_other_fields(self) -> None:
        case = _case(
            (
                _ticket_row(
                    source_url="https://example.com/apply",
                    ticket_status="found",
                ),
            )
        )
        result = _process(case)
        base_row = {
            "movie_id": "M0001",
            "canonical_title": "Film A",
            "review_priority": "high",
            "review_status": "pending",
            "ticket_candidate_count": 99,
        }
        updated = tickets.apply_ticket_fields([base_row], result.summaries)[0]
        self.assertEqual(updated["review_priority"], "high")
        self.assertEqual(updated["review_status"], "pending")
        self.assertEqual(updated["canonical_title"], "Film A")
        self.assertEqual(updated["ticket_candidate_count"], 1)
        self.assertEqual(updated["ticket_verified_admissions"], None)

    def test_inputs_and_base_rows_are_not_mutated(self) -> None:
        case = _case(
            (
                _ticket_row(
                    source_url="https://example.com/immutable",
                    ticket_status="found",
                ),
            )
        )
        raw_snapshot = copy.deepcopy(case.raw_inputs.tickets_sold_web)
        cleaned_snapshot = copy.deepcopy(case.cleaned_inputs.tickets_sold_web)
        base_row = {"movie_id": "M0001", "custom_note": "keep me"}
        base_snapshot = copy.deepcopy(base_row)

        result = _process(case)
        updated = tickets.apply_ticket_fields([base_row], result.summaries)

        self.assertEqual(case.raw_inputs.tickets_sold_web, raw_snapshot)
        self.assertEqual(case.cleaned_inputs.tickets_sold_web, cleaned_snapshot)
        self.assertEqual(base_row, base_snapshot)
        self.assertEqual(updated[0]["custom_note"], "keep me")
        self.assertIsNot(updated[0], base_row)


if __name__ == "__main__":
    unittest.main()
