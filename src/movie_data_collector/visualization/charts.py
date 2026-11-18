"""Matplotlib charts built from validated EDA chart-ready tables.

EDA owns every analytical rule. This module only renders tables that have
already passed :func:`validate_visualization_report`; it never reads source
files, rebuilds the report, imports dataframe libraries or calculates revenue.
Matplotlib is imported lazily so importing the visualization contract remains
free of plotting dependencies until a chart is actually requested.
"""

from __future__ import annotations

import math
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable

from .validation import (
    ACCEPTED_HIGH_PRIORITY_IDS,
    CANDIDATE_MOVIE_ID,
    EXPECTED_DTP_ROUNDED_ROWS,
    EXPECTED_SCATTER_ROWS,
    GAP_REFERENCE_PCT,
    LOWER_BOUND_IDS,
    QUARANTINED_MOVIE_ID,
    REVENUE_WARNING_LABEL,
    VisualizationValidationError,
    rows_as_dicts,
    validate_visualization_report,
)


@dataclass(frozen=True)
class ChartResult:
    """Immutable rendering receipt returned by every chart function."""

    output_path: Path
    chart_name: str
    plotted_point_count: int


_CHART_TABLES: MappingProxyType[str, str] = MappingProxyType(
    {
        "movie_match_status": "movie_match_status_donut",
        "release_year_distribution": "release_year_histogram",
        "release_year_match_status": "release_year_match_status_stacked",
        "genre_frequency": "genre_frequency_bar",
        "director_profile": "director_profile_bar",
        "data_quality_flags": "independent_data_quality_flags",
    }
)

_REQUIRED_FIELDS: MappingProxyType[str, tuple[str, ...]] = MappingProxyType(
    {
        "movie_match_status": ("bov_match_status", "movie_count"),
        "release_year_distribution": ("release_year", "movie_count"),
        "release_year_match_status": (
            "release_year",
            "bov_match_status",
            "movie_count",
        ),
        "genre_frequency": ("genre_token", "movie_count"),
        "director_profile": (
            "director_raw",
            "director_norm_key",
            "director_count",
        ),
        "data_quality_flags": (
            "flag",
            "flag_label",
            "true_count",
            "false_count",
            "missing_count",
        ),
    }
)

_REVENUE_TABLE_SPECS: MappingProxyType[
    str, tuple[str, str, tuple[str, ...]]
] = MappingProxyType(
    {
        "dtp_revenue_histogram": (
            "chart_data",
            "dtp_revenue_histogram",
            ("revenue_bin_vnd", "movie_count"),
        ),
        "dtp_lower_bound_evidence": (
            "tables",
            "lower_bound_revenue_table",
            (
                "movie_id",
                "canonical_title",
                "dtp_revenue_raw",
                "dtp_revenue_vnd",
                "dtp_revenue_quality",
                "display_value",
                "include_revenue_eda",
            ),
        ),
        "bov_comparison_scatter": (
            "chart_data",
            "bov_comparison_scatter",
            (
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
            ),
        ),
    }
)

_KNOWN_STATUS_COLORS: MappingProxyType[str, str] = MappingProxyType(
    {
        "matched": "#2f7d63",
        "needs_review": "#d9a441",
        "not_found": "#b2504a",
    }
)
_FALLBACK_STATUS_COLORS: tuple[str, ...] = (
    "#5b7f9e",
    "#8c6ca3",
    "#7a8b6f",
    "#a8755a",
    "#6f8fa6",
)
_PRIMARY_COLOR = "#3f6f8f"
_OTHER_COLOR = "#9aa4ad"
_NOTE_COLOR = "#57606a"
_WARNING_COLOR = "#8a3b12"
_WARNING_BACKGROUND = "#fff4e5"
_WARNING_BORDER = "#d9a441"
_HIGH_PRIORITY_COLOR = "#b2504a"
_HIGH_PRIORITY_EDGE = "#24292f"
_REFERENCE_BAND_COLOR = "#d9a441"

_SCATTER_EXCLUDED_IDS: tuple[str, ...] = (
    *LOWER_BOUND_IDS,
    QUARANTINED_MOVIE_ID,
    CANDIDATE_MOVIE_ID,
)

_TOP_DIRECTOR_COUNT = 10
_DPI = 150

