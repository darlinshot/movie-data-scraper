"""Focused tests for the diagnostic BOV comparison scatter chart."""

from __future__ import annotations

import ast
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VISUALIZATION_DIR = (
    PROJECT_ROOT / "src" / "movie_data_collector" / "visualization"
)
_HELPERS: Any = None

EXCLUDED_SCATTER_IDS: tuple[str, ...] = (
    "M0001",
    "M0024",
    "M0016",
    "M0043",
)
HIGH_PRIORITY_IDS: tuple[str, ...] = ("M0020", "M0029", "M0030", "M0077")


def _load_module_from_path(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _helpers() -> Any:
    global _HELPERS
    if _HELPERS is None:
        _HELPERS = _load_module_from_path(
            "_bov_scatter_chart_test_helpers",
            Path(__file__).with_name("test_analytics_visualization_charts.py"),
        )
    return _HELPERS


def _tmpdir(test: unittest.TestCase) -> Path:
    return _helpers()._tmpdir(test)


def _charts() -> Any:
    return _helpers()._charts()


def _eda_helpers() -> Any:
    return _helpers()._helpers_module()


def _figure_texts(fig: Any) -> list[str]:
    return _helpers()._figure_texts(fig)


def _call_capturing_figure(
    charts: Any, function_name: str, report: Any, path: Path
) -> tuple[Any, Any]:
    return _helpers()._call_capturing_figure(
        charts, function_name, report, path
    )


def _allow_unvalidated(charts: Any) -> Any:
    return mock.patch.object(
        charts, "validate_visualization_report", return_value=object()
    )


def _actual_report() -> Any:
    return _eda_helpers().eda.build_eda_report()


def _with_scatter_rows(report: Any, rows: tuple[tuple[Any, ...], ...]) -> Any:
    return _eda_helpers()._with_chart(
        report, "bov_comparison_scatter", rows=rows
    )


def _replace_scatter_field(
    report: Any, target_movie_id: str, **changes: Any
) -> Any:
    columns = _eda_helpers()._SCATTER_COLUMNS
    rows: list[tuple[Any, ...]] = []
    for row in report.chart_data["bov_comparison_scatter"].rows:
        record = dict(zip(columns, row))
        if record["movie_id"] == target_movie_id:
            record.update(changes)
        rows.append(tuple(record[column] for column in columns))
    return _with_scatter_rows(report, tuple(rows))


class BovComparisonScatterRenderingTests(unittest.TestCase):
    def test_actual_eda_report_produces_valid_png(self) -> None:
        charts = _charts()
        report = _actual_report()
        output = _tmpdir(self) / "scatter" / "nested" / "bov_comparison.png"

        result = charts.plot_bov_comparison_scatter(report, output)

        self.assertTrue(output.is_file())
        self.assertGreater(output.stat().st_size, 1024)
        self.assertEqual(output.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(result.output_path, output)
        self.assertEqual(result.chart_name, "bov_comparison_scatter")
        self.assertEqual(result.plotted_point_count, 77)
        self.assertEqual(
            len(report.chart_data["bov_comparison_scatter"].rows), 77
        )

    def test_correct_scatter_table_is_consumed(self) -> None:
        charts = _charts()
        report = _eda_helpers()._valid_report()
        expected_table = report.chart_data["bov_comparison_scatter"]

        with mock.patch.object(
            charts, "rows_as_dicts", wraps=charts.rows_as_dicts
        ) as rows_spy:
            charts.plot_bov_comparison_scatter(
                report, _tmpdir(self) / "consumed.png"
            )

        rows_spy.assert_called_once_with(expected_table)

    def test_exact_population_is_enforced(self) -> None:
        charts = _charts()
        report = _eda_helpers()._valid_report()
        rows = report.chart_data["bov_comparison_scatter"].rows
        short_report = _with_scatter_rows(report, rows[:-1])

        with _allow_unvalidated(charts):
            with self.assertRaises(charts.VisualizationValidationError) as caught:
                charts.plot_bov_comparison_scatter(
                    short_report, _tmpdir(self) / "short.png"
                )

        message = str(caught.exception)
        self.assertIn("bov_comparison_scatter", message)
        self.assertIn("row count", message)
        self.assertIn("expected 77", message)

    def test_excluded_ids_are_rejected_if_introduced(self) -> None:
        charts = _charts()
        report = _eda_helpers()._valid_report()

        for movie_id in EXCLUDED_SCATTER_IDS:
            with self.subTest(excluded_id=movie_id):
                broken = _replace_scatter_field(
                    report, "M0002", movie_id=movie_id
                )
                with _allow_unvalidated(charts):
                    with self.assertRaises(
                        charts.VisualizationValidationError
                    ) as caught:
                        charts.plot_bov_comparison_scatter(
                            broken, _tmpdir(self) / f"{movie_id}.png"
                        )
                self.assertIn("must not appear", str(caught.exception))
                self.assertIn(movie_id, str(caught.exception))

    def test_missing_high_priority_id_is_rejected(self) -> None:
        charts = _charts()
        report = _eda_helpers()._valid_report()
        broken = _replace_scatter_field(report, "M0020", movie_id="M0099")

        with _allow_unvalidated(charts):
            with self.assertRaises(charts.VisualizationValidationError) as caught:
                charts.plot_bov_comparison_scatter(
                    broken, _tmpdir(self) / "missing_high.png"
                )

        message = str(caught.exception)
        self.assertIn("M0020", message)
        self.assertIn("high-priority", message)

    def test_incorrect_high_priority_flag_is_rejected(self) -> None:
        charts = _charts()
        report = _eda_helpers()._valid_report()
        broken = _replace_scatter_field(
            report, "M0029", review_priority="normal"
        )

        with _allow_unvalidated(charts):
            with self.assertRaises(charts.VisualizationValidationError) as caught:
                charts.plot_bov_comparison_scatter(
                    broken, _tmpdir(self) / "bad_priority.png"
                )

        message = str(caught.exception)
        self.assertIn("M0029", message)
        self.assertIn("review_priority", message)
        self.assertIn("expected 'high'", message)

    def test_invalid_revenue_coordinates_are_rejected(self) -> None:
        charts = _charts()
        report = _eda_helpers()._valid_report()
        invalid_values = (0, -1, float("nan"), float("inf"), float("-inf"))
        root = _tmpdir(self)

        for field in ("dtp_revenue_vnd", "bov_revenue_vnd"):
            for value in invalid_values:
                with self.subTest(field=field, value=value):
                    broken = _replace_scatter_field(report, "M0002", **{field: value})
                    with _allow_unvalidated(charts), mock.patch.object(
                        charts,
                        "_matplotlib_modules",
                        side_effect=AssertionError("rendering must not start"),
                    ):
                        with self.assertRaises(
                            charts.VisualizationValidationError
                        ) as caught:
                            charts.plot_bov_comparison_scatter(
                                broken, root / f"{field}_{value}.png"
                            )
                    message = str(caught.exception)
                    self.assertIn(field, message)
                    self.assertIn("finite positive revenue coordinate", message)

    def test_validation_failure_prevents_rendering(self) -> None:
        charts = _charts()
        report = _eda_helpers()._valid_report()
        output = _tmpdir(self) / "blocked" / "scatter.png"

        with mock.patch.object(
            charts,
            "validate_visualization_report",
            side_effect=charts.VisualizationValidationError("blocked"),
        ), mock.patch.object(
            charts,
            "_matplotlib_modules",
            side_effect=AssertionError("rendering must not start"),
        ):
            with self.assertRaises(charts.VisualizationValidationError):
                charts.plot_bov_comparison_scatter(report, output)

        self.assertFalse(output.parent.exists())
        self.assertFalse(output.exists())

    def test_figure_is_closed_after_successful_rendering(self) -> None:
        charts = _charts()
        report = _eda_helpers()._valid_report()
        plt = charts._matplotlib_modules()[1]
        plt.close("all")
        self.addCleanup(plt.close, "all")

        with mock.patch.object(plt, "close", wraps=plt.close) as close_spy:
            charts.plot_bov_comparison_scatter(
                report, _tmpdir(self) / "closed_success.png"
            )

        self.assertEqual(close_spy.call_count, 1)
        self.assertEqual(plt.get_fignums(), [])

    def test_figure_is_closed_when_saving_raises(self) -> None:
        from matplotlib.figure import Figure

        charts = _charts()
        report = _eda_helpers()._valid_report()
        output = _tmpdir(self) / "save_error.png"
        plt = charts._matplotlib_modules()[1]
        plt.close("all")
        self.addCleanup(plt.close, "all")

        with mock.patch.object(
            Figure, "savefig", side_effect=OSError("simulated save failure")
        ), mock.patch.object(plt, "close", wraps=plt.close) as close_spy:
            with self.assertRaises(OSError):
                charts.plot_bov_comparison_scatter(report, output)

        self.assertEqual(close_spy.call_count, 1)
        self.assertEqual(plt.get_fignums(), [])
        self.assertFalse(output.exists())

    def test_report_and_tables_remain_unchanged(self) -> None:
        charts = _charts()
        helpers = _eda_helpers()
        report = helpers._valid_report()
        before = helpers._snapshot_report(report)

        charts.plot_bov_comparison_scatter(
            report, _tmpdir(self) / "immutability.png"
        )

        self.assertEqual(helpers._snapshot_report(report), before)

    def test_no_csv_raw_input_or_forbidden_imports(self) -> None:
        charts = _charts()
        banned_imports = {"pandas", "numpy", "seaborn", "plotly"}
        banned_calls = {"open", "read_csv", "build_eda_report", "load_eda_dataset"}
        banned_tokens = (".csv", ".jsonl", "analytics_movie_id_map")

        for source in sorted(VISUALIZATION_DIR.glob("*.py")):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            imported: set[str] = set()
            called: set[str] = set()
            strings: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(
                        alias.name.split(".")[0] for alias in node.names
                    )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    called.add(node.func.id)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    strings.append(node.value)

            with self.subTest(source=source.name):
                self.assertFalse(imported & banned_imports)
                self.assertFalse(called & banned_calls)
                joined = "\n".join(strings)
                for token in banned_tokens:
                    self.assertNotIn(token, joined)

        self.assertEqual(
            charts._SCATTER_EXCLUDED_IDS,
            (*charts.LOWER_BOUND_IDS, charts.QUARANTINED_MOVIE_ID, charts.CANDIDATE_MOVIE_ID),
        )
        self.assertEqual(charts.ACCEPTED_HIGH_PRIORITY_IDS, HIGH_PRIORITY_IDS)


class BovComparisonScatterContentTests(unittest.TestCase):
    def test_warning_labels_scales_and_population_are_rendered(self) -> None:
        charts = _charts()
        report = _actual_report()
        result, fig = _call_capturing_figure(
            charts,
            "plot_bov_comparison_scatter",
            report,
            _tmpdir(self) / "content.png",
        )
        ax = fig.axes[0]

        self.assertEqual(result.plotted_point_count, 77)
        self.assertIn(charts.REVENUE_WARNING_LABEL, _figure_texts(fig))
        self.assertEqual(
            charts.REVENUE_WARNING_LABEL,
            "Exploratory — revenue scope unverified",
        )
        self.assertEqual(ax.get_xscale(), "log")
        self.assertEqual(ax.get_yscale(), "log")
        for token in ("DTP", "VND", "log scale"):
            self.assertIn(token, ax.get_xlabel())
        for token in ("BOV", "VND", "log scale"):
            self.assertIn(token, ax.get_ylabel())
        self.assertGreater(ax.get_xlim()[0], 0)
        self.assertGreater(ax.get_ylim()[0], 0)

    def test_high_priority_points_are_annotated_by_id(self) -> None:
        charts = _charts()
        report = _eda_helpers()._valid_report()
        _result, fig = _call_capturing_figure(
            charts,
            "plot_bov_comparison_scatter",
            report,
            _tmpdir(self) / "annotations.png",
        )
        ax = fig.axes[0]
        annotation_texts = [text.get_text() for text in ax.texts]

        for movie_id in HIGH_PRIORITY_IDS:
            self.assertIn(movie_id, annotation_texts)
        self.assertFalse(any(text.startswith("Film ") for text in annotation_texts))

        collections = {
            collection.get_label(): collection for collection in ax.collections
        }
        high = collections["High-priority review"]
        normal = next(
            collection
            for label, collection in collections.items()
            if label.startswith("Accepted comparison observations")
        )
        self.assertEqual(len(high.get_offsets()), 4)
        self.assertEqual(len(normal.get_offsets()), 73)
        self.assertGreater(high.get_sizes()[0], normal.get_sizes()[0])
        self.assertEqual(
            len(high.get_offsets()) + len(normal.get_offsets()), 77
        )

    def test_reference_band_is_diagnostic_and_uses_eda_metadata(self) -> None:
        charts = _charts()
        report = _eda_helpers()._valid_report()
        _result, fig = _call_capturing_figure(
            charts,
            "plot_bov_comparison_scatter",
            report,
            _tmpdir(self) / "reference.png",
        )
        ax = fig.axes[0]
        texts = _figure_texts(fig)

        self.assertEqual(
            report.chart_data["bov_comparison_scatter"].metadata[
                "gap_reference_pct"
            ],
            10,
        )
        self.assertTrue(
            any(label == "±10% diagnostic reference" for label in (
                collection.get_label() for collection in ax.collections
            ))
        )
        self.assertEqual(
            [line.get_label() for line in ax.lines], ["Identity y = x"]
        )
        joined = " ".join(texts)
        self.assertIn("77 accepted comparison observations", joined)
        self.assertIn("scope comparability has not been verified", joined.lower())
        self.assertIn("pending review", joined.lower())
        self.assertIn("diagnostic references only", joined.lower())
        self.assertIn("not validation thresholds", joined.lower())

    def test_no_regression_correlation_or_summary_statistics(self) -> None:
        charts = _charts()
        report = _eda_helpers()._valid_report()
        _result, fig = _call_capturing_figure(
            charts,
            "plot_bov_comparison_scatter",
            report,
            _tmpdir(self) / "no_statistics.png",
        )
        joined = " ".join(_figure_texts(fig)).lower()

        for token in (
            "regression",
            "correlation",
            "r =",
            "r²",
            "mean",
            "median",
            "total revenue",
            "forecast",
            "ranking",
        ):
            self.assertNotIn(token, joined)


if __name__ == "__main__":
    unittest.main()
