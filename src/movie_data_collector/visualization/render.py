"""Batch rendering orchestration for the validated visualization pipeline.

This module builds and validates the EDA report once, then renders the nine
existing charts in a deterministic order. It contains no analytical logic and
delegates every chart to its existing public rendering function.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..analytics.eda import build_eda_report as _build_eda_report
from .charts import (
    ChartResult,
    plot_bov_comparison_scatter,
    plot_data_quality_flags,
    plot_director_profile,
    plot_dtp_lower_bound_evidence,
    plot_dtp_revenue_histogram,
    plot_genre_frequency,
    plot_movie_match_status,
    plot_release_year_distribution,
    plot_release_year_match_status,
)
from .validation import validate_visualization_report


@dataclass(frozen=True)
class VisualizationBatchResult:
    """Immutable receipt describing one completed visualization batch."""

    output_dir: Path
    chart_results: tuple[ChartResult, ...]
    chart_count: int
    validation_status: str
    movie_count: int


class VisualizationBatchError(RuntimeError):
    """Descriptive failure raised by visualization batch orchestration."""

    def __init__(
        self,
        message: str,
        *,
        chart_name: str | None = None,
        output_path: str | Path | None = None,
    ) -> None:
        super().__init__(message)
        self._chart_name = chart_name
        self._output_path = Path(output_path) if output_path is not None else None

    @property
    def chart_name(self) -> str | None:
        """Chart whose rendering failed, when applicable."""
        return self._chart_name

    @property
    def output_path(self) -> Path | None:
        """Intended output path of the failed chart, when applicable."""
        return self._output_path


ChartRenderer = Callable[[Any, Path], ChartResult]

_CHART_SPECS: tuple[tuple[str, str, str], ...] = (
    (
        "movie_match_status",
        "01_movie_match_status.png",
        "plot_movie_match_status",
    ),
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
    (
        "genre_frequency",
        "04_genre_frequency.png",
        "plot_genre_frequency",
    ),
    (
        "director_profile",
        "05_director_profile.png",
        "plot_director_profile",
    ),
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

_EXPECTED_CHART_COUNT = len(_CHART_SPECS)


def render_all_visualizations(
    output_dir: str | Path = "reports/visualizations",
    report: Any | None = None,
) -> VisualizationBatchResult:
    """Build, validate and render all nine charts into ``output_dir``."""
    if report is None:
        report = _build_eda_report()

    validation = validate_visualization_report(report)

    destination = Path(output_dir)
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise VisualizationBatchError(
            f"could not create visualization output directory {destination!s}: {exc}"
        ) from exc

    results: list[ChartResult] = []
    for chart_name, filename, renderer_name in _CHART_SPECS:
        renderer: ChartRenderer = globals()[renderer_name]
        target = destination / filename
        try:
            result = renderer(report, target)
        except Exception as exc:
            raise VisualizationBatchError(
                f"failed to render chart {chart_name!r} to {target!s}: {exc}",
                chart_name=chart_name,
                output_path=target,
            ) from exc
        results.append(result)

    chart_results = tuple(results)
    if len(chart_results) != _EXPECTED_CHART_COUNT:
        raise VisualizationBatchError(
            f"expected {_EXPECTED_CHART_COUNT} chart results, got {len(chart_results)}"
        )

    return VisualizationBatchResult(
        output_dir=destination,
        chart_results=chart_results,
        chart_count=len(chart_results),
        validation_status=str(validation.validation_status),
        movie_count=int(validation.validated_movie_count),
    )


__all__ = [
    "VisualizationBatchError",
    "VisualizationBatchResult",
    "render_all_visualizations",
]
