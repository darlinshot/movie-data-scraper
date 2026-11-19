"""Focused tests for visualization batch rendering orchestration."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import shutil
import sys
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
PACKAGE_PATH = SRC_PATH / "movie_data_collector"
RENDER_PATH = (
    PACKAGE_PATH / "visualization" / "render.py"
)

_HELPERS: Any = None
_RENDER: Any = None

EXPECTED_SPECS: tuple[tuple[str, str, str], ...] = (
    ("movie_match_status", "01_movie_match_status.png", "plot_movie_match_status"),
    (
        "release_year_distribution",
        "02_release_year_distribution.png",
        "plot_release_year_distribution",
    ),
    (
        "release_year_match_status",
        "03_release_year_match_status.png",
        "plot_release_year_match_status",
    ),
    ("genre_frequency", "04_genre_frequency.png", "plot_genre_frequency"),
    ("director_profile", "05_director_profile.png", "plot_director_profile"),
    (
        "data_quality_flags",
        "06_data_quality_flags.png",
        "plot_data_quality_flags",
    ),
    (
        "dtp_revenue_histogram",
        "07_dtp_revenue_histogram.png",
        "plot_dtp_revenue_histogram",
    ),
    (
        "dtp_lower_bound_evidence",
        "08_dtp_lower_bound_evidence.png",
        "plot_dtp_lower_bound_evidence",
    ),
    (
        "bov_comparison_scatter",
        "09_bov_comparison_scatter.png",
        "plot_bov_comparison_scatter",
    ),
)
EXPECTED_FILENAMES: tuple[str, ...] = tuple(
    filename for _chart_name, filename, _function in EXPECTED_SPECS
)


def _load_module_from_path(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _eda_helpers() -> Any:
    global _HELPERS
    if _HELPERS is None:
        _HELPERS = _load_module_from_path(
            "_render_orchestration_eda_helpers",
            Path(__file__).with_name("test_analytics_visualization.py"),
        )
    return _HELPERS


def _load_render_module() -> Any:
    with mock.patch.dict(sys.modules), mock.patch.object(
        sys, "path", [str(SRC_PATH), *sys.path]
    ):
        for name in (
            "movie_data_collector",
            "movie_data_collector.analytics",
            "movie_data_collector.analytics.eda",
            "movie_data_collector.visualization",
            "movie_data_collector.visualization.charts",
            "movie_data_collector.visualization.render",
            "movie_data_collector.visualization.validation",
        ):
            sys.modules.pop(name, None)

        package = ModuleType("movie_data_collector")
        package.__path__ = [str(PACKAGE_PATH)]
        sys.modules["movie_data_collector"] = package

        return importlib.import_module("movie_data_collector.visualization.render")


def _render() -> Any:
    global _RENDER
    if _RENDER is None:
        _RENDER = _load_render_module()
    return _RENDER


def _tmpdir(test: unittest.TestCase) -> Path:
    path = Path(tempfile.mkdtemp(prefix="movie-viz-render-"))
    test.addCleanup(shutil.rmtree, path, ignore_errors=True)
    return path


def _validation_result() -> SimpleNamespace:
    return SimpleNamespace(validation_status="validated", validated_movie_count=92)


def _chart_result(
    render: Any, chart_name: str, output_path: Path, index: int
) -> Any:
    return render.ChartResult(
        output_path=output_path,
        chart_name=chart_name,
        plotted_point_count=index + 1,
    )


@contextmanager
def _patched_charts(
    render: Any,
    output_dir: Path,
    *,
    results: dict[str, Any] | None = None,
    failures: dict[str, BaseException] | None = None,
) -> Iterator[tuple[Any, dict[str, Any]]]:
    manager = mock.Mock()
    chart_mocks: dict[str, Any] = {}
    failures = failures or {}
    results = results or {}

    with ExitStack() as stack:
        for index, (chart_name, filename, function_name) in enumerate(EXPECTED_SPECS):
            target = output_dir / filename
            if chart_name in failures:
                chart_mock = mock.Mock(
                    name=function_name, side_effect=failures[chart_name]
                )
            else:
                chart_mock = mock.Mock(
                    name=function_name,
                    return_value=results.get(chart_name)
                    or _chart_result(render, chart_name, target, index),
                )
            manager.attach_mock(chart_mock, function_name)
            chart_mocks[function_name] = chart_mock
            stack.enter_context(mock.patch.object(render, function_name, chart_mock))
        yield manager, chart_mocks


def _expected_calls(
    manager: Any,
    report: Any,
    output_dir: Path,
    *,
    through: int | None = None,
) -> list[Any]:
    specs = EXPECTED_SPECS if through is None else EXPECTED_SPECS[:through]
    return [
        getattr(mock.call, function_name)(report, output_dir / filename)
        for _chart_name, filename, function_name in specs
    ]


class VisualizationRenderFlowTests(unittest.TestCase):
    def test_builds_report_once_and_validates_before_rendering(self) -> None:
        render = _render()
        output_dir = _tmpdir(self) / "batch"
        report = _eda_helpers()._valid_report()
        validation = _validation_result()
        build = mock.Mock(name="_build_eda_report", return_value=report)
        validate = mock.Mock(name="validate_visualization_report", return_value=validation)

        with mock.patch.object(render, "_build_eda_report", build), mock.patch.object(
            render, "validate_visualization_report", validate
        ), _patched_charts(render, output_dir) as (manager, _chart_mocks):
            manager.attach_mock(build, "_build_eda_report")
            manager.attach_mock(validate, "validate_visualization_report")
            result = render.render_all_visualizations(output_dir)

        build.assert_called_once_with()
        validate.assert_called_once_with(report)
        self.assertEqual(
            manager.mock_calls,
            [
                mock.call._build_eda_report(),
                mock.call.validate_visualization_report(report),
                *_expected_calls(manager, report, output_dir),
            ],
        )
        self.assertEqual(result.output_dir, output_dir)
        self.assertEqual(result.validation_status, "validated")
        self.assertEqual(result.movie_count, 92)

    def test_supplied_report_prevents_rebuild(self) -> None:
        render = _render()
        output_dir = _tmpdir(self) / "supplied"
        report = _eda_helpers()._valid_report()
        build = mock.Mock(name="_build_eda_report", side_effect=AssertionError("rebuilt"))
        validate = mock.Mock(
            name="validate_visualization_report", return_value=_validation_result()
        )

        with mock.patch.object(render, "_build_eda_report", build), mock.patch.object(
            render, "validate_visualization_report", validate
        ), _patched_charts(render, output_dir) as (manager, _chart_mocks):
            result = render.render_all_visualizations(output_dir, report=report)

        build.assert_not_called()
        validate.assert_called_once_with(report)
        self.assertEqual(manager.mock_calls, _expected_calls(manager, report, output_dir))
        self.assertEqual(result.output_dir, output_dir)

    def test_exact_chart_results_and_metadata_are_preserved(self) -> None:
        render = _render()
        output_dir = _tmpdir(self) / "results"
        report = _eda_helpers()._valid_report()
        expected_results = {
            chart_name: render.ChartResult(
                output_path=output_dir / filename,
                chart_name=chart_name,
                plotted_point_count=index + 1,
            )
            for index, (chart_name, filename, _function) in enumerate(EXPECTED_SPECS)
        }

        with mock.patch.object(
            render,
            "validate_visualization_report",
            return_value=_validation_result(),
        ), _patched_charts(render, output_dir, results=expected_results):
            result = render.render_all_visualizations(output_dir, report=report)

        self.assertIsInstance(result.chart_results, tuple)
        self.assertEqual(len(result.chart_results), 9)
        self.assertEqual(result.chart_count, 9)
        for actual, chart_name in zip(
            result.chart_results, (spec[0] for spec in EXPECTED_SPECS)
        ):
            self.assertIs(actual, expected_results[chart_name])
        self.assertEqual(result.validation_status, "validated")
        self.assertEqual(result.movie_count, 92)

    def test_first_chart_failure_stops_all_later_charts(self) -> None:
        render = _render()
        output_dir = _tmpdir(self) / "first_failure"
        report = _eda_helpers()._valid_report()
        original = RuntimeError("first chart failed")

        with mock.patch.object(
            render,
            "validate_visualization_report",
            return_value=_validation_result(),
        ), _patched_charts(
            render,
            output_dir,
            failures={EXPECTED_SPECS[0][0]: original},
        ) as (manager, chart_mocks):
            with self.assertRaises(render.VisualizationBatchError) as caught:
                render.render_all_visualizations(output_dir, report=report)

        error = caught.exception
        self.assertEqual(error.chart_name, EXPECTED_SPECS[0][0])
        self.assertEqual(error.output_path, output_dir / EXPECTED_SPECS[0][1])
        self.assertIn(EXPECTED_SPECS[0][0], str(error))
        self.assertIn(str(output_dir / EXPECTED_SPECS[0][1]), str(error))
        self.assertIs(error.__cause__, original)
        chart_mocks[EXPECTED_SPECS[0][2]].assert_called_once()
        for _chart_name, _filename, function_name in EXPECTED_SPECS[1:]:
            chart_mocks[function_name].assert_not_called()
        self.assertEqual(len(manager.mock_calls), 1)

    def test_chart_failure_preserves_earlier_outputs(self) -> None:
        render = _render()
        output_dir = _tmpdir(self) / "later_failure"
        output_dir.mkdir(parents=True)
        report = _eda_helpers()._valid_report()
        original = RuntimeError("fifth chart failed")
        sentinel = b"earlier chart output"

        for _chart_name, filename, _function in EXPECTED_SPECS[:4]:
            (output_dir / filename).write_bytes(sentinel)

        with mock.patch.object(
            render,
            "validate_visualization_report",
            return_value=_validation_result(),
        ), _patched_charts(
            render,
            output_dir,
            failures={EXPECTED_SPECS[4][0]: original},
        ) as (_manager, chart_mocks):
            with self.assertRaises(render.VisualizationBatchError) as caught:
                render.render_all_visualizations(output_dir, report=report)

        self.assertIs(caught.exception.__cause__, original)
        self.assertEqual(caught.exception.chart_name, EXPECTED_SPECS[4][0])
        for _chart_name, filename, function_name in EXPECTED_SPECS[:4]:
            chart_mocks[function_name].assert_called_once()
            self.assertEqual((output_dir / filename).read_bytes(), sentinel)
        chart_mocks[EXPECTED_SPECS[4][2]].assert_called_once()
        for _chart_name, _filename, function_name in EXPECTED_SPECS[5:]:
            chart_mocks[function_name].assert_not_called()

    def test_validation_failure_prevents_output_directory_creation(self) -> None:
        render = _render()
        output_dir = _tmpdir(self) / "validated_blocked"
        report = _eda_helpers()._valid_report()
        original = ValueError("validation blocked")

        with mock.patch.object(
            render,
            "validate_visualization_report",
            side_effect=original,
        ), _patched_charts(render, output_dir) as (_manager, chart_mocks):
            with self.assertRaises(ValueError) as caught:
                render.render_all_visualizations(output_dir, report=report)

        self.assertIs(caught.exception, original)
        self.assertFalse(output_dir.exists())
        for chart_mock in chart_mocks.values():
            chart_mock.assert_not_called()

    def test_output_directory_creation_failure_is_wrapped(self) -> None:
        render = _render()
        output_dir = _tmpdir(self) / "cannot_create"
        report = _eda_helpers()._valid_report()
        original = OSError("permission denied")

        with mock.patch.object(
            render,
            "validate_visualization_report",
            return_value=_validation_result(),
        ), mock.patch.object(Path, "mkdir", side_effect=original), _patched_charts(
            render, output_dir
        ) as (_manager, chart_mocks):
            with self.assertRaises(render.VisualizationBatchError) as caught:
                render.render_all_visualizations(output_dir, report=report)

        error = caught.exception
        self.assertIn("could not create visualization output directory", str(error))
        self.assertIn(str(output_dir), str(error))
        self.assertIs(error.__cause__, original)
        for chart_mock in chart_mocks.values():
            chart_mock.assert_not_called()

    def test_unrelated_output_files_are_untouched(self) -> None:
        render = _render()
        output_dir = _tmpdir(self) / "existing_files"
        output_dir.mkdir(parents=True)
        unrelated = output_dir / "notes.txt"
        unrelated.write_text("keep me", encoding="utf-8")
        report = _eda_helpers()._valid_report()

        with mock.patch.object(
            render,
            "validate_visualization_report",
            return_value=_validation_result(),
        ), _patched_charts(render, output_dir):
            render.render_all_visualizations(output_dir, report=report)

        self.assertTrue(unrelated.is_file())
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep me")

    def test_supplied_report_is_not_mutated(self) -> None:
        render = _render()
        output_dir = _tmpdir(self) / "immutable"
        helpers = _eda_helpers()
        report = helpers._valid_report()
        before = helpers._snapshot_report(report)

        with mock.patch.object(
            render,
            "validate_visualization_report",
            return_value=_validation_result(),
        ), _patched_charts(render, output_dir):
            render.render_all_visualizations(output_dir, report=report)

        self.assertEqual(helpers._snapshot_report(report), before)

    def test_source_has_no_direct_io_or_forbidden_imports(self) -> None:
        render = _render()
        tree = ast.parse(RENDER_PATH.read_text(encoding="utf-8"))
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
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                strings.append(node.value)

        self.assertFalse(
            imported
            & {"pandas", "numpy", "matplotlib", "seaborn", "plotly", "csv", "json"}
        )
        self.assertFalse(called & {"open", "read_csv", "load_eda_dataset"})
        self.assertIn("_build_eda_report", called)
        joined = "\n".join(strings)
        for token in (".csv", ".jsonl", ".json", ".html", ".pdf", ".svg", "analytics_movie_id_map"):
            self.assertNotIn(token, joined)
        self.assertEqual(
            inspect.signature(render.render_all_visualizations).parameters[
                "output_dir"
            ].default,
            "reports/visualizations",
        )
        self.assertEqual(
            tuple((name, filename) for name, filename, _func in render._CHART_SPECS),
            tuple((name, filename) for name, filename, _func in EXPECTED_SPECS),
        )
        self.assertEqual(
            tuple(function for _name, _filename, function in render._CHART_SPECS),
            tuple(function for _name, _filename, function in EXPECTED_SPECS),
        )


class VisualizationRenderIntegrationTests(unittest.TestCase):
    def test_real_data_batch_renders_nine_valid_pngs(self) -> None:
        render = _render()
        output_dir = _tmpdir(self) / "real_batch"
        output_dir.mkdir(parents=True)
        unrelated = output_dir / "keep.txt"
        unrelated.write_bytes(b"unrelated")

        result = render.render_all_visualizations(output_dir)

        self.assertEqual(result.output_dir, output_dir)
        self.assertEqual(result.validation_status, "validated")
        self.assertEqual(result.movie_count, 92)
        self.assertEqual(result.chart_count, 9)
        self.assertEqual(len(result.chart_results), 9)
        self.assertTrue(
            all(isinstance(item, render.ChartResult) for item in result.chart_results)
        )
        self.assertEqual(
            tuple(item.chart_name for item in result.chart_results),
            tuple(chart_name for chart_name, _filename, _func in EXPECTED_SPECS),
        )
        self.assertEqual(
            tuple(item.output_path.name for item in result.chart_results),
            EXPECTED_FILENAMES,
        )

        produced = tuple(sorted(path.name for path in output_dir.glob("*.png")))
        self.assertEqual(produced, tuple(sorted(EXPECTED_FILENAMES)))
        for filename in EXPECTED_FILENAMES:
            path = output_dir / filename
            payload = path.read_bytes()
            self.assertTrue(payload)
            self.assertEqual(payload[:8], b"\x89PNG\r\n\x1a\n")

        self.assertEqual(unrelated.read_bytes(), b"unrelated")


if __name__ == "__main__":
    unittest.main()