_STYLE: MappingProxyType[str, Any] = MappingProxyType(
    {
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#d0d7de",
        "axes.labelcolor": "#24292f",
        "axes.titlecolor": "#24292f",
        "text.color": "#24292f",
        "xtick.color": "#57606a",
        "ytick.color": "#57606a",
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": "#e6eaf0",
        "grid.linestyle": "-",
        "grid.linewidth": 0.8,
        "font.size": 10,
        "axes.titlesize": 14,
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)

_MISSING = object()
_mpl: Any = None
_plt: Any = None

Record = dict[str, Any]
Builder = Callable[[Any, Any, Any, tuple[Record, ...]], int]
Preparer = Callable[[Any, str], tuple[Any, tuple[Record, ...]]]


def _matplotlib_modules() -> tuple[Any, Any]:
    """Import the plotting modules only when a chart is requested."""
    global _mpl, _plt
    if _plt is None:
        import matplotlib as mpl
        import matplotlib.pyplot as plt

        _mpl = mpl
        _plt = plt
    return _mpl, _plt


def _prepare(report: Any, chart_name: str) -> tuple[Any, tuple[Record, ...]]:
    """Validate the report and adapt exactly one chart-ready EDA table."""
    validate_visualization_report(report)

    chart_data = getattr(report, "chart_data", None)
    if chart_data is None:
        raise VisualizationValidationError("report field 'chart_data': missing")

    table_name = _CHART_TABLES[chart_name]
    if table_name not in chart_data:
        raise VisualizationValidationError(
            f"report field 'chart_data': missing required table {table_name!r}"
        )
    table = chart_data[table_name]
    records = rows_as_dicts(table)

    if not records:
        raise VisualizationValidationError(
            f"table {table_name!r}: expected at least one row for chart "
            f"{chart_name!r}, got 0"
        )

    for field in _REQUIRED_FIELDS[chart_name]:
        for index, record in enumerate(records):
            if field not in record:
                raise VisualizationValidationError(
                    f"table {table_name!r} row {index}: missing required field "
                    f"{field!r} for chart {chart_name!r}"
                )
    return table, records


def _prepare_revenue_table(
    report: Any, chart_name: str
) -> tuple[Any, tuple[Record, ...]]:
    """Validate the report and adapt one designated revenue evidence table."""
    validate_visualization_report(report)

    group_name, table_name, required_fields = _REVENUE_TABLE_SPECS[chart_name]
    group = getattr(report, group_name, None)
    if group is None:
        raise VisualizationValidationError(
            f"report field {group_name!r}: missing"
        )
    if table_name not in group:
        raise VisualizationValidationError(
            f"report field {group_name!r}: missing required table {table_name!r}"
        )

    table = group[table_name]
    records = rows_as_dicts(table)
    if not records:
        raise VisualizationValidationError(
            f"table {table_name!r}: expected at least one row for chart "
            f"{chart_name!r}, got 0"
        )

    for field in required_fields:
        for index, record in enumerate(records):
            if field not in record:
                raise VisualizationValidationError(
                    f"table {table_name!r} row {index}: missing required field "
                    f"{field!r} for chart {chart_name!r}"
                )
    return table, records


def _text_value(
    records: tuple[Record, ...], field: str, table_name: str
) -> list[str]:
    values: list[str] = []
    for index, record in enumerate(records):
        value = record.get(field, _MISSING)
        if not isinstance(value, str) or not value.strip():
            raise VisualizationValidationError(
                f"table {table_name!r} row {index} field {field!r}: expected a "
                f"non-empty string, got {value!r}"
            )
        values.append(value)
    return values


def _count_value(
    records: tuple[Record, ...], field: str, table_name: str
) -> list[int]:
    values: list[int] = []
    for index, record in enumerate(records):
        value = record.get(field, _MISSING)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise VisualizationValidationError(
                f"table {table_name!r} row {index} field {field!r}: expected a "
                f"non-negative integer, got {value!r}"
            )
        values.append(value)
    return values


def _positive_coordinate_value(
    records: tuple[Record, ...], field: str, table_name: str
) -> list[float]:
    values: list[float] = []
    for index, record in enumerate(records):
        value = record.get(field, _MISSING)
        candidate = float("nan")
        if not isinstance(value, bool) and isinstance(value, Real):
            candidate = float(value)
        if not math.isfinite(candidate) or candidate <= 0.0:
            raise VisualizationValidationError(
                f"table {table_name!r} row {index} field {field!r}: expected a "
                f"finite positive revenue coordinate, got {value!r}"
            )
        values.append(candidate)
    return values


def _gap_reference_pct(table: Any, table_name: str) -> float:
    metadata = getattr(table, "metadata", None)
    if not isinstance(metadata, MappingABC):
        raise VisualizationValidationError(
            f"table {table_name!r} metadata: expected a mapping, "
            f"got {type(metadata).__name__}"
        )
    value = metadata.get("gap_reference_pct", _MISSING)
    candidate = float("nan")
    if not isinstance(value, bool) and isinstance(value, Real):
        candidate = float(value)
    if not math.isfinite(candidate) or candidate <= 0.0:
        raise VisualizationValidationError(
            f"table {table_name!r} metadata field 'gap_reference_pct': expected "
            f"a finite positive number, got {value!r}"
        )
    if candidate != float(GAP_REFERENCE_PCT):
        raise VisualizationValidationError(
            f"table {table_name!r} metadata field 'gap_reference_pct': expected "
            f"{GAP_REFERENCE_PCT!r}, got {value!r}"
        )
    return candidate


def _prepare_bov_scatter(
    report: Any, chart_name: str
) -> tuple[Any, tuple[Record, ...]]:
    """Validate the EDA scatter population before any figure is created."""
    if chart_name != "bov_comparison_scatter":
        raise VisualizationValidationError(
            f"chart {chart_name!r}: unsupported scatter preparer target"
        )
    table, records = _prepare_revenue_table(report, "bov_comparison_scatter")
    table_name = _REVENUE_TABLE_SPECS["bov_comparison_scatter"][1]

    if len(records) != EXPECTED_SCATTER_ROWS:
        raise VisualizationValidationError(
            f"table {table_name!r} row count: expected {EXPECTED_SCATTER_ROWS} "
            f"comparison rows, got {len(records)}"
        )

    movie_ids = _text_value(records, "movie_id", table_name)
    found_exclusions = tuple(
        movie_id
        for movie_id in dict.fromkeys(movie_ids)
        if movie_id in _SCATTER_EXCLUDED_IDS
    )
    if found_exclusions:
        raise VisualizationValidationError(
            f"table {table_name!r} field 'movie_id': excluded IDs "
            f"{_SCATTER_EXCLUDED_IDS!r} must not appear; found {found_exclusions!r}"
        )

    for movie_id in ACCEPTED_HIGH_PRIORITY_IDS:
        matches = tuple(
            record for record in records if record["movie_id"] == movie_id
        )
        if len(matches) != 1:
            raise VisualizationValidationError(
                f"table {table_name!r} field 'movie_id': expected exactly one "
                f"retained row for high-priority {movie_id!r}, got {len(matches)}"
            )
        if matches[0]["review_priority"] != "high":
            raise VisualizationValidationError(
                f"table {table_name!r} row with movie_id {movie_id!r} field "
                f"'review_priority': expected 'high', "
                f"got {matches[0]['review_priority']!r}"
            )

    _positive_coordinate_value(records, "dtp_revenue_vnd", table_name)
    _positive_coordinate_value(records, "bov_revenue_vnd", table_name)
    _gap_reference_pct(table, table_name)
    return table, records


def _year_value(
    records: tuple[Record, ...], field: str, table_name: str
) -> list[int | str]:
    values: list[int | str] = []
    for index, record in enumerate(records):
        value = record.get(field, _MISSING)
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise VisualizationValidationError(
                f"table {table_name!r} row {index} field {field!r}: expected an "
                f"integer year or year label, got {value!r}"
            )
        if isinstance(value, str) and not value.strip():
            raise VisualizationValidationError(
                f"table {table_name!r} row {index} field {field!r}: expected a "
                "non-empty year label"
            )
        values.append(value)
    return values


def _year_sort_key(value: int | str) -> tuple[int, int | str]:
    if isinstance(value, int):
        return (0, value)
    return (1, value)


def _status_order(statuses: list[str]) -> list[str]:
    present = list(dict.fromkeys(statuses))
    ordered = [status for status in _KNOWN_STATUS_COLORS if status in present]
    ordered.extend(sorted(status for status in present if status not in ordered))
    return ordered


def _status_colors(statuses: list[str]) -> dict[str, str]:
    colors = dict(_KNOWN_STATUS_COLORS)
    unknown = sorted(status for status in statuses if status not in colors)
    for index, status in enumerate(unknown):
        colors[status] = _FALLBACK_STATUS_COLORS[
            index % len(_FALLBACK_STATUS_COLORS)
        ]
    return {status: colors[status] for status in statuses}


def _status_label(status: str) -> str:
    return status.replace("_", " ").strip().title()


def _subtitle(ax: Any, text: str) -> None:
    ax.text(
        0.0,
        1.015,
        text,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=9,
        color=_NOTE_COLOR,
    )


def _figure_note(fig: Any, text: str) -> None:
    fig.text(
        0.01,
        0.015,
        text,
        ha="left",
        va="bottom",
        fontsize=9,
        color=_NOTE_COLOR,
    )


def _revenue_warning(fig: Any) -> None:
    """Display the authoritative revenue-scope warning prominently."""
    fig.text(
        0.5,
        0.975,
        REVENUE_WARNING_LABEL,
        ha="center",
        va="top",
        fontsize=10,
        fontweight="bold",
        color=_WARNING_COLOR,
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": _WARNING_BACKGROUND,
            "edgecolor": _WARNING_BORDER,
            "linewidth": 1.0,
        },
    )


