"""Focused tests for the two DTP revenue visualization functions."""

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

REVENUE_CASES: tuple[tuple[str, str, str, str, int], ...] = (
    (
        "plot_dtp_revenue_histogram",
        "dtp_revenue_histogram",
        "chart_data",
        "dtp_revenue_histogram",
        2,
    ),
    (
        "plot_dtp_lower_bound_evidence",
        "dtp_lower_bound_evidence",
        "tables",
        "lower_bound_revenue_table",
        2,
    ),
)


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
            "_revenue_chart_test_helpers",
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


class DtpRevenueChartRenderingTests(unittest.TestCase):
    def test_revenue_charts_save_nonempty_pngs_and_expected_results(self) -> None:
        charts = _charts()
        report = _eda_helpers()._valid_report()
        root = _tmpdir(self)

        for function_name, chart_name, _group, _table, points in REVENUE_CASES:
            with self.subTest(function=function_name):
                output = root / "revenue" / "nested" / f"{chart_name}.png"
                result = getattr(charts, function_name)(report, output)

                self.assertTrue(output.is_file())
                self.assertGreater(output.stat().st_size, 1024)
                self.assertEqual(output.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(result.output_path, output)
                self.assertEqual(result.chart_name, chart_name)
                self.assertEqual(result.plotted_point_count, points)

    def test_each_revenue_chart_consumes_its_designated_table(self) -> None:
        charts = _charts()
        report = _eda_helpers()._valid_report()
        root = _tmpdir(self)

        for function_name, _chart_name, group, table_name, _points in REVENUE_CASES:
            with self.subTest(function=function_name):
                expected_table = getattr(report, group)[table_name]
                with mock.patch.object(
                    charts, "rows_as_dicts", wraps=charts.rows_as_dicts
                ) as rows_spy:
                    getattr(charts, function_name)(report, root / f"{function_name}.png")

                rows_spy.assert_called_once_with(expected_table)

    def test_empty_table_raises_descriptive_error(self) -> None:
        charts = _charts()
        helpers = _eda_helpers()
        report = helpers._valid_report()
        root = _tmpdir(self)

        for function_name, _chart_name, group, table_name, _points in REVENUE_CASES:
            with self.subTest(function=function_name):
                if group == "chart_data":
                    broken = helpers._with_chart(report, table_name, rows=())
                else:
                    broken = helpers._with_table(report, table_name, rows=())

                with _allow_unvalidated(charts):
                    with self.assertRaises(charts.VisualizationValidationError) as caught:
                        getattr(charts, function_name)(broken, root / f"{function_name}.png")

                message = str(caught.exception)
                self.assertIn(table_name, message)
                self.assertIn("at least one row", message)

    def test_malformed_revenue_data_raises_descriptive_error(self) -> None:
        charts = _charts()
        helpers = _eda_helpers()
        report = helpers._valid_report()
        root = _tmpdir(self)

        bad_histogram = helpers._with_chart(
            report,
            "dtp_revenue_histogram",
            rows=(("under_10b", -1),),
        )
        with _allow_unvalidated(charts):
            with self.assertRaises(charts.VisualizationValidationError) as caught:
                charts.plot_dtp_revenue_histogram(
                    bad_histogram, root / "bad_histogram.png"
                )
        self.assertIn("movie_count", str(caught.exception))
        self.assertIn("non-negative integer", str(caught.exception))

        lower_rows = report.tables["lower_bound_revenue_table"].rows
        bad_lower = helpers._with_table(
            report,
            "lower_bound_revenue_table",
            rows=(("M0099", *lower_rows[0][1:]), lower_rows[1]),
        )
        with _allow_unvalidated(charts):
            with self.assertRaises(charts.VisualizationValidationError) as caught:
                charts.plot_dtp_lower_bound_evidence(
                    bad_lower, root / "bad_lower.png"
                )
        self.assertIn("M0001", str(caught.exception))
        self.assertIn("movie_id", str(caught.exception))

    def test_validation_failure_prevents_rendering(self) -> None:
        charts = _charts()
        report = _eda_helpers()._valid_report()
        root = _tmpdir(self)

        for function_name, _chart_name, _group, _table, _points in REVENUE_CASES:
            with self.subTest(function=function_name):
                output = root / function_name / "blocked.png"
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
                        getattr(charts, function_name)(report, output)

                self.assertFalse(output.parent.exists())
                self.assertFalse(output.exists())

    def test_figures_are_closed_after_successful_rendering(self) -> None:
        charts = _charts()
        report = _eda_helpers()._valid_report()
        root = _tmpdir(self)
        plt = charts._matplotlib_modules()[1]
        plt.close("all")
        self.addCleanup(plt.close, "all")

        with mock.patch.object(plt, "close", wraps=plt.close) as close_spy:
            for function_name, _chart_name, _group, _table, _points in REVENUE_CASES:
                getattr(charts, function_name)(report, root / f"{function_name}.png")

        self.assertEqual(close_spy.call_count, len(REVENUE_CASES))
        self.assertEqual(plt.get_fignums(), [])

    def test_figure_is_closed_when_saving_raises(self) -> None:
        from matplotlib.figure import Figure

        charts = _charts()
        report = _eda_helpers()._valid_report()
        output = _tmpdir(self) / "save-error.png"
        plt = charts._matplotlib_modules()[1]
        plt.close("all")
        self.addCleanup(plt.close, "all")

        with mock.patch.object(
            Figure, "savefig", side_effect=OSError("simulated save failure")
        ), mock.patch.object(plt, "close", wraps=plt.close) as close_spy:
            with self.assertRaises(OSError):
                charts.plot_dtp_revenue_histogram(report, output)

        self.assertEqual(close_spy.call_count, 1)
        self.assertEqual(plt.get_fignums(), [])
        self.assertFalse(output.exists())

    def test_report_and_tables_remain_unchanged(self) -> None:
        charts = _charts()
        helpers = _eda_helpers()
        report = helpers._valid_report()
        before = helpers._snapshot_report(report)
        root = _tmpdir(self)

        for function_name, _chart_name, _group, _table, _points in REVENUE_CASES:
            getattr(charts, function_name)(report, root / f"{function_name}.png")

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

        revenue_fields = {
            field
            for chart_name, (_group, _table, fields) in (
                charts._REVENUE_TABLE_SPECS.items()
            )
            if chart_name != "bov_comparison_scatter"
            for field in fields
        }
        self.assertFalse(
            any("bov" in field.lower() for field in revenue_fields)
        )
        self.assertIn("plot_bov_comparison_scatter", charts.__all__)


class DtpRevenueChartContentTests(unittest.TestCase):
    def test_histogram_represents_exactly_90_rounded_rows(self) -> None:
        charts = _charts()
        report = _eda_helpers()._valid_report()
        table = report.chart_data["dtp_revenue_histogram"]

        result, fig = _call_capturing_figure(
            charts,
            "plot_dtp_revenue_histogram",
            report,
            _tmpdir(self) / "histogram.png",
        )

        represented = sum(row[1] for row in table.rows)
        self.assertEqual(represented, charts.EXPECTED_DTP_ROUNDED_ROWS)
        self.assertEqual(represented, 90)
        self.assertEqual(result.plotted_point_count, len(table.rows))
        self.assertEqual(table.columns, ("revenue_bin_vnd", "movie_count"))
        texts = _figure_texts(fig)
        self.assertTrue(any("90 rounded DTP observations" in text for text in texts))
        self.assertTrue(any("lower-bound observations are excluded" in text for text in texts))
        self.assertTrue(any("VND" in text for text in texts))

    def test_revenue_warning_appears_prominently_in_both_charts(self) -> None:
        charts = _charts()
        report = _eda_helpers()._valid_report()
        root = _tmpdir(self)
        expected = "Exploratory — revenue scope unverified"
        self.assertEqual(charts.REVENUE_WARNING_LABEL, expected)

        for function_name, _chart_name, _group, _table, _points in REVENUE_CASES:
            with self.subTest(function=function_name):
                _result, fig = _call_capturing_figure(
                    charts, function_name, report, root / f"{function_name}.png"
                )
                self.assertIn(expected, _figure_texts(fig))

    def test_lower_bound_ids_titles_and_display_values_are_rendered(self) -> None:
        charts = _charts()
        report = _eda_helpers()._valid_report()
        table = report.tables["lower_bound_revenue_table"]

        result, fig = _call_capturing_figure(
            charts,
            "plot_dtp_lower_bound_evidence",
            report,
            _tmpdir(self) / "lower_bound.png",
        )

        ax = fig.axes[0]
        label_text = "\n".join(
            label.get_text() for label in ax.get_yticklabels()
        )
        for row in table.rows:
            movie_id, title = row[0], row[1]
            display_value = row[5]
            self.assertIn(movie_id, label_text)
            self.assertIn(title, label_text)
            self.assertIn(display_value, _figure_texts(fig))

        self.assertEqual([row[0] for row in table.rows], ["M0001", "M0024"])
        self.assertEqual(
            [row[5] for row in table.rows], ["≥46000000000", "≥21000000000"]
        )
        self.assertEqual(result.plotted_point_count, 2)
        texts = _figure_texts(fig)
        self.assertTrue(any("Lower bounds only" in text for text in texts))
        self.assertTrue(
            any("excluded from the rounded-value histogram" in text for text in texts)
        )


if __name__ == "__main__":
    unittest.main()
