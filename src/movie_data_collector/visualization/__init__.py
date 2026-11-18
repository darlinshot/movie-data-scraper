"""Initial Python visualization contract over the approved EDA output."""

from __future__ import annotations

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
from .render import (
    VisualizationBatchError,
    VisualizationBatchResult,
    render_all_visualizations,
)
from .validation import (
    VisualizationValidationError,
    VisualizationValidationResult,
    rows_as_dicts,
    validate_visualization_report,
)

__all__ = [
    "ChartResult",
    "VisualizationBatchError",
    "VisualizationBatchResult",
    "VisualizationValidationError",
    "VisualizationValidationResult",
    "plot_bov_comparison_scatter",
    "plot_data_quality_flags",
    "plot_director_profile",
    "plot_dtp_lower_bound_evidence",
    "plot_dtp_revenue_histogram",
    "plot_genre_frequency",
    "plot_movie_match_status",
    "plot_release_year_distribution",
    "plot_release_year_match_status",
    "render_all_visualizations",
    "rows_as_dicts",
    "validate_visualization_report",
]