def _missing_director_note(table: Any) -> str:
    exclusions = getattr(table, "exclusions", ()) or ()
    missing = tuple(
        str(item)
        for item in exclusions
        if "missing" in str(item).lower() and "director" in str(item).lower()
    )
    if missing:
        return "EDA exclusion for missing directors: " + "; ".join(missing)
    return "EDA exclusion for missing directors: not reported in table metadata."


def _autopct(total: int) -> Callable[[float], str]:
    def format_percent(percent: float) -> str:
        count = int(round(percent * total / 100.0))
        return f"{percent:.1f}%\n({count})"

    return format_percent


def _save_figure(
    fig: Any, output_path: str | Path, chart_name: str, point_count: int
) -> ChartResult:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=_DPI, format="png", bbox_inches="tight")
    return ChartResult(
        output_path=path,
        chart_name=chart_name,
        plotted_point_count=int(point_count),
    )


def _render(
    chart_name: str,
    report: Any,
    output_path: str | Path,
    builder: Builder,
    figsize: tuple[float, float] = (10, 6),
    preparer: Preparer = _prepare,
    layout_rect: tuple[float, float, float, float] = (0, 0.10, 1, 1),
) -> ChartResult:
    table, records = preparer(report, chart_name)
    mpl, plt = _matplotlib_modules()
    fig: Any = None
    try:
        with mpl.rc_context(_STYLE):
            fig, ax = plt.subplots(figsize=figsize)
            point_count = builder(fig, ax, table, records)
            fig.tight_layout(rect=layout_rect)
            return _save_figure(fig, output_path, chart_name, point_count)
    finally:
        if fig is not None:
            plt.close(fig)


