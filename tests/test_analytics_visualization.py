"""Focused standard-library tests for the Python visualization contract."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EDA_PATH = (
    PROJECT_ROOT / "src" / "movie_data_collector" / "analytics" / "eda.py"
)
VALIDATION_PATH = (
    PROJECT_ROOT
    / "src"
    / "movie_data_collector"
    / "visualization"
    / "validation.py"
)
INIT_PATH = VALIDATION_PATH.with_name("__init__.py")


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


eda: ModuleType = _load_module("analytics_eda_for_visualization_tests", EDA_PATH)
validation: ModuleType = _load_module(
    "visualization_validation_under_test", VALIDATION_PATH
)

rows_as_dicts = validation.rows_as_dicts
validate_visualization_report = validation.validate_visualization_report
VisualizationValidationError = validation.VisualizationValidationError

_SCATTER_COLUMNS: tuple[str, ...] = (
    "movie_id",
    "canonical_title",
    "dtp_revenue_vnd",
    "dtp_revenue_quality",
    "bov_revenue_vnd",
    "revenue_gap_pct",
    "magnitude_gap_warning",
    "gap_band",
    "gap_band_label",
    "review_priority",
    "review_priority_label",
    "review_status",
    "review_status_label",
    "mapping_validation_status",
    "mapping_validation_status_label",
)

_PENDING_COLUMNS: tuple[str, ...] = (
    "movie_id",
    "canonical_title",
    "raw_source_row_dtp",
    "bov_match_status",
    "mapping_validation_status",
    "mapping_validation_status_label",
    "mapping_validation_reason",
    "review_status",
    "review_status_label",
    "review_priority",
    "review_priority_label",
    "data_quality_status",
    "has_pending_review",
    "include_revenue_comparison",
    "include_revenue_eda",
    "dtp_revenue_raw",
    "dtp_revenue_vnd",
    "dtp_revenue_quality",
    "workflow_note",
)

_LOWER_BOUND_COLUMNS: tuple[str, ...] = (
    "movie_id",
    "canonical_title",
    "dtp_revenue_raw",
    "dtp_revenue_vnd",
    "dtp_revenue_quality",
    "display_value",
    "include_revenue_eda",
)

_HIGH_PRIORITY_IDS = frozenset({"M0020", "M0029", "M0030", "M0077"})


def _metadata(**extra: Any) -> MappingProxyType[str, Any]:
    values: dict[str, Any] = {
        "revenue_warning_label": eda.REVENUE_WARNING_LABEL,
        "revenue_scope_verified": eda.REVENUE_SCOPE_VERIFIED,
    }
    values.update(extra)
    return MappingProxyType(values)


def _table(
    name: str,
    columns: tuple[str, ...],
    rows: tuple[tuple[Any, ...], ...],
    **kwargs: Any,
) -> Any:
    return eda.EdaTable(
        name=name,
        columns=columns,
        rows=rows,
        population=kwargs.get("population", "synthetic fixture"),
        filters=tuple(kwargs.get("filters", ())),
        exclusions=tuple(kwargs.get("exclusions", ())),
        notes=tuple(kwargs.get("notes", ())),
        metadata=kwargs.get("metadata", _metadata()),
    )


def _scatter_rows() -> tuple[tuple[Any, ...], ...]:
    ids = tuple(
        f"M{index:04d}"
        for index in range(2, 82)
        if index not in {16, 24, 43}
    )
    assert len(ids) == 77
    rows: list[tuple[Any, ...]] = []
    for offset, movie_id in enumerate(ids):
        priority = "high" if movie_id in _HIGH_PRIORITY_IDS else "normal"
        rows.append(
            (
                movie_id,
                f"Film {movie_id}",
                100_000_000_000 + offset,
                "rounded",
                90_000_000_000 + offset,
                10.0,
                0,
                "above_10pct_warning",
                "Above 10% reference warning",
                priority,
                "High" if priority == "high" else "Normal",
                "auto_accepted",
                "Automatically accepted",
                "matcher_accepted",
                "Matcher accepted",
            )
        )
    return tuple(rows)


def _valid_report() -> Any:
    director_rows = tuple(
        (
            f"Director {index}",
            f"director {index}",
            40 if index == 49 else 1,
        )
        for index in range(50)
    )
    chart_data = {
        "movie_match_status_donut": _table(
            "movie_status_counts",
            ("bov_match_status", "movie_count"),
            (("matched", 81), ("needs_review", 1), ("not_found", 10)),
        ),
        "release_year_histogram": _table(
            "release_year_distribution",
            ("release_year", "movie_count"),
            ((2024, 71), (2026, 21)),
        ),
        "release_year_match_status_stacked": _table(
            "release_year_match_matrix",
            ("release_year", "bov_match_status", "movie_count"),
            ((2024, "matched", 71), (2026, "matched", 21)),
        ),
        "genre_frequency_bar": _table(
            "genre_token_frequency",
            ("genre_token", "movie_count"),
            (("Drama", 92),),
        ),
        "director_profile_bar": _table(
            "director_profile",
            ("director_raw", "director_norm_key", "director_count"),
            director_rows,
        ),
        "independent_data_quality_flags": _table(
            "flag_summary",
            ("flag", "flag_label", "true_count", "false_count", "missing_count"),
            tuple(
                (f"flag_{index}", f"Flag {index}", 0, 92, 0)
                for index in range(11)
            ),
        ),
        "dtp_revenue_histogram": _table(
            "dtp_revenue_distribution",
            ("revenue_bin_vnd", "movie_count"),
            (("under_10b", 10), ("10b_to_under_50b", 80)),
        ),
        "bov_comparison_scatter": _table(
            "bov_comparison_scatter",
            _SCATTER_COLUMNS,
            _scatter_rows(),
            metadata=_metadata(gap_reference_pct=10),
        ),
    }
    summaries = {
        "dtp_revenue_population": _table(
            "dtp_revenue_population",
            ("metric", "value", "population", "notes"),
            (
                ("eligible_rows", 92, "DTP exploratory population", "note"),
                ("rounded_exact_rows", 90, "DTP exploratory population", "note"),
                ("lower_bound_rows", 2, "DTP exploratory population", "note"),
                ("missing_invalid_rows", 0, "DTP exploratory population", "note"),
            ),
        ),
    }
    tables = {
        "lower_bound_revenue_table": _table(
            "lower_bound_revenue_table",
            _LOWER_BOUND_COLUMNS,
            (
                (
                    "M0001",
                    "Film M0001",
                    "hơn 46 tỷ",
                    46_000_000_000,
                    "lower_bound",
                    "≥46000000000",
                    1,
                ),
                (
                    "M0024",
                    "Film M0024",
                    "hơn 21 tỷ",
                    21_000_000_000,
                    "lower_bound",
                    "≥21000000000",
                    1,
                ),
            ),
        ),
        "pending_workflow_table": _table(
            "pending_workflow_table",
            _PENDING_COLUMNS,
            (
                (
                    "M0016",
                    "Film M0016",
                    17,
                    "matched",
                    "known_false_positive_quarantined",
                    "Known false positive, quarantined",
                    "sequel_number_error",
                    "pending",
                    "Pending review",
                    "high",
                    "High",
                    "pending_review",
                    1,
                    0,
                    1,
                    None,
                    None,
                    None,
                    "Status only; no quarantined BOV value in general workflow.",
                ),
            ),
        ),
    }
    return eda.EdaReport(
        source_path=None,
        row_count=92,
        column_count=54,
        summaries=MappingProxyType(summaries),
        chart_data=MappingProxyType(chart_data),
        tables=MappingProxyType(tables),
        warnings=(),
    )


def _with_chart(report: Any, name: str, **changes: Any) -> Any:
    chart_data = dict(report.chart_data)
    chart_data[name] = replace(chart_data[name], **changes)
    return replace(report, chart_data=MappingProxyType(chart_data))


def _with_table(report: Any, name: str, **changes: Any) -> Any:
    tables = dict(report.tables)
    tables[name] = replace(tables[name], **changes)
    return replace(report, tables=MappingProxyType(tables))


def _snapshot_report(report: Any) -> tuple[Any, ...]:
    snapshots: list[Any] = []
    for group_name in ("summaries", "chart_data", "tables"):
        group = getattr(report, group_name)
        for name in sorted(group):
            table = group[name]
            snapshots.append(
                (
                    group_name,
                    name,
                    table.name,
                    table.columns,
                    table.rows,
                    dict(table.metadata),
                )
            )
    return tuple(snapshots)


class VisualizationAdapterTests(unittest.TestCase):
    def test_conversion_preserves_values_and_types(self) -> None:
        payload = object()
        table = _table(
            "typed_table",
            ("text", "number", "flag", "missing", "payload", "float"),
            (("keep  spaces", 7, True, None, payload, 1.5),),
        )

        records = rows_as_dicts(table)

        self.assertIsInstance(records, tuple)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["text"], "keep  spaces")
        self.assertEqual(record["number"], 7)
        self.assertIs(record["flag"], True)
        self.assertIsNone(record["missing"])
        self.assertIs(record["payload"], payload)
        self.assertIsInstance(record["float"], float)
        record["number"] = 99
        self.assertEqual(table.rows[0][1], 7)

    def test_duplicate_columns_are_rejected(self) -> None:
        table = _table(
            "bad_columns",
            ("a", "b", "a"),
            ((1, 2, 3),),
        )

        with self.assertRaises(VisualizationValidationError) as caught:
            rows_as_dicts(table)

        message = str(caught.exception)
        self.assertIn("bad_columns", message)
        self.assertIn("duplicate column", message)
        self.assertIn("('a',)", message)

    def test_invalid_row_lengths_are_rejected(self) -> None:
        table = _table(
            "bad_rows",
            ("a", "b", "c"),
            ((1, 2), (3, 4, 5, 6)),
        )

        with self.assertRaises(VisualizationValidationError) as caught:
            rows_as_dicts(table)

        message = str(caught.exception)
        self.assertIn("bad_rows", message)
        self.assertIn("row 0", message)
        self.assertIn("2 value(s)", message)
        self.assertIn("expected 3", message)


class VisualizationValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = _valid_report()

    def test_valid_synthetic_report_returns_expected_result(self) -> None:
        result = validate_visualization_report(self.report)

        self.assertEqual(result.validated_movie_count, 92)
        self.assertEqual(result.validation_status, "validated")
        self.assertEqual(
            result.validated_chart_table_names,
            (
                "movie_match_status_donut",
                "release_year_histogram",
                "release_year_match_status_stacked",
                "genre_frequency_bar",
                "director_profile_bar",
                "independent_data_quality_flags",
                "dtp_revenue_histogram",
                "bov_comparison_scatter",
            ),
        )
        self.assertEqual(
            result.validated_revenue_table_names,
            ("lower_bound_revenue_table", "pending_workflow_table"),
        )

    def test_missing_chart_ready_tables_are_rejected(self) -> None:
        chart_data = dict(self.report.chart_data)
        del chart_data["genre_frequency_bar"]
        missing_chart = replace(
            self.report, chart_data=MappingProxyType(chart_data)
        )
        with self.assertRaises(VisualizationValidationError) as caught:
            validate_visualization_report(missing_chart)
        message = str(caught.exception)
        self.assertIn("chart_data", message)
        self.assertIn("genre_frequency_bar", message)

        tables = dict(self.report.tables)
        del tables["pending_workflow_table"]
        missing_evidence = replace(
            self.report, tables=MappingProxyType(tables)
        )
        with self.assertRaises(VisualizationValidationError) as caught:
            validate_visualization_report(missing_evidence)
        self.assertIn("pending_workflow_table", str(caught.exception))

    def test_incorrect_column_order_or_missing_columns_are_rejected(self) -> None:
        scatter = self.report.chart_data["bov_comparison_scatter"]
        reordered = _with_chart(
            self.report,
            "bov_comparison_scatter",
            columns=tuple(reversed(scatter.columns)),
        )
        with self.assertRaises(VisualizationValidationError) as caught:
            validate_visualization_report(reordered)
        message = str(caught.exception)
        self.assertIn("bov_comparison_scatter", message)
        self.assertIn("column 0", message)
        self.assertIn("movie_id", message)

        missing = _with_chart(
            self.report,
            "bov_comparison_scatter",
            columns=scatter.columns[:-1],
        )
        with self.assertRaises(VisualizationValidationError) as caught:
            validate_visualization_report(missing)
        message = str(caught.exception)
        self.assertIn("missing columns", message)
        self.assertIn("mapping_validation_status_label", message)

    def test_incorrect_movie_population_is_rejected(self) -> None:
        bad_report_count = replace(self.report, row_count=91)
        with self.assertRaises(VisualizationValidationError) as caught:
            validate_visualization_report(bad_report_count)
        message = str(caught.exception)
        self.assertIn("row_count", message)
        self.assertIn("expected 92", message)
        self.assertIn("got 91", message)

        bad_status_sum = _with_chart(
            self.report,
            "movie_match_status_donut",
            rows=(("matched", 80), ("needs_review", 1), ("not_found", 10)),
        )
        with self.assertRaises(VisualizationValidationError) as caught:
            validate_visualization_report(bad_status_sum)
        message = str(caught.exception)
        self.assertIn("movie_match_status_donut", message)
        self.assertIn("movie_count sum", message)
        self.assertIn("expected 92", message)
        self.assertIn("got 91", message)

    def test_incorrect_revenue_warning_metadata_is_rejected(self) -> None:
        scatter = self.report.chart_data["bov_comparison_scatter"]
        base_metadata = dict(scatter.metadata)

        bad_label = _with_chart(
            self.report,
            "bov_comparison_scatter",
            metadata=MappingProxyType(
                {**base_metadata, "revenue_warning_label": "wrong label"}
            ),
        )
        with self.assertRaises(VisualizationValidationError) as caught:
            validate_visualization_report(bad_label)
        message = str(caught.exception)
        self.assertIn("bov_comparison_scatter", message)
        self.assertIn("revenue_warning_label", message)

        bad_scope = _with_chart(
            self.report,
            "bov_comparison_scatter",
            metadata=MappingProxyType(
                {**base_metadata, "revenue_scope_verified": True}
            ),
        )
        with self.assertRaises(VisualizationValidationError) as caught:
            validate_visualization_report(bad_scope)
        message = str(caught.exception)
        self.assertIn("revenue_scope_verified", message)
        self.assertIn("expected False", message)

        bad_gap_reference = _with_chart(
            self.report,
            "bov_comparison_scatter",
            metadata=MappingProxyType({**base_metadata, "gap_reference_pct": 20}),
        )
        with self.assertRaises(VisualizationValidationError) as caught:
            validate_visualization_report(bad_gap_reference)
        message = str(caught.exception)
        self.assertIn("gap_reference_pct", message)
        self.assertIn("expected 10", message)

    def test_lower_bound_ids_and_display_values_are_validated(self) -> None:
        result = validate_visualization_report(self.report)
        self.assertEqual(result.validation_status, "validated")

        lower_rows = self.report.tables["lower_bound_revenue_table"].rows
        wrong_ids = _with_table(
            self.report,
            "lower_bound_revenue_table",
            rows=(( "M0099", *lower_rows[0][1:]), lower_rows[1]),
        )
        with self.assertRaises(VisualizationValidationError) as caught:
            validate_visualization_report(wrong_ids)
        message = str(caught.exception)
        self.assertIn("lower_bound_revenue_table", message)
        self.assertIn("movie_id", message)
        self.assertIn("M0001", message)

        wrong_display = _with_table(
            self.report,
            "lower_bound_revenue_table",
            rows=(lower_rows[0], (*lower_rows[1][:5], "21000000000", 1)),
        )
        with self.assertRaises(VisualizationValidationError) as caught:
            validate_visualization_report(wrong_display)
        message = str(caught.exception)
        self.assertIn("display_value", message)
        self.assertIn("≥", message)

    def test_scatter_exclusions_and_exact_population_are_validated(self) -> None:
        rows = list(_scatter_rows())
        rows[0] = ("M0001", *rows[0][1:])
        forbidden_id = _with_chart(
            self.report,
            "bov_comparison_scatter",
            rows=tuple(rows),
        )
        with self.assertRaises(VisualizationValidationError) as caught:
            validate_visualization_report(forbidden_id)
        message = str(caught.exception)
        self.assertIn("bov_comparison_scatter", message)
        self.assertIn("exclusions", message)
        self.assertIn("M0001", message)

        short_scatter = _with_chart(
            self.report,
            "bov_comparison_scatter",
            rows=_scatter_rows()[:-1],
        )
        with self.assertRaises(VisualizationValidationError) as caught:
            validate_visualization_report(short_scatter)
        message = str(caught.exception)
        self.assertIn("row count", message)
        self.assertIn("expected 77", message)
        self.assertIn("got 76", message)

    def test_four_accepted_high_priority_scatter_rows_are_retained(self) -> None:
        rows = list(_scatter_rows())
        index = next(
            index for index, row in enumerate(rows) if row[0] == "M0020"
        )
        original = rows[index]
        rows[index] = (*original[:9], "normal", *original[10:])
        demoted = _with_chart(
            self.report,
            "bov_comparison_scatter",
            rows=tuple(rows),
        )
        with self.assertRaises(VisualizationValidationError) as caught:
            validate_visualization_report(demoted)
        message = str(caught.exception)
        self.assertIn("M0020", message)
        self.assertIn("review_priority", message)
        self.assertIn("expected 'high'", message)

        rows = [
            ("M0099", *row[1:]) if row[0] == "M0077" else row
            for row in _scatter_rows()
        ]
        missing_one = _with_chart(
            self.report,
            "bov_comparison_scatter",
            rows=tuple(rows),
        )
        with self.assertRaises(VisualizationValidationError) as caught:
            validate_visualization_report(missing_one)
        self.assertIn("M0077", str(caught.exception))

    def test_input_report_and_tables_are_not_mutated(self) -> None:
        before = _snapshot_report(self.report)

        validate_visualization_report(self.report)

        self.assertEqual(_snapshot_report(self.report), before)

        table = self.report.chart_data["movie_match_status_donut"]
        rows_before = table.rows
        records = rows_as_dicts(table)
        records[0]["movie_count"] = -1
        self.assertEqual(table.rows, rows_before)
        self.assertEqual(_snapshot_report(self.report), before)
        self.assertEqual(
            validate_visualization_report(self.report).validation_status,
            "validated",
        )


class VisualizationImportSafetyTests(unittest.TestCase):
    def test_validation_works_without_forbidden_data_or_plotting_imports(self) -> None:
        banned = {"pandas", "numpy", "matplotlib", "seaborn", "plotly"}
        for path in (VALIDATION_PATH, INIT_PATH):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            found: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    found.update(
                        alias.name.split(".")[0] for alias in node.names
                    )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    found.add(node.module.split(".")[0])
            self.assertFalse(
                found & banned,
                f"{path.name} imports forbidden modules: {sorted(found & banned)}",
            )

        for module_name in banned:
            self.assertNotIn(module_name, sys.modules)

        report = _valid_report()
        result = validate_visualization_report(report)
        self.assertEqual(result.validation_status, "validated")


class RealDataVisualizationTests(unittest.TestCase):
    def test_approved_csv_report_passes_visualization_preflight(self) -> None:
        report = eda.build_eda_report()
        result = validate_visualization_report(report)

        self.assertEqual(result.validated_movie_count, 92)
        self.assertEqual(result.validation_status, "validated")
        self.assertEqual(
            result.validated_chart_table_names,
            (
                "movie_match_status_donut",
                "release_year_histogram",
                "release_year_match_status_stacked",
                "genre_frequency_bar",
                "director_profile_bar",
                "independent_data_quality_flags",
                "dtp_revenue_histogram",
                "bov_comparison_scatter",
            ),
        )
        self.assertEqual(
            result.validated_revenue_table_names,
            ("lower_bound_revenue_table", "pending_workflow_table"),
        )


class VisualizationPackageImportTests(unittest.TestCase):
    def test_public_api_imports_from_movie_data_collector_visualization(self) -> None:
        src_path = PROJECT_ROOT / "src"
        package_path = src_path / "movie_data_collector"
        package_name = "movie_data_collector"
        module_name = "movie_data_collector.visualization"
        expected_exports = {
            "rows_as_dicts",
            "validate_visualization_report",
            "VisualizationValidationError",
            "VisualizationValidationResult",
        }

        self.assertTrue(INIT_PATH.is_file())
        self.assertFalse(INIT_PATH.with_name("init.py").exists())

        with mock.patch.dict(sys.modules), mock.patch.object(
            sys, "path", [str(src_path), *sys.path]
        ):
            for name in (
                "movie_data_collector.analytics",
                "movie_data_collector.analytics.eda",
                "movie_data_collector.visualization",
                "movie_data_collector.visualization.validation",
            ):
                sys.modules.pop(name, None)

            package = ModuleType(package_name)
            package.__path__ = [str(package_path)]
            sys.modules[package_name] = package

            imported = importlib.import_module(module_name)

            self.assertEqual(Path(imported.__file__).resolve(), INIT_PATH.resolve())
            self.assertTrue(expected_exports.issubset(set(imported.__all__)))
            for export in expected_exports:
                self.assertTrue(hasattr(imported, export), export)
            self.assertTrue(callable(imported.rows_as_dicts))
            self.assertTrue(callable(imported.validate_visualization_report))
            self.assertTrue(
                issubclass(imported.VisualizationValidationError, Exception)
            )
            self.assertTrue(isinstance(imported.VisualizationValidationResult, type))
            for field in (
                "validated_movie_count",
                "validated_chart_table_names",
                "validated_revenue_table_names",
                "validation_status",
            ):
                self.assertIn(
                    field, imported.VisualizationValidationResult.__dataclass_fields__
                )

            sample_table = _table("import_check", ("a", "b"), ((1, "keep"),))
            self.assertEqual(
                imported.rows_as_dicts(sample_table), ({"a": 1, "b": "keep"},)
            )
            self.assertEqual(
                imported.validate_visualization_report(
                    _valid_report()
                ).validation_status,
                "validated",
            )


if __name__ == "__main__":
    unittest.main()
