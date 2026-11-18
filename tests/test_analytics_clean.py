"""Standard-library tests for the analytics cleaning and normalization layer."""

from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLEAN_PATH = (
    PROJECT_ROOT / "src" / "movie_data_collector" / "analytics" / "clean.py"
)

_spec = importlib.util.spec_from_file_location("analytics_clean_under_test", CLEAN_PATH)
if _spec is None or _spec.loader is None:
    raise AssertionError(f"Could not load clean module from {CLEAN_PATH}")
clean: ModuleType = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = clean
_spec.loader.exec_module(clean)

FieldStatus = clean.FieldStatus


def _movie(**overrides: Any) -> dict[str, Any]:
    row = {
        "movie_name": "Phim Hay",
        "title_bovn": "Phim Hay",
        "original_title": "Good Film",
        "release_year": "2024",
        "genre": "Hành động, Kinh dị",
        "director": "Nguyễn Văn Đức",
        "revenue_doanhthuphim": "100 tỷ",
        "revenue_bovn": "",
        "tickets_sold": "",
        "screening_count": "",
        "source_url_doanhthuphim": "https://doanhthuphim.vn/phim/phim-hay",
        "source_url_bovn": "https://boxoffice.test/phim-hay",
        "match_status": "matched",
        "collection_status": "ok",
    }
    row.update(overrides)
    return row


def _ticket(**overrides: Any) -> dict[str, Any]:
    row = {
        "movie_name": "Phim Hay",
        "title_bovn": "Phim Hay",
        "source_url_doanhthuphim": "https://doanhthuphim.vn/phim/phim-hay",
        "tickets_sold_web": "1000",
        "tickets_display": "1.000 vé",
        "tickets_basis": "partial_or_uncertain",
        "ticket_status": "needs_review",
        "confidence": "40.0",
        "source_title": "Tin tức: Phim Hay bán 1.000 vé",
        "source_url": "https://news.example.com/story?id=7",
        "source_name": "Example News",
        "published": "2026-11-18T00:00:00+00:00",
        "snippet": "",
        "search_backend": "google",
        "matched_query": "Phim Hay vé",
        "search_queries": "Phim Hay",
        "candidate_count": "1",
        "error": "",
        "collected_at": "2026-11-18T00:00:00+00:00",
    }
    row.update(overrides)
    return row


def _raw_inputs(
    movies: list[dict[str, Any]] | None = None,
    tickets: list[dict[str, Any]] | None = None,
    collection: list[dict[str, Any]] | None = None,
    boxoffice: list[dict[str, Any]] | None = None,
) -> Any:
    return clean.RawInputs(
        movies=tuple(movies if movies is not None else [_movie()]),
        collection_log=tuple(
            collection
            if collection is not None
            else [
                {
                    "source_url_doanhthuphim": "https://doanhthuphim.vn/phim/phim-hay",
                    "match_status": "matched",
                    "match_score": "95.0",
                    "match_reason": "auto",
                }
            ]
        ),
        tickets_sold_web=tuple(tickets if tickets is not None else [_ticket()]),
        boxoffice_matches=tuple(
            boxoffice
            if boxoffice is not None
            else [
                {
                    "movie_name": "Phim Hay",
                    "source_url_doanhthuphim": "https://doanhthuphim.vn/phim/phim-hay",
                    "source_url_bovn": "https://boxoffice.test/phim-hay",
                    "_bov_candidate": False,
                }
            ]
        ),
    )


def _clean_one_movie(**overrides: Any) -> Any:
    return clean.clean_raw_inputs(_raw_inputs(movies=[_movie(**overrides)])).movies[0]


def _clean_one_ticket(**overrides: Any) -> Any:
    return clean.clean_raw_inputs(
        _raw_inputs(tickets=[_ticket(**overrides)])
    ).tickets_sold_web[0]