def _build_movie_match_status(
    fig: Any, ax: Any, table: Any, records: tuple[Record, ...]
) -> int:
    del fig
    table_name = _CHART_TABLES["movie_match_status"]
    statuses = _text_value(records, "bov_match_status", table_name)
    counts = _count_value(records, "movie_count", table_name)
    total = sum(counts)

    colors = [
        _status_colors(statuses)[status] for status in statuses
    ]
    labels = [_status_label(status) for status in statuses]
    wedges, _texts, _autotexts = ax.pie(
        counts,
        labels=labels,
        colors=colors,
        autopct=_autopct(total),
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.38, "edgecolor": "white", "linewidth": 1.0},
        textprops={"fontsize": 10},
    )
    del wedges
    ax.text(
        0.0,
        0.0,
        f"Total\n{total}",
        ha="center",
        va="center",
        fontsize=12,
        fontweight="bold",
    )
    ax.set_title(
        "Movie match status distribution",
        loc="left",
        fontsize=14,
        fontweight="bold",
        pad=28,
    )
    _subtitle(
        ax,
        "Diagnostic matcher status only; not a data-quality or correctness score.",
    )
    ax.axis("equal")
    ax.grid(False)
    return len(records)


def _build_release_year_distribution(
    fig: Any, ax: Any, table: Any, records: tuple[Record, ...]
) -> int:
    del fig, table
    table_name = _CHART_TABLES["release_year_distribution"]
    raw_years = _year_value(records, "release_year", table_name)
    counts = _count_value(records, "movie_count", table_name)
    paired = sorted(
        zip(raw_years, counts), key=lambda item: _year_sort_key(item[0])
    )
    years = [year for year, _count in paired]
    if len({str(year) for year in years}) != len(years):
        raise VisualizationValidationError(
            f"table {table_name!r} field 'release_year': duplicate year labels "
            "cannot be rendered as a count bar chart"
        )
    ordered_counts = [count for _year, count in paired]
    x_positions = list(range(len(years)))

    bars = ax.bar(x_positions, ordered_counts, color=_PRIMARY_COLOR, width=0.68)
    ax.bar_label(bars, padding=3, fontsize=9)
    ax.set_xticks(x_positions, [str(year) for year in years])
    ax.tick_params(axis="x", labelrotation=45 if len(years) > 8 else 0)
    ax.set_xlabel("Release year")
    ax.set_ylabel("Movie count")
    ax.set_ylim(0, max(ordered_counts) * 1.15 if ordered_counts else 1)
    ax.set_title("Movies by release year", loc="left", pad=28)
    _subtitle(ax, "Descriptive counts only; no revenue, trend or performance inference.")
    return len(records)


