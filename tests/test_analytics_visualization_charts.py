"""Focused tests for the six non-revenue Matplotlib chart functions."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHARTS_PATH = (
    PROJECT_ROOT
    / "src"
    / "movie_data_collector"
    / "visualization"
    / "charts.py"
)
_HELPERS = None
_CHARTS: Any = None

CHART_CASES: tuple[tuple[str, str, str, int], ...] = (
    (
        "plot_movie_match_status",
        "movie_match_status",
        "movie_match_status_donut",
        3,
    ),
    (
        "plot_release_year_distribution",
        "release_year_distribution",
        "release_year_histogram",
        2,
    ),
    (
        "plot_release_year_match_status",
        "release_year_match_status",
        "release_year_match_status_stacked",
        2,
    ),
    (
        "plot_genre_frequency",
        "genre_frequency",
        "genre_frequency_bar",
        1,
    ),
    (
        "plot_director_profile",
        "director_profile",
        "director_profile_bar",
        11,
    ),
    (
        "plot_data_quality_flags",
        "data_quality_flags",
        "independent_data_quality_flags",
        11,
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


def _helpers_module() -> ModuleType:
    global _HELPERS
    if _HELPERS is None:
        _HELPERS = _load_module_from_path(
            "_movie_viz_chart_test_helpers",
            Path(__file__).with_name("test_analytics_visualization.py"),
        )
    return _HELPERS


def _load_charts_module() -> Any:
    src_path = PROJECT_ROOT / "src"
    package_path = src_path / "movie_data_collector"
    with mock.patch.dict(sys.modules), mock.patch.object(
        sys, "path", [str(src_path), *sys.path]
    ):
        for name in (
            "movie_data_collector",
            "movie_data_collector.analytics",
            "movie_data_collector.analytics.eda",
            "movie_data_collector.visualization",
            "movie_data_collector.visualization.charts",
            "movie_data_collector.visualization.validation",
        ):
            sys.modules.pop(name, None)

        package = ModuleType("movie_data_collector")
        package.__path__ = [str(package_path)]
        sys.modules["movie_data_collector"] = package

        return importlib.import_module("movie_data_collector.visualization.charts")


def _charts() -> Any:
    global _CHARTS
    if _CHARTS is None:
        import matplotlib

        matplotlib.use("Agg", force=True)
        _CHARTS = _load_charts_module()
    return _CHARTS


def _tmpdir(test: unittest.TestCase) -> Path:
    path = Path(tempfile.mkdtemp(prefix="movie-viz-charts-"))
    test.addCleanup(shutil.rmtree, path, ignore_errors=True)
    return path


def _call(charts: Any, function_name: str, report: Any, path: Path) -> Any:
    return getattr(charts, function_name)(report, path)


def _allow_unvalidated(charts: Any) -> Any:
    return mock.patch.object(
        charts, "validate_visualization_report", return_value=object()
    )


def _call_capturing_figure(
    charts: Any, function_name: str, report: Any, path: Path
) -> tuple[Any, Any]:
    plt = charts._matplotlib_modules()[1]
    original_close = plt.close
    captured: list[Any] = []

    def capture_and_close(fig: Any) -> None:
        captured.append(fig)
        original_close(fig)

    with mock.patch.object(plt, "close", side_effect=capture_and_close):
        result = _call(charts, function_name, report, path)
    if len(captured) != 1:
        raise AssertionError(f"expected one captured figure, got {len(captured)}")
    return result, captured[0]


def _figure_texts(fig: Any) -> list[str]:
    texts = [text.get_text() for text in fig.texts]
    for ax in fig.axes:
        texts.extend(text.get_text() for text in ax.texts)
    return texts


class VisualizationChartRenderingTests(unittest.TestCase):
    def test_each_chart_saves_nonempty_png_and_expected_result(self) -> None:
        charts = _charts()
        report = _helpers_module()._valid_report()
        root = _tmpdir(self)

        for function_name, chart_name, _table_name, expected_points in CHART_CASES:
            with self.subTest(function=function_name):
                output = root / "nested" / "deeper" / f"{chart_name}.png"
                result = _call(charts, function_name, report, output)

                self.assertTrue(output.is_file())
                self.assertGreater(output.stat().st_size, 1024)
                self.assertEqual(output.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(result.output_path, output)
                self.assertEqual(result.chart_name, chart_name)
                self.assertEqual(
                    result.plotted_point_count, expected_points
                )

    def test_each_chart_consumes_its_declared_chart_ready_table(self) -> None:
        charts = _charts()
        report = _helpers_module()._valid_report()
        root = _tmpdir(self)

        for function_name, _chart_name, table_name, _points in CHART_CASES:
            with self.subTest(function=function_name):
                expected_table = report.chart_data[table_name]
                output = root / f"{function_name}.png"
                with mock.patch.object(
                    charts, "rows_as_dicts", wraps=charts.rows_as_dicts
                ) as rows_spy:
                    _call(charts, function_name, report, output)

                rows_spy.assert_called_once_with(expected_table)

    def test_empty_required_table_raises_descriptive_error(self) -> None:
        charts = _charts()
        helpers = _helpers_module()
        report = helpers._valid_report()
        root = _tmpdir(self)
        error_type = charts.VisualizationValidationError

        for function_name, _chart_name, table_name, _points in CHART_CASES:
            with self.subTest(function=function_name):
                empty_report = helpers._with_chart(
                    report, table_name, rows=()
                )
                with _allow_unvalidated(charts):
                    with self.assertRaises(error_type) as caught:
                        _call(
                            charts,
                            function_name,
                            empty_report,
                            root / f"{function_name}.png",
                        )

                message = str(caught.exception)
                self.assertIn(table_name, message)
                self.assertIn("at least one row", message)

    def test_malformed_count_raises_descriptive_error(self) -> None:
        charts = _charts()
        helpers = _helpers_module()
        report = helpers._with_chart(
            helpers._valid_report(),
            "movie_match_status_donut",
            rows=(("matched", -1),),
        )

        with _allow_unvalidated(charts):
            with self.assertRaises(charts.VisualizationValidationError) as caught:
                _call(
                    charts,
                    "plot_movie_match_status",
                    report,
                    _tmpdir(self) / "bad.png",
                )

        message = str(caught.exception)
        self.assertIn("movie_count", message)
        self.assertIn("non-negative integer", message)

    def test_validation_failure_prevents_rendering(self) -> None:
        charts = _charts()
        helpers = _helpers_module()
        report = helpers._valid_report()
        output = _tmpdir(self) / "must_not_exist" / "blocked.png"

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
                _call(charts, "plot_movie_match_status", report, output)

        self.assertFalse(output.parent.exists())
        self.assertFalse(output.exists())

    def test_figures_are_closed_after_successful_rendering(self) -> None:
        charts = _charts()
        report = _helpers_module()._valid_report()
        root = _tmpdir(self)
        plt = charts._matplotlib_modules()[1]
        plt.close("all")
        self.addCleanup(plt.close, "all")

        with mock.patch.object(plt, "close", wraps=plt.close) as close_spy:
            for function_name, _chart_name, _table_name, _points in CHART_CASES:
                _call(charts, function_name, report, root / f"{function_name}.png")

        self.assertEqual(close_spy.call_count, len(CHART_CASES))
        self.assertEqual(plt.get_fignums(), [])

    def test_figure_is_closed_when_saving_raises(self) -> None:
        from matplotlib.figure import Figure

        charts = _charts()
        report = _helpers_module()._valid_report()
        output = _tmpdir(self) / "save-error.png"
        plt = charts._matplotlib_modules()[1]
        plt.close("all")
        self.addCleanup(plt.close, "all")

        with mock.patch.object(
            Figure, "savefig", side_effect=OSError("simulated save failure")
        ), mock.patch.object(plt, "close", wraps=plt.close) as close_spy:
            with self.assertRaises(OSError):
                _call(charts, "plot_genre_frequency", report, output)

        self.assertEqual(close_spy.call_count, 1)
        self.assertEqual(plt.get_fignums(), [])
        self.assertFalse(output.exists())

    def test_report_and_tables_remain_unchanged(self) -> None:
        charts = _charts()
        helpers = _helpers_module()
        report = helpers._valid_report()
        before = helpers._snapshot_report(report)
        root = _tmpdir(self)

        for function_name, _chart_name, _table_name, _points in CHART_CASES:
            _call(charts, function_name, report, root / f"{function_name}.png")

        self.assertEqual(helpers._snapshot_report(report), before)

    def test_source_has_no_forbidden_io_or_dataframe_imports(self) -> None:
        charts = _charts()
        tree = ast.parse(CHARTS_PATH.read_text(encoding="utf-8"))
        imported: set[str] = set()
        called: set[str] = set()
        strings: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
            ):
                strings.append(node.value)

        self.assertFalse(imported & {"pandas", "numpy", "seaborn", "plotly"})
        self.assertFalse(
            called
            & {"open", "read_csv", "build_eda_report", "load_eda_dataset"}
        )
        joined = "\n".join(strings)
        for token in (".csv", ".jsonl", "analytics_movie_id_map"):
            self.assertNotIn(token, joined)

        fields = {
            field
            for required in charts._REQUIRED_FIELDS.values()
            for field in required
        }
        self.assertFalse(
            any(
                token in field.lower()
                for field in fields
                for token in ("revenue", "ticket", "screening")
            )
        )
        self.assertEqual(
            set(charts._CHART_TABLES.values()),
            {
                "movie_match_status_donut",
                "release_year_histogram",
                "release_year_match_status_stacked",
                "genre_frequency_bar",
                "director_profile_bar",
                "independent_data_quality_flags",
            },
        )


class VisualizationChartContentTests(unittest.TestCase):
    def test_stacked_chart_densifies_years_chronologically(self) -> None:
        charts = _charts()
        helpers = _helpers_module()
        report = helpers._with_chart(
            helpers._valid_report(),
            "release_year_match_status_stacked",
            rows=(
                (2026, "matched", 21),
                (2024, "not_found", 10),
                (2024, "matched", 71),
            ),
        )

        with _allow_unvalidated(charts):
            result, fig = _call_capturing_figure(
                charts,
                "plot_release_year_match_status",
                report,
                _tmpdir(self) / "stacked.png",
            )

        ax = fig.axes[0]
        self.assertEqual(
            [label.get_text() for label in ax.get_xticklabels()],
            ["2024", "2026"],
        )
        self.assertEqual(
            [round(patch.get_height(), 6) for patch in ax.patches],
            [71.0, 21.0, 10.0, 0.0],
        )
        self.assertEqual(result.plotted_point_count, 3)
        self.assertTrue(
            any("zero for rendering only" in text for text in _figure_texts(fig))
        )

    def test_genre_chart_sorts_by_count_then_token(self) -> None:
        charts = _charts()
        helpers = _helpers_module()
        report = helpers._with_chart(
            helpers._valid_report(),
            "genre_frequency_bar",
            rows=(("Drama", 5), ("Action", 10), ("Comedy", 10)),
        )

        with _allow_unvalidated(charts):
            result, fig = _call_capturing_figure(
                charts,
                "plot_genre_frequency",
                report,
                _tmpdir(self) / "genres.png",
            )

        ax = fig.axes[0]
        labels = [label.get_text() for label in ax.get_yticklabels()]
        self.assertEqual(labels[:3], ["Action", "Comedy", "Drama"])
        self.assertEqual(result.plotted_point_count, 3)
        self.assertTrue(
            any("non-additive" in text for text in _figure_texts(fig))
        )

    def test_director_chart_labels_other_and_missing_directors(self) -> None:
        charts = _charts()
        helpers = _helpers_module()
        report = helpers._with_chart(
            helpers._valid_report(),
            "director_profile_bar",
            exclusions=("3 rows with missing director_raw",),
        )

        result, fig = _call_capturing_figure(
            charts,
            "plot_director_profile",
            report,
            _tmpdir(self) / "directors.png",
        )

        ax = fig.axes[0]
        labels = [label.get_text() for label in ax.get_yticklabels()]
        self.assertTrue(
            any(
                label.startswith("Other (") and "40 directors" in label
                for label in labels
            ),
            labels,
        )
        texts = _figure_texts(fig)
        self.assertTrue(any("40 directors" in text for text in texts))
        self.assertTrue(
            any("missing director_raw" in text for text in texts), texts
        )
        self.assertEqual(result.plotted_point_count, 11)


if __name__ == "__main__":
    unittest.main()