class AnalyticsCleanTests(unittest.TestCase):
    def test_normal_movie_title(self) -> None:
        movie = _clean_one_movie(movie_name="Phim Hay")

        self.assertEqual(movie.movie_name_raw, "Phim Hay")
        self.assertEqual(movie.canonical_title, "Phim Hay")
        self.assertIs(movie.title_status, FieldStatus.VALID)

    def test_title_with_leading_trailing_whitespace_is_preserved_verbatim(self) -> None:
        title = "  Phim  test — Đưa  "

        movie = _clean_one_movie(movie_name=title)

        self.assertEqual(movie.movie_name_raw, title)
        self.assertEqual(movie.canonical_title, title)
        self.assertIs(movie.title_status, FieldStatus.VALID)

    def test_vietnamese_title_with_accents_is_preserved(self) -> None:
        title = "Người Vợ Ba: Bí Mật Đêm Thứ Sáu"

        movie = _clean_one_movie(movie_name=title)

        self.assertEqual(movie.canonical_title, title)

    def test_title_with_sequel_number_and_subtitle_is_preserved(self) -> None:
        title = "Chị Mười Ba: 3 Ngày Sinh Tử – Phần 2 (Đặc Biệt)"

        movie = _clean_one_movie(movie_name=title)

        self.assertEqual(movie.canonical_title, title)

    def test_missing_title_is_explicit(self) -> None:
        movie = _clean_one_movie(movie_name="")

        self.assertEqual(movie.movie_name_raw, "")
        self.assertEqual(movie.canonical_title, "")
        self.assertIs(movie.title_status, FieldStatus.MISSING)

    def test_whitespace_only_title_is_preserved_verbatim(self) -> None:
        title = "   \t  "

        movie = _clean_one_movie(movie_name=title)

        self.assertEqual(movie.movie_name_raw, title)
        self.assertEqual(movie.canonical_title, title)
        self.assertIs(movie.title_status, FieldStatus.MISSING)

    def test_missing_original_title_is_explicit(self) -> None:
        movie = _clean_one_movie(original_title="")

        self.assertEqual(movie.original_title_source, "")
        self.assertIsNone(movie.original_title_raw)
        self.assertIs(movie.original_title_status, FieldStatus.MISSING)

    def test_present_original_title_is_preserved(self) -> None:
        movie = _clean_one_movie(original_title="Endgame")

        self.assertEqual(movie.original_title_raw, "Endgame")
        self.assertIs(movie.original_title_status, FieldStatus.VALID)

    def test_valid_release_year(self) -> None:
        movie = _clean_one_movie(release_year="2024")

        self.assertEqual(movie.release_year, 2024)
        self.assertEqual(movie.release_year_source, "2024")
        self.assertIs(movie.release_year_status, FieldStatus.VALID)

    def test_missing_release_year(self) -> None:
        movie = _clean_one_movie(release_year="")

        self.assertIsNone(movie.release_year)
        self.assertIs(movie.release_year_status, FieldStatus.MISSING)

    def test_invalid_release_year(self) -> None:
        for invalid in ("20A4", "20245", "2024-01-01", "nan", " twenty "):
            with self.subTest(invalid=invalid):
                movie = _clean_one_movie(release_year=invalid)

                self.assertIsNone(movie.release_year)
                self.assertEqual(movie.release_year_source, invalid)
                self.assertIs(movie.release_year_status, FieldStatus.INVALID)

    def test_release_year_is_not_inferred_from_title_or_url(self) -> None:
        movie = _clean_one_movie(
            movie_name="Phim 2020",
            release_year="",
            source_url_doanhthuphim="https://example.test/2021/phim",
        )

        self.assertIsNone(movie.release_year)
        self.assertIs(movie.release_year_status, FieldStatus.MISSING)

    def test_genre_tokenization_with_multiple_values(self) -> None:
        movie = _clean_one_movie(genre="Hành động, Kinh dị, Tâm linh")

        self.assertEqual(
            movie.genre_tokens, ("Hành động", "Kinh dị", "Tâm linh")
        )
        self.assertEqual(
            movie.genre_token_path, "Hành động|Kinh dị|Tâm linh"
        )

    def test_genre_values_with_extra_whitespace_do_not_create_duplicate_tokens(self) -> None:
        movie = _clean_one_movie(genre=" Hành động ,  Hành động ,Kinh dị ")

        self.assertEqual(movie.genre_tokens, ("Hành động", "Kinh dị"))
        self.assertEqual(movie.genre_token_path, "Hành động|Kinh dị")

    def test_vietnamese_genre_text_is_preserved(self) -> None:
        genre = "Phim điện ảnh chiếu rạp, Kinh dị, Hành động"

        movie = _clean_one_movie(genre=genre)

        self.assertEqual(movie.genre_raw, genre)
        self.assertEqual(movie.genre_tokens[0], "Phim điện ảnh chiếu rạp")

    def test_deterministic_genre_token_order(self) -> None:
        genre = "Tâm linh, Hành động, Kinh dị"

        first = _clean_one_movie(genre=genre)
        second = _clean_one_movie(genre=genre)

        self.assertEqual(first.genre_tokens, ("Tâm linh", "Hành động", "Kinh dị"))
        self.assertEqual(first.genre_tokens, second.genre_tokens)
        self.assertEqual(first.genre_token_path, second.genre_token_path)

    def test_missing_genre(self) -> None:
        movie = _clean_one_movie(genre="")

        self.assertEqual(movie.genre_source, "")
        self.assertIsNone(movie.genre_raw)
        self.assertIs(movie.genre_status, FieldStatus.MISSING)
        self.assertEqual(movie.genre_tokens, ())
        self.assertIsNone(movie.genre_token_path)

    def test_genre_grouped_is_none_per_approved_design(self) -> None:
        movie = _clean_one_movie(genre="Hài, Hành động")

        self.assertIsNone(movie.genre_grouped)

    def test_director_normalization(self) -> None:
        movie = _clean_one_movie(director="  Nguyễn  Văn  Đức  ")

        self.assertEqual(movie.director_raw, "  Nguyễn  Văn  Đức  ")
        self.assertEqual(movie.director_norm_key, "nguyen van duc")
        self.assertIs(movie.director_status, FieldStatus.VALID)

    def test_director_normalization_strips_d_stroke_and_preserves_punctuation(self) -> None:
        movie = _clean_one_movie(director="Đặng–Nguyễn, Quang Dũng")

        self.assertEqual(movie.director_norm_key, "dang–nguyen, quang dung")

    def test_missing_director(self) -> None:
        movie = _clean_one_movie(director="")

        self.assertEqual(movie.director_source, "")
        self.assertIsNone(movie.director_raw)
        self.assertIsNone(movie.director_norm_key)
        self.assertIs(movie.director_status, FieldStatus.MISSING)

    def test_director_normalization_does_not_fuzzy_merge(self) -> None:
        first = _clean_one_movie(director="Trần Hữu Tấn")
        second = _clean_one_movie(director="Trần Hữu Tâm")

        self.assertNotEqual(first.director_norm_key, second.director_norm_key)

    def test_url_hostname_lowercasing(self) -> None:
        ticket = _clean_one_ticket(source_url="https://News.Example.com/story?id=7")

        self.assertEqual(
            ticket.source_url_normalized, "https://news.example.com/story?id=7"
        )

    def test_url_fragment_removal(self) -> None:
        ticket = _clean_one_ticket(
            source_url="https://news.example.com/story?id=7#section"
        )

        self.assertEqual(
            ticket.source_url_normalized, "https://news.example.com/story?id=7"
        )

    def test_tracking_parameter_removal(self) -> None:
        ticket = _clean_one_ticket(
            source_url=(
                "https://news.example.com/story/"
                "?utm_source=google&id=7&utm_medium=rss"
            )
        )

        self.assertEqual(
            ticket.source_url_normalized, "https://news.example.com/story?id=7"
        )

    def test_trailing_slash_handling(self) -> None:
        story = _clean_one_ticket(source_url="https://news.example.com/story/")
        root = _clean_one_ticket(source_url="https://news.example.com/")

        self.assertEqual(story.source_url_normalized, "https://news.example.com/story")
        self.assertEqual(root.source_url_normalized, "https://news.example.com")

    def test_google_news_rss_url_is_preserved_intact(self) -> None:
        url = "https://News.Google.com/rss/articles/ABC123?oc=5#top"

        ticket = _clean_one_ticket(source_url=url)

        self.assertEqual(ticket.source_url_normalized, url)
        self.assertIs(ticket.source_url_status, FieldStatus.VALID)

    def test_invalid_google_news_rss_url_is_rejected_before_preservation(self) -> None:
        ticket = _clean_one_ticket(
            source_url="https://news.google.com:99999/rss/articles/ABC123"
        )

        self.assertIsNone(ticket.source_url_normalized)
        self.assertIs(ticket.source_url_status, FieldStatus.INVALID)

    def test_raw_url_preservation(self) -> None:
        movie_url = "HTTPS://Example.COM/Phim/#frag?utm_source=x"
        ticket_url = "https://News.Example.com/Story/?utm_source=x#frag"

        result = clean.clean_raw_inputs(
            _raw_inputs(
                movies=[_movie(source_url_doanhthuphim=movie_url)],
                tickets=[_ticket(source_url=ticket_url)],
            )
        )

        self.assertEqual(result.movies[0].source_url_dtp, movie_url)
        self.assertEqual(result.tickets_sold_web[0].source_url_raw, ticket_url)
        self.assertEqual(result.tickets_sold_web[0].raw["source_url"], ticket_url)

    def test_source_url_dtp_is_not_normalized(self) -> None:
        url = "HTTPS://Example.COM/Phim/#frag?utm_source=x/"

        movie = _clean_one_movie(source_url_doanhthuphim=url)

        self.assertEqual(movie.source_url_dtp, url)
        self.assertIs(movie.source_url_dtp_status, FieldStatus.VALID)

    def test_ticket_title_normalization_preserves_punctuation(self) -> None:
        ticket = _clean_one_ticket(source_title="  Phim Hay: Đẹp!  ")

        self.assertEqual(ticket.source_title_normalized, "phim hay: dep!")

    def test_missing_ticket_url_and_title_are_explicit(self) -> None:
        ticket = _clean_one_ticket(source_url="", source_title="")

        self.assertIsNone(ticket.source_url_normalized)
        self.assertIs(ticket.source_url_status, FieldStatus.MISSING)
        self.assertIsNone(ticket.source_title_normalized)
        self.assertIs(ticket.source_title_status, FieldStatus.MISSING)

    def test_relative_ticket_url_is_invalid(self) -> None:
        for url in ("/story?id=7", "story?id=7", "?id=7", "#section"):
            with self.subTest(url=url):
                ticket = _clean_one_ticket(source_url=url)

                self.assertIsNone(ticket.source_url_normalized)
                self.assertIs(ticket.source_url_status, FieldStatus.INVALID)

    def test_ticket_url_without_scheme_is_invalid(self) -> None:
        ticket = _clean_one_ticket(source_url="news.example.com/story?id=7")

        self.assertIsNone(ticket.source_url_normalized)
        self.assertIs(ticket.source_url_status, FieldStatus.INVALID)

    def test_unsupported_ticket_url_scheme_is_invalid(self) -> None:
        ticket = _clean_one_ticket(source_url="ftp://news.example.com/story?id=7")

        self.assertIsNone(ticket.source_url_normalized)
        self.assertIs(ticket.source_url_status, FieldStatus.INVALID)

    def test_ticket_url_with_invalid_hostname_is_invalid(self) -> None:
        invalid_urls = (
            "https://[invalid-host",
            "https://exa mple.com/story",
            "https://bad_.example.com/story",
            "https://example..com/story",
            "https://-bad.example.com/story",
            "https://user@/story",
        )
        for url in invalid_urls:
            with self.subTest(url=url):
                ticket = _clean_one_ticket(source_url=url)

                self.assertIsNone(ticket.source_url_normalized)
                self.assertIs(ticket.source_url_status, FieldStatus.INVALID)

    def test_ticket_url_with_invalid_port_is_invalid(self) -> None:
        invalid_urls = (
            "https://example.com:99999/story",
            "https://example.com:abc/story",
            "https://example.com:/story",
        )
        for url in invalid_urls:
            with self.subTest(url=url):
                ticket = _clean_one_ticket(source_url=url)

                self.assertIsNone(ticket.source_url_normalized)
                self.assertIs(ticket.source_url_status, FieldStatus.INVALID)

    def test_valid_http_ticket_url_is_normalized(self) -> None:
        ticket = _clean_one_ticket(source_url="http://News.Example.com/Story/Path")

        self.assertEqual(
            ticket.source_url_normalized, "http://news.example.com/Story/Path"
        )
        self.assertIs(ticket.source_url_status, FieldStatus.VALID)

    def test_valid_https_ticket_url_is_normalized(self) -> None:
        ticket = _clean_one_ticket(source_url="https://News.Example.com/Story/Path")

        self.assertEqual(
            ticket.source_url_normalized, "https://news.example.com/Story/Path"
        )
        self.assertIs(ticket.source_url_status, FieldStatus.VALID)

    def test_existing_query_parameters_are_preserved(self) -> None:
        url = "https://news.example.com/story?ref=ABC&id=7&next=a%2Fb"

        ticket = _clean_one_ticket(source_url=url)

        self.assertEqual(
            ticket.source_url_normalized,
            "https://news.example.com/story?ref=ABC&id=7&next=a%2Fb",
        )

    def test_input_dictionaries_are_not_mutated(self) -> None:
        ticket_row = _ticket(
            source_url="https://News.Example.com/story/#x",
            proof={"quotes": ["raw quote"]},
        )
        collection_row = {
            "source_url_doanhthuphim": "https://example.test/a",
            "match_status": "matched",
            "match_score": "95.0",
            "match_reason": "auto",
            "context": {"tags": ["raw"]},
        }
        boxoffice_row = {
            "movie_name": "Phim Hay",
            "source_url_doanhthuphim": "https://example.test/a",
            "_bov_candidate": False,
            "evidence": {"items": ["raw"]},
        }
        raw = _raw_inputs(
            movies=[_movie(movie_name="  Phim Gốc  ")],
            tickets=[ticket_row],
            collection=[collection_row],
            boxoffice=[boxoffice_row],
        )
        snapshot = copy.deepcopy(raw)

        result = clean.clean_raw_inputs(raw)

        self.assertEqual(raw, snapshot)
        self.assertIsNot(result.tickets_sold_web[0].raw, raw.tickets_sold_web[0])
        self.assertIsNot(result.collection_log[0], raw.collection_log[0])
        self.assertIsNot(result.boxoffice_matches[0], raw.boxoffice_matches[0])

    def test_nested_output_objects_are_deep_copied(self) -> None:
        ticket_nested = {"quotes": ["one", "two"]}
        collection_nested = {"tags": ["alpha"]}
        boxoffice_nested = {"details": {"quotes": ["beta"]}}

        ticket_row = _ticket(source_url="https://news.example.com/story", proof=ticket_nested)
        collection_row = {
            "source_url_doanhthuphim": "https://example.test/a",
            "match_status": "matched",
            "match_score": "95.0",
            "match_reason": "auto",
            "context": collection_nested,
        }
        boxoffice_row = {
            "movie_name": "Phim Hay",
            "source_url_doanhthuphim": "https://example.test/a",
            "_bov_candidate": False,
            "evidence": boxoffice_nested,
        }
        raw = _raw_inputs(
            movies=[_movie(source_url_doanhthuphim="https://example.test/a")],
            tickets=[ticket_row],
            collection=[collection_row],
            boxoffice=[boxoffice_row],
        )
        snapshot = copy.deepcopy(raw)

        result = clean.clean_raw_inputs(raw)

        self.assertIsNot(result.tickets_sold_web[0].raw["proof"], ticket_nested)
        self.assertIsNot(
            result.tickets_sold_web[0].raw["proof"]["quotes"], ticket_nested["quotes"]
        )
        self.assertIsNot(result.collection_log[0]["context"], collection_nested)
        self.assertIsNot(
            result.collection_log[0]["context"]["tags"], collection_nested["tags"]
        )
        self.assertIsNot(result.boxoffice_matches[0]["evidence"], boxoffice_nested)
        self.assertIsNot(
            result.boxoffice_matches[0]["evidence"]["details"],
            boxoffice_nested["details"],
        )

        result.tickets_sold_web[0].raw["proof"]["quotes"].append("changed")
        result.collection_log[0]["context"]["tags"].append("changed")
        result.boxoffice_matches[0]["evidence"]["details"]["quotes"].append("changed")

        self.assertEqual(raw, snapshot)

    def test_collection_log_and_boxoffice_records_are_copied_unchanged(self) -> None:
        collection_row = {
            "source_url_doanhthuphim": "https://example.test/a",
            "match_status": "matched",
            "match_score": "95.0",
            "match_reason": "auto",
        }
        boxoffice_row = {
            "movie_name": "Phim Hay",
            "source_url_doanhthuphim": "https://example.test/a",
            "_bov_candidate": False,
            "nested": {"keep": ["as", "is"]},
        }
        raw = _raw_inputs(
            movies=[_movie(source_url_doanhthuphim="https://example.test/a")],
            collection=[collection_row],
            boxoffice=[boxoffice_row],
        )

        result = clean.clean_raw_inputs(raw)

        self.assertEqual(result.collection_log, (collection_row,))
        self.assertEqual(result.boxoffice_matches, (boxoffice_row,))
        self.assertIsNot(result.collection_log[0], collection_row)
        self.assertIsNot(result.boxoffice_matches[0], boxoffice_row)
        self.assertIsNot(result.boxoffice_matches[0]["nested"], boxoffice_row["nested"])

    def test_output_record_count_equals_input_movie_count(self) -> None:
        movies = [
            _movie(movie_name="Phim 1", source_url_doanhthuphim="https://test/1"),
            _movie(movie_name="Phim 2", source_url_doanhthuphim="https://test/2"),
            _movie(movie_name="Phim 3", source_url_doanhthuphim="https://test/3"),
        ]

        result = clean.clean_raw_inputs(
            _raw_inputs(movies=movies, tickets=[_ticket(), _ticket()])
        )

        self.assertEqual(len(result.movies), len(movies))
        self.assertEqual(len(result.tickets_sold_web), 2)
        self.assertEqual(result.movies[0].raw_source_row_dtp, 2)
        self.assertEqual(result.movies[1].raw_source_row_dtp, 3)
        self.assertEqual(result.movies[2].raw_source_row_dtp, 4)

    def test_invalid_source_structure_raises_descriptive_exception(self) -> None:
        valid_movie = _movie()
        valid_ticket = _ticket()

        cases = (
            (
                SimpleNamespace(
                    collection_log=(),
                    tickets_sold_web=(),
                    boxoffice_matches=(),
                ),
                "movies",
            ),
            (
                clean.RawInputs(
                    movies=(["not", "a", "mapping"],),
                    collection_log=(),
                    tickets_sold_web=(),
                    boxoffice_matches=(),
                ),
                "movies.csv",
            ),
            (
                clean.RawInputs(
                    movies=({"movie_name": "Only title"},),
                    collection_log=(),
                    tickets_sold_web=(),
                    boxoffice_matches=(),
                ),
                "original_title",
            ),
            (
                clean.RawInputs(
                    movies=(valid_movie,),
                    collection_log=(),
                    tickets_sold_web=({"source_url": "https://test/1"},),
                    boxoffice_matches=(),
                ),
                "source_url_doanhthuphim",
            ),
            (
                clean.RawInputs(
                    movies=(valid_movie,),
                    collection_log=(),
                    tickets_sold_web=(valid_ticket,),
                    boxoffice_matches=("not a mapping",),
                ),
                "boxoffice_matches.jsonl",
            ),
        )

        for raw, expected_message in cases:
            with self.subTest(expected_message=expected_message):
                with self.assertRaises(clean.CleaningInputError) as ctx:
                    clean.clean_raw_inputs(raw)
                self.assertIn(expected_message, str(ctx.exception))

    def test_non_string_source_value_raises_descriptive_exception(self) -> None:
        raw = _raw_inputs(movies=[_movie(movie_name=123)])

        with self.assertRaises(clean.CleaningInputError) as ctx:
            clean.clean_raw_inputs(raw)

        message = str(ctx.exception)
        self.assertIn("movies.csv row 2", message)
        self.assertIn("movie_name", message)
        self.assertIn("int", message)

    def test_clean_does_not_require_or_create_mapping_or_output(self) -> None:
        result = clean.clean_raw_inputs(_raw_inputs())

        fields = set(result.__dataclass_fields__)
        self.assertEqual(
            fields,
            {"movies", "collection_log", "tickets_sold_web", "boxoffice_matches"},
        )


if __name__ == "__main__":
    unittest.main()