def _build_release_year_match_status(
    fig: Any, ax: Any, table: Any, records: tuple[Record, ...]
) -> int:
    del fig, table
    table_name = _CHART_TABLES["release_year_match_status"]
    raw_years = _year_value(records, "release_year", table_name)
    statuses = _text_value(records, "bov_match_status", table_name)
    counts = _count_value(records, "movie_count", table_name)

    matrix: dict[tuple[int | str, str], int] = {}
    for index, (year, status, count) in enumerate(zip(raw_years, statuses, counts)):
        key = (year, status)
        if key in matrix:
            raise VisualizationValidationError(
                f"table {table_name!r} row {index}: duplicate release_year / "
                f"bov_match_status combination {key!r}"
            )
        matrix[key] = count

    years = sorted(set(raw_years), key=_year_sort_key)
    ordered_statuses = _status_order(statuses)
    colors = _status_colors(ordered_statuses)
    x_positions = list(range(len(years)))
    bottom = [0] * len(years)

    for status in ordered_statuses:
        # Zero-filled series are presentation scaffolding only; matrix remains untouched.
        series = [matrix.get((year, status), 0) for year in years]
        bars = ax.bar(
            x_positions,
            series,
            bottom=bottom,
            color=colors[status],
            label=_status_label(status),
            edgecolor="white",
            linewidth=0.6,
            width=0.68,
        )
        del bars
        bottom = [current + value for current, value in zip(bottom, series)]

    ax.set_xticks(x_positions, [str(year) for year in years])
    ax.tick_params(axis="x", labelrotation=45 if len(years) > 8 else 0)
    ax.set_xlabel("Release year")
    ax.set_ylabel("Movie count")
    ax.legend(title="Match status", loc="upper right", frameon=False)
    ax.set_title("Release year by match status", loc="left", pad=28)
    _subtitle(
        ax,
        "Year-only diagnostic counts; missing year/status cells are zero for rendering only. "
        "No revenue trend is represented.",
    )
    return len(records)


def _build_genre_frequency(
    fig: Any, ax: Any, table: Any, records: tuple[Record, ...]
) -> int:
    table_name = _CHART_TABLES["genre_frequency"]
    genres = _text_value(records, "genre_token", table_name)
    counts = _count_value(records, "movie_count", table_name)
    paired = sorted(
        zip(genres, counts), key=lambda item: (-item[1], item[0])
    )

    bars = ax.barh(
        [genre for genre, _count in paired],
        [count for _genre, count in paired],
        color=_PRIMARY_COLOR,
        height=0.68,
    )
    ax.bar_label(bars, padding=3, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Movie count")
    ax.set_ylabel("Genre token")
    ax.set_title("Genre token frequency", loc="left", pad=28)
    _subtitle(
        ax, "A movie may belong to multiple genres; counts are non-additive."
    )
    _figure_note(
        fig,
        "Genre tokens are not mutually exclusive; no composite genre category is implied.",
    )
    return len(records)


def _build_director_profile(
    fig: Any, ax: Any, table: Any, records: tuple[Record, ...]
) -> int:
    table_name = _CHART_TABLES["director_profile"]
    raw_names = _text_value(records, "director_raw", table_name)
    norm_keys = _text_value(records, "director_norm_key", table_name)
    counts = _count_value(records, "director_count", table_name)
    ordered = sorted(
        zip(raw_names, norm_keys, counts),
        key=lambda item: (-item[2], item[0], item[1]),
    )

    top = ordered[:_TOP_DIRECTOR_COUNT]
    remaining = ordered[_TOP_DIRECTOR_COUNT:]
    labels = [raw_name for raw_name, _norm, _count in top]
    values = [count for _raw, _norm, count in top]
    colors = [_PRIMARY_COLOR] * len(top)

    if remaining:
        labels.append(f"Other ({len(remaining)} directors)")
        values.append(sum(count for _raw, _norm, count in remaining))
        colors.append(_OTHER_COLOR)
        other_note = (
            f"Top {len(top)} shown; Other ({len(remaining)} directors) aggregates "
            "remaining directors for presentation only."
        )
    else:
        other_note = (
            f"Top {len(top)} shown; no remaining directors to aggregate as Other."
        )

    bars = ax.barh(labels, values, color=colors, height=0.68)
    ax.bar_label(bars, padding=3, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Movies with non-missing director")
    ax.set_ylabel("Director raw name")
    ax.set_title("Director profile (presentation subset)", loc="left", pad=28)
    _subtitle(ax, other_note)
    _figure_note(fig, _missing_director_note(table))
    return len(values)


def _build_data_quality_flags(
    fig: Any, ax: Any, table: Any, records: tuple[Record, ...]
) -> int:
    del table
    table_name = _CHART_TABLES["data_quality_flags"]
    _text_value(records, "flag", table_name)
    labels = _text_value(records, "flag_label", table_name)
    true_counts = _count_value(records, "true_count", table_name)
    _count_value(records, "false_count", table_name)
    _count_value(records, "missing_count", table_name)

    bars = ax.barh(labels, true_counts, color=_PRIMARY_COLOR, height=0.68)
    ax.bar_label(bars, padding=3, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Movies with flag = True")
    ax.set_ylabel("Independent flag")
    ax.set_title("Independent data-quality flags", loc="left", pad=28)
    _subtitle(
        ax,
        "Each flag is evaluated independently and may overlap; no composite score is calculated.",
    )
    return len(records)


def _build_dtp_revenue_histogram(
    fig: Any, ax: Any, table: Any, records: tuple[Record, ...]
) -> int:
    del table
    table_name = _REVENUE_TABLE_SPECS["dtp_revenue_histogram"][1]
    bins = _text_value(records, "revenue_bin_vnd", table_name)
    counts = _count_value(records, "movie_count", table_name)

    if len({str(bin_label) for bin_label in bins}) != len(bins):
        raise VisualizationValidationError(
            f"table {table_name!r} field 'revenue_bin_vnd': duplicate EDA bin labels"
        )
    represented = sum(counts)
    if represented != EXPECTED_DTP_ROUNDED_ROWS:
        raise VisualizationValidationError(
            f"table {table_name!r} population for 'movie_count': expected "
            f"{EXPECTED_DTP_ROUNDED_ROWS} rounded DTP observations, got {represented}"
        )

    x_positions = list(range(len(bins)))
    bars = ax.bar(x_positions, counts, color=_PRIMARY_COLOR, width=0.68)
    ax.bar_label(bars, padding=3, fontsize=9)
    ax.set_xticks(x_positions, bins)
    ax.tick_params(axis="x", labelrotation=45 if len(bins) > 6 else 0)
    ax.set_xlabel("DTP revenue bin (VND; EDA-provided labels)")
    ax.set_ylabel("Movie count")
    ax.set_ylim(0, max(counts) * 1.15 if counts else 1)
    ax.set_title(
        "DTP revenue distribution — rounded observations",
        loc="left",
        pad=34,
    )
    _subtitle(
        ax,
        "Precomputed EDA VND bins only; lower-bound and BOV revenue are not included.",
    )
    _revenue_warning(fig)
    _figure_note(
        fig,
        f"Histogram contains {EXPECTED_DTP_ROUNDED_ROWS} rounded DTP observations only; "
        "lower-bound observations are excluded and shown separately.",
    )
    return len(records)


def _build_dtp_lower_bound_evidence(
    fig: Any, ax: Any, table: Any, records: tuple[Record, ...]
) -> int:
    del table
    table_name = _REVENUE_TABLE_SPECS["dtp_lower_bound_evidence"][1]
    movie_ids = _text_value(records, "movie_id", table_name)
    titles = _text_value(records, "canonical_title", table_name)
    _text_value(records, "dtp_revenue_raw", table_name)
    values = _count_value(records, "dtp_revenue_vnd", table_name)
    _text_value(records, "dtp_revenue_quality", table_name)
    display_values = _text_value(records, "display_value", table_name)

    expected_ids = tuple(LOWER_BOUND_IDS)
    if tuple(movie_ids) != expected_ids or len(records) != len(expected_ids):
        raise VisualizationValidationError(
            f"table {table_name!r} field 'movie_id': expected exactly "
            f"{expected_ids!r}, got {tuple(movie_ids)!r}"
        )
    for index, display_value in enumerate(display_values):
        if not display_value.startswith("≥"):
            raise VisualizationValidationError(
                f"table {table_name!r} row {index} field 'display_value': "
                f"expected a lower-bound string beginning '≥', got {display_value!r}"
            )

    labels = [
        f"{movie_id} — {title}" for movie_id, title in zip(movie_ids, titles)
    ]
    bars = ax.barh(labels, values, color=_PRIMARY_COLOR, height=0.55)
    ax.bar_label(bars, labels=display_values, padding=4, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel("DTP lower-bound revenue (VND)")
    ax.set_ylabel("Movie")
    if values:
        ax.set_xlim(0, max(values) * 1.25)
    ax.set_title("DTP lower-bound revenue evidence", loc="left", pad=34)
    _subtitle(
        ax,
        "Lower bounds only — not exact values; display labels are copied verbatim from EDA.",
    )
    _revenue_warning(fig)
    _figure_note(
        fig,
        "Lower-bound values are excluded from the rounded-value histogram; "
        "no totals, averages or rankings are calculated.",
    )
    return len(records)


def _build_bov_comparison_scatter(
    fig: Any, ax: Any, table: Any, records: tuple[Record, ...]
) -> int:
    table_name = _REVENUE_TABLE_SPECS["bov_comparison_scatter"][1]
    movie_ids = _text_value(records, "movie_id", table_name)
    dtp_values = _positive_coordinate_value(
        records, "dtp_revenue_vnd", table_name
    )
    bov_values = _positive_coordinate_value(records, "bov_revenue_vnd", table_name)
    priorities = _text_value(records, "review_priority", table_name)
    gap_pct = _gap_reference_pct(table, table_name)

    normal_indexes = [
        index for index, priority in enumerate(priorities) if priority != "high"
    ]
    high_indexes = [
        index for index, priority in enumerate(priorities) if priority == "high"
    ]

    ax.scatter(
        [dtp_values[index] for index in normal_indexes],
        [bov_values[index] for index in normal_indexes],
        s=26,
        color=_PRIMARY_COLOR,
        alpha=0.65,
        edgecolors="none",
        label=f"Accepted comparison observations ({len(normal_indexes)})",
        zorder=2,
    )
    ax.scatter(
        [dtp_values[index] for index in high_indexes],
        [bov_values[index] for index in high_indexes],
        s=95,
        marker="D",
        color=_HIGH_PRIORITY_COLOR,
        edgecolors=_HIGH_PRIORITY_EDGE,
        linewidths=0.7,
        label="High-priority review",
        zorder=4,
    )

    all_values = dtp_values + bov_values
    axis_min = min(all_values) * 0.6
    axis_max = max(all_values) * 1.6
    reference_x = [axis_min, axis_max]
    lower_band = [value / (1.0 + gap_pct / 100.0) for value in reference_x]
    upper_band = [value * (1.0 + gap_pct / 100.0) for value in reference_x]

    ax.fill_between(
        reference_x,
        lower_band,
        upper_band,
        color=_REFERENCE_BAND_COLOR,
        alpha=0.18,
        label=f"±{gap_pct:g}% diagnostic reference",
        zorder=0,
    )
    ax.plot(
        reference_x,
        reference_x,
        color=_NOTE_COLOR,
        linestyle="--",
        linewidth=1.0,
        label="Identity y = x",
        zorder=1,
    )

    annotation_offsets = (
        (6, 6),
        (6, -16),
        (-46, 6),
        (-46, -16),
    )
    for position, index in enumerate(high_indexes):
        offset = annotation_offsets[position % len(annotation_offsets)]
        ax.annotate(
            movie_ids[index],
            xy=(dtp_values[index], bov_values[index]),
            xytext=offset,
            textcoords="offset points",
            fontsize=8,
            fontweight="bold",
            color=_HIGH_PRIORITY_COLOR,
            bbox={
                "boxstyle": "round,pad=0.15",
                "facecolor": "white",
                "edgecolor": _HIGH_PRIORITY_COLOR,
                "alpha": 0.9,
            },
            zorder=5,
        )

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(axis_min, axis_max)
    ax.set_ylim(axis_min, axis_max)
    ax.set_xlabel("DTP revenue (VND; log scale)")
    ax.set_ylabel("BOV revenue (VND; log scale)")
    ax.set_title("DTP vs BOV revenue — diagnostic comparison", loc="left", pad=34)
    ax.legend(loc="lower right", frameon=True, framealpha=0.95)
    _subtitle(
        ax,
        f"{EXPECTED_SCATTER_ROWS} accepted comparison observations shown; "
        "scope comparability has not been verified. High-priority points are pending review.",
    )
    _revenue_warning(fig)
    _figure_note(
        fig,
        f"Log axes; identity y = x and ±{gap_pct:g}% band are diagnostic references only, "
        "not validation thresholds or proof of conflict. Neither source is authoritative; "
        "no fitted line or statistical model.",
    )
    return len(records)


def plot_movie_match_status(report: Any, output_path: str | Path) -> ChartResult:
    """Render the movie match-status donut from validated EDA output."""
    return _render(
        "movie_match_status",
        report,
        output_path,
        _build_movie_match_status,
        figsize=(8, 6),
    )


def plot_release_year_distribution(
    report: Any, output_path: str | Path
) -> ChartResult:
    """Render release-year movie counts as a chronological bar chart."""
    return _render(
        "release_year_distribution",
        report,
        output_path,
        _build_release_year_distribution,
    )


def plot_release_year_match_status(
    report: Any, output_path: str | Path
) -> ChartResult:
    """Render a stacked year-by-match-status bar chart from EDA counts."""
    return _render(
        "release_year_match_status",
        report,
        output_path,
        _build_release_year_match_status,
    )


def plot_genre_frequency(report: Any, output_path: str | Path) -> ChartResult:
    """Render a sorted horizontal bar chart of non-additive genre tokens."""
    return _render(
        "genre_frequency",
        report,
        output_path,
        _build_genre_frequency,
        figsize=(10, 7),
    )


def plot_director_profile(report: Any, output_path: str | Path) -> ChartResult:
    """Render a readable director subset with a presentation-only Other bar."""
    return _render(
        "director_profile",
        report,
        output_path,
        _build_director_profile,
        figsize=(10, 7),
    )


def plot_data_quality_flags(report: Any, output_path: str | Path) -> ChartResult:
    """Render true counts for independently evaluated data-quality flags."""
    return _render(
        "data_quality_flags",
        report,
        output_path,
        _build_data_quality_flags,
        figsize=(10, 7),
    )


def plot_dtp_revenue_histogram(
    report: Any, output_path: str | Path
) -> ChartResult:
    """Render the EDA-provided rounded DTP revenue histogram."""
    return _render(
        "dtp_revenue_histogram",
        report,
        output_path,
        _build_dtp_revenue_histogram,
        figsize=(10, 6),
        preparer=_prepare_revenue_table,
        layout_rect=(0, 0.13, 1, 0.92),
    )


def plot_dtp_lower_bound_evidence(
    report: Any, output_path: str | Path
) -> ChartResult:
    """Render EDA lower-bound revenue records as separate evidence."""
    return _render(
        "dtp_lower_bound_evidence",
        report,
        output_path,
        _build_dtp_lower_bound_evidence,
        figsize=(10, 5),
        preparer=_prepare_revenue_table,
        layout_rect=(0, 0.13, 1, 0.92),
    )


def plot_bov_comparison_scatter(
    report: Any, output_path: str | Path
) -> ChartResult:
    """Render the diagnostic DTP-versus-BOV comparison scatter."""
    return _render(
        "bov_comparison_scatter",
        report,
        output_path,
        _build_bov_comparison_scatter,
        figsize=(9.5, 8),
        preparer=_prepare_bov_scatter,
        layout_rect=(0, 0.14, 1, 0.92),
    )


__all__ = [
    "ChartResult",
    "plot_movie_match_status",
    "plot_release_year_distribution",
    "plot_release_year_match_status",
    "plot_genre_frequency",
    "plot_director_profile",
    "plot_data_quality_flags",
    "plot_dtp_revenue_histogram",
    "plot_dtp_lower_bound_evidence",
    "plot_bov_comparison_scatter",
]
