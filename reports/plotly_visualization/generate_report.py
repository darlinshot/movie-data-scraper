"""Generate the self-contained Plotly HTML report from approved EDA tables.

This generator is a presentation layer only. It loads the approved analytics CSV
through ``build_eda_report``, validates that report with the existing
visualization contract, and draws the nine charts from the chart-ready EDA
tables. It never reloads raw scraper data, recalculates business rules, or
writes to the analytics pipeline.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

from movie_data_collector.analytics.eda import (
    ACCEPTED_HIGH_PRIORITY_IDS,
    CANDIDATE_MOVIE_ID,
    GAP_REFERENCE_PCT,
    LOWER_BOUND_IDS,
    QUARANTINED_MOVIE_ID,
    REVENUE_WARNING_LABEL,
    build_eda_report,
)
from movie_data_collector.visualization.validation import (
    rows_as_dicts,
    validate_visualization_report,
)

OUTPUT_PATH = HERE / "index.html"
CSS_PATH = Path("assets/css/style.css")

INK = "#182230"
MUTED = "#64748b"
LINE = "#e2e7ee"
GRID = "#eef1f5"
NAVY = "#0d1b2a"
PRIMARY = "#3f6f8f"
OTHER = "#9aa4ad"
HIGH = "#b2504a"
AMBER = "#b45309"
AMBER_SOFT = "#fff7e6"
AMBER_LINE = "#f5d28a"
STATUS_ORDER = ("matched", "needs_review", "not_found")
STATUS_LABELS = {
    "matched": "Matched",
    "needs_review": "Needs Review",
    "not_found": "Not Found",
}
STATUS_COLORS = {
    "matched": "#2f7d63",
    "needs_review": "#d9a441",
    "not_found": "#b2504a",
}
FONT = (
    "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "
    "'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
)
PLOTLY_CONFIG = {
    "responsive": True,
    "displaylogo": False,
    "displayModeBar": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}
ChartSpec = tuple[str, go.Figure, str, str, str, str, str, bool, bool]


def _rows(report: Any, key: str, group: str = "chart_data") -> tuple[dict[str, Any], ...]:
    """Return one approved EDA table as dictionaries."""
    source: Mapping[str, Any] = getattr(report, group)
    return rows_as_dicts(source[key])


def _count(rows: Sequence[dict[str, Any]], field: str) -> int:
    return sum(int(row[field]) for row in rows)


def _table_text(table: Any) -> str:
    parts = [*(table.notes or ()), *(table.exclusions or ())]
    return " ".join(str(part) for part in parts if part)


def _warning_annotation() -> dict[str, Any]:
    return {
        "x": 0.99,
        "y": 1.10,
        "xref": "paper",
        "yref": "paper",
        "xanchor": "right",
        "yanchor": "bottom",
        "showarrow": False,
        "text": f"<b>{html.escape(REVENUE_WARNING_LABEL)}</b>",
        "bgcolor": AMBER_SOFT,
        "bordercolor": AMBER_LINE,
        "borderwidth": 1,
        "borderpad": 7,
        "font": {"color": AMBER, "size": 11, "family": FONT},
    }


def _style_figure(
    fig: go.Figure,
    *,
    height: int,
    margin: dict[str, int],
    xaxis: dict[str, Any] | None = None,
    yaxis: dict[str, Any] | None = None,
    showlegend: bool = False,
    legend: dict[str, Any] | None = None,
    revenue: bool = False,
    annotations: Sequence[dict[str, Any]] = (),
    barmode: str | None = None,
) -> go.Figure:
    """Apply report-wide chart styling without changing any data."""
    layout_annotations = [dict(item) for item in annotations]
    if revenue:
        layout_annotations.append(_warning_annotation())

    updates: dict[str, Any] = {
        "template": "plotly_white",
        "autosize": True,
        "height": height,
        "margin": margin,
        "paper_bgcolor": "#ffffff",
        "plot_bgcolor": "#ffffff",
        "font": {"family": FONT, "size": 12, "color": INK},
        "hoverlabel": {
            "bgcolor": NAVY,
            "bordercolor": NAVY,
            "font": {"color": "#ffffff", "size": 12, "family": FONT},
        },
        "annotations": layout_annotations,
        "showlegend": showlegend,
        "legend": legend
        or {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
            "font": {"size": 11},
        },
        "xaxis": {
            "linecolor": LINE,
            "zerolinecolor": LINE,
            "gridcolor": GRID,
            "title": {"font": {"size": 12, "color": MUTED}},
            **(xaxis or {}),
        },
        "yaxis": {
            "linecolor": LINE,
            "zerolinecolor": LINE,
            "gridcolor": GRID,
            "title": {"font": {"size": 12, "color": MUTED}},
            **(yaxis or {}),
        },
    }
    if barmode is not None:
        updates["barmode"] = barmode
    fig.update_layout(**updates)
    return fig


def _assert_contract(report: Any) -> Any:
    """Fail early if the approved EDA contract or safeguards do not hold."""
    validation = validate_visualization_report(report)
    if validation.validation_status != "validated":
        raise RuntimeError("EDA report failed visualization validation")
    if validation.validated_movie_count != 92 or report.column_count != 54:
        raise RuntimeError("Expected 92 movies and 54 analytical columns")

    status_rows = _rows(report, "movie_match_status_donut")
    status_counts = {
        str(row["bov_match_status"]): int(row["movie_count"]) for row in status_rows
    }
    if status_counts != {"matched": 81, "needs_review": 1, "not_found": 10}:
        raise RuntimeError(f"Unexpected match-status counts: {status_counts}")

    histogram_rows = _rows(report, "dtp_revenue_histogram")
    if _count(histogram_rows, "movie_count") != 90:
        raise RuntimeError("DTP histogram must contain exactly 90 rounded observations")

    lower_rows = rows_as_dicts(report.tables["lower_bound_revenue_table"])
    lower_ids = tuple(str(row["movie_id"]) for row in lower_rows)
    if lower_ids != LOWER_BOUND_IDS:
        raise RuntimeError(f"Unexpected lower-bound IDs: {lower_ids}")

    scatter_rows = _rows(report, "bov_comparison_scatter")
    scatter_ids = {str(row["movie_id"]) for row in scatter_rows}
    if len(scatter_rows) != 77:
        raise RuntimeError(f"Scatter must contain exactly 77 rows, got {len(scatter_rows)}")
    excluded = {
        LOWER_BOUND_IDS[0],
        LOWER_BOUND_IDS[1],
        QUARANTINED_MOVIE_ID,
        CANDIDATE_MOVIE_ID,
    }
    if scatter_ids & excluded:
        raise RuntimeError(f"Scatter contains excluded IDs: {sorted(scatter_ids & excluded)}")
    for movie_id in ACCEPTED_HIGH_PRIORITY_IDS:
        matches = [row for row in scatter_rows if row["movie_id"] == movie_id]
        if len(matches) != 1 or matches[0]["review_priority"] != "high":
            raise RuntimeError(f"High-priority point {movie_id} is missing or not distinguishable")

    metadata = report.chart_data["bov_comparison_scatter"].metadata
    if metadata.get("gap_reference_pct") != GAP_REFERENCE_PCT:
        raise RuntimeError("Unexpected revenue-gap reference metadata")
    return validation


def _match_status_figure(report: Any) -> go.Figure:
    rows = _rows(report, "movie_match_status_donut")
    counts = {str(row["bov_match_status"]): int(row["movie_count"]) for row in rows}
    labels = [STATUS_LABELS[status] for status in STATUS_ORDER]
    values = [counts[status] for status in STATUS_ORDER]
    colors = [STATUS_COLORS[status] for status in STATUS_ORDER]
    total = sum(values)

    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.38,
            sort=False,
            marker={"colors": colors, "line": {"color": "#ffffff", "width": 2}},
            textinfo="label+percent",
            textfont={"size": 12},
            hovertemplate=(
                "<b>%{label}</b><br>Movies: %{value}"
                "<br>Share: %{percent}<extra></extra>"
            ),
        )
    )
    return _style_figure(
        fig,
        height=430,
        margin={"l": 20, "r": 20, "t": 28, "b": 20},
        showlegend=True,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": -0.08,
            "xanchor": "center",
            "x": 0.5,
            "font": {"size": 11},
        },
        annotations=[
            {
                "x": 0.5,
                "y": 0.5,
                "xref": "paper",
                "yref": "paper",
                "showarrow": False,
                "text": f"Total<br><b>{total}</b>",
                "font": {"size": 20, "color": NAVY, "family": FONT},
            }
        ],
    )


def _release_year_figure(report: Any) -> go.Figure:
    rows = _rows(report, "release_year_histogram")
    years = [row["release_year"] for row in rows]
    counts = [int(row["movie_count"]) for row in rows]
    fig = go.Figure(
        go.Bar(
            x=years,
            y=counts,
            text=counts,
            textposition="outside",
            cliponaxis=False,
            marker={"color": PRIMARY},
            hovertemplate="<b>Year %{x}</b><br>Movies: %{y}<extra></extra>",
        )
    )
    return _style_figure(
        fig,
        height=430,
        margin={"l": 55, "r": 20, "t": 28, "b": 85},
        xaxis={
            "title": "Release year",
            "type": "category",
            "tickangle": 45 if len(years) > 8 else 0,
            "showgrid": False,
            "automargin": True,
        },
        yaxis={"title": "Movie count", "dtick": 1, "rangemode": "tozero"},
    )


def _release_year_status_figure(report: Any) -> go.Figure:
    stacked = _rows(report, "release_year_match_status_stacked")
    years = [row["release_year"] for row in _rows(report, "release_year_histogram")]
    matrix: dict[tuple[Any, str], int] = {
        (row["release_year"], str(row["bov_match_status"])): int(row["movie_count"])
        for row in stacked
    }
    fig = go.Figure()
    for status in STATUS_ORDER:
        label = STATUS_LABELS[status]
        counts = [matrix.get((year, status), 0) for year in years]
        fig.add_trace(
            go.Bar(
                name=label,
                x=years,
                y=counts,
                marker={
                    "color": STATUS_COLORS[status],
                    "line": {"color": "#ffffff", "width": 1},
                },
                hovertemplate=(
                    f"<b>%{{x}}</b><br>{html.escape(label)}: %{{y}}"
                    f"<extra>{html.escape(label)}</extra>"
                ),
            )
        )
    return _style_figure(
        fig,
        height=460,
        margin={"l": 55, "r": 20, "t": 28, "b": 80},
        xaxis={
            "title": "Release year",
            "type": "category",
            "tickangle": 45,
            "showgrid": False,
        },
        yaxis={"title": "Movie count", "dtick": 1, "rangemode": "tozero"},
        showlegend=True,
        legend={
            "orientation": "h",
            "title": {"text": "Match status", "font": {"size": 11}},
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
            "font": {"size": 11},
        },
        barmode="stack",
    )


def _genre_figure(report: Any) -> go.Figure:
    rows = _rows(report, "genre_frequency_bar")
    tokens = [str(row["genre_token"]) for row in rows]
    counts = [int(row["movie_count"]) for row in rows]
    fig = go.Figure(
        go.Bar(
            x=counts,
            y=tokens,
            orientation="h",
            marker={"color": PRIMARY},
            text=counts,
            textposition="outside",
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Genre token count: %{x}<extra></extra>",
        )
    )
    return _style_figure(
        fig,
        height=820,
        margin={"l": 185, "r": 45, "t": 28, "b": 55},
        xaxis={
            "title": "Movie count (non-additive token count)",
            "dtick": 5,
            "rangemode": "tozero",
        },
        yaxis={"autorange": "reversed", "tickfont": {"size": 10}, "automargin": True},
    )


def _director_figure(report: Any) -> go.Figure:
    rows = _rows(report, "director_profile_bar")
    top_rows = rows[:10]
    remaining_rows = rows[10:]
    labels = [str(row["director_raw"]) for row in top_rows]
    counts = [int(row["director_count"]) for row in top_rows]
    if remaining_rows:
        labels.append(f"Other ({len(remaining_rows)} directors)")
        counts.append(_count(remaining_rows, "director_count"))
    colors = [PRIMARY] * len(top_rows) + ([OTHER] if remaining_rows else [])

    fig = go.Figure(
        go.Bar(
            x=counts,
            y=labels,
            orientation="h",
            marker={"color": colors},
            text=counts,
            textposition="outside",
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Movies: %{x}<extra></extra>",
        )
    )
    return _style_figure(
        fig,
        height=540,
        margin={"l": 210, "r": 45, "t": 28, "b": 55},
        xaxis={
            "title": "Movies with non-missing director",
            "dtick": 1,
            "rangemode": "tozero",
        },
        yaxis={"autorange": "reversed", "tickfont": {"size": 11}, "automargin": True},
    )


def _quality_flags_figure(report: Any) -> go.Figure:
    rows = _rows(report, "independent_data_quality_flags")
    labels = [str(row["flag_label"]) for row in rows]
    counts = [int(row["true_count"]) for row in rows]
    customdata = [
        [str(row["flag"]), int(row["false_count"]), int(row["missing_count"])]
        for row in rows
    ]
    fig = go.Figure(
        go.Bar(
            x=counts,
            y=labels,
            orientation="h",
            marker={"color": PRIMARY},
            text=counts,
            textposition="outside",
            cliponaxis=False,
            customdata=customdata,
            hovertemplate=(
                "<b>%{y}</b><br>True: %{x}<br>False: %{customdata[1]}"
                "<br>Missing: %{customdata[2]}<br>Field: %{customdata[0]}<extra></extra>"
            ),
        )
    )
    return _style_figure(
        fig,
        height=580,
        margin={"l": 250, "r": 45, "t": 28, "b": 55},
        xaxis={"title": "Movies with flag = True", "dtick": 10, "rangemode": "tozero"},
        yaxis={"autorange": "reversed", "tickfont": {"size": 11}, "automargin": True},
    )


def _dtp_histogram_figure(report: Any) -> go.Figure:
    rows = _rows(report, "dtp_revenue_histogram")
    bins = [str(row["revenue_bin_vnd"]) for row in rows]
    counts = [int(row["movie_count"]) for row in rows]
    fig = go.Figure(
        go.Bar(
            x=bins,
            y=counts,
            marker={"color": PRIMARY},
            text=counts,
            textposition="outside",
            cliponaxis=False,
            hovertemplate=(
                "<b>%{x}</b><br>Rounded DTP observations: %{y}<extra></extra>"
            ),
        )
    )
    return _style_figure(
        fig,
        height=440,
        margin={"l": 55, "r": 20, "t": 95, "b": 95},
        xaxis={
            "title": "DTP revenue bin (EDA labels)",
            "tickangle": -25,
            "showgrid": False,
            "automargin": True,
        },
        yaxis={"title": "Rounded observations", "dtick": 5, "rangemode": "tozero"},
        revenue=True,
    )


def _lower_bound_figure(report: Any) -> go.Figure:
    rows = rows_as_dicts(report.tables["lower_bound_revenue_table"])
    labels = [f"{row['movie_id']} — {row['canonical_title']}" for row in rows]
    values = [int(row["dtp_revenue_vnd"]) for row in rows]
    display_values = [str(row["display_value"]) for row in rows]
    raw_values = [str(row["dtp_revenue_raw"]) for row in rows]
    maximum = max(values) if values else 1
    step = 10_000_000_000
    tick_values = list(range(0, ((maximum // step) + 2) * step, step))
    tick_text = [f"{value // step}B" for value in tick_values]

    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker={"color": "#d9a441"},
            text=display_values,
            textposition="outside",
            cliponaxis=False,
            customdata=[[raw] for raw in raw_values],
            hovertemplate=(
                "<b>%{y}</b><br>Displayed EDA value: %{text}"
                "<br>Raw DTP text: %{customdata[0]}<extra>Lower bound</extra>"
            ),
        )
    )
    return _style_figure(
        fig,
        height=380,
        margin={"l": 250, "r": 80, "t": 95, "b": 60},
        xaxis={
            "title": "Reported lower-bound floor (VND; not an exact value)",
            "tickvals": tick_values,
            "ticktext": tick_text,
            "range": [0, maximum * 1.35],
        },
        yaxis={"automargin": True, "tickfont": {"size": 11}},
        revenue=True,
    )


def _bov_scatter_figure(report: Any) -> go.Figure:
    rows = _rows(report, "bov_comparison_scatter")
    normal = [row for row in rows if row["review_priority"] != "high"]
    high = [row for row in rows if row["review_priority"] == "high"]
    reference_pct = int(
        report.chart_data["bov_comparison_scatter"].metadata["gap_reference_pct"]
    )
    factor = 1 + reference_pct / 100

    dtp_values = sorted(int(row["dtp_revenue_vnd"]) for row in rows)
    bov_values = [int(row["bov_revenue_vnd"]) for row in rows]
    lower = [value / factor for value in dtp_values]
    upper = [value * factor for value in dtp_values]
    minimum = min(dtp_values + bov_values)
    maximum = max(dtp_values + bov_values)
    axis_range = [minimum * 0.6, maximum * 1.6]
    tick_values = [1_000_000_000, 10_000_000_000, 100_000_000_000, 1_000_000_000_000]
    tick_text = ["1B", "10B", "100B", "1T"]

    def customdata(row: dict[str, Any]) -> list[Any]:
        return [
            str(row["canonical_title"]),
            str(row["movie_id"]),
            float(row["revenue_gap_pct"]) if row["revenue_gap_pct"] is not None else None,
            str(row["gap_band_label"]),
            str(row["review_status_label"]),
            str(row["review_priority_label"]),
        ]

    hovertemplate = (
        "<b>%{customdata[0]}</b><br>Movie ID: %{customdata[1]}"
        "<br>DTP: %{x:,.0f} VND<br>BOV: %{y:,.0f} VND"
        "<br>EDA gap reference: %{customdata[2]:.1f}%"
        "<br>Band: %{customdata[3]}<br>Review: %{customdata[4]}"
        "<br>Priority: %{customdata[5]}<extra></extra>"
    )

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dtp_values + list(reversed(dtp_values)),
            y=lower + list(reversed(upper)),
            mode="lines",
            fill="toself",
            fillcolor="rgba(217, 164, 65, 0.12)",
            line={"color": "rgba(217, 164, 65, 0.18)", "width": 1},
            name=f"±{reference_pct}% diagnostic reference",
            legendrank=3,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[minimum * 0.6, maximum * 1.6],
            y=[minimum * 0.6, maximum * 1.6],
            mode="lines",
            line={"color": "#8a94a3", "dash": "dot", "width": 1},
            name="Identity y = x",
            legendrank=4,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[int(row["dtp_revenue_vnd"]) for row in normal],
            y=[int(row["bov_revenue_vnd"]) for row in normal],
            mode="markers",
            name=f"Accepted comparison observations ({len(normal)})",
            legendrank=1,
            marker={
                "color": PRIMARY,
                "size": 8,
                "opacity": 0.78,
                "line": {"color": "#ffffff", "width": 0.6},
            },
            customdata=[customdata(row) for row in normal],
            hovertemplate=hovertemplate,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[int(row["dtp_revenue_vnd"]) for row in high],
            y=[int(row["bov_revenue_vnd"]) for row in high],
            mode="markers+text",
            name="High-priority review",
            legendrank=2,
            text=[str(row["movie_id"]) for row in high],
            textposition="top center",
            textfont={"color": HIGH, "size": 10, "family": FONT},
            marker={
                "color": HIGH,
                "size": 12,
                "symbol": "diamond",
                "line": {"color": NAVY, "width": 1},
            },
            customdata=[customdata(row) for row in high],
            hovertemplate=hovertemplate,
        )
    )
    return _style_figure(
        fig,
        height=640,
        margin={"l": 70, "r": 30, "t": 95, "b": 105},
        xaxis={
            "title": "DTP revenue (VND; log scale)",
            "type": "log",
            "range": axis_range,
            "tickvals": tick_values,
            "ticktext": tick_text,
        },
        yaxis={
            "title": "BOV revenue (VND; log scale)",
            "type": "log",
            "range": axis_range,
            "tickvals": tick_values,
            "ticktext": tick_text,
        },
        showlegend=True,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": -0.22,
            "xanchor": "center",
            "x": 0.5,
            "font": {"size": 10},
        },
        revenue=True,
    )


def _figure_html(fig: go.Figure, div_id: str) -> str:
    return fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        config=PLOTLY_CONFIG,
        div_id=div_id,
    )


def _chart_card(
    *,
    chart_id: str,
    figure: go.Figure,
    number: str,
    title: str,
    explanation: str,
    source: str,
    note: str = "",
    revenue: bool = False,
    full: bool = False,
) -> str:
    warning = (
        '<p class="chart-warning"><span aria-hidden="true">!</span> '
        f"{html.escape(REVENUE_WARNING_LABEL)}</p>"
        if revenue
        else ""
    )
    note_html = f'<p class="chart-note">{html.escape(note)}</p>' if note else ""
    classes = "chart-card chart-card--full" if full else "chart-card"
    if revenue:
        classes += " chart-card--revenue"
    return f"""        <figure class="{classes}" id="chart-{chart_id}">
          <div class="chart-card__header">
            <div class="chart-card__headline">
              <span class="chart-index">{html.escape(number)}</span>
              <h3>{html.escape(title)}</h3>
            </div>
            {warning}
          </div>
          <p class="chart-explanation">{html.escape(explanation)}</p>
          <div class="plot-frame">{_figure_html(figure, f'plot-{chart_id}')}</div>
          <figcaption class="chart-card__caption">
            <span class="source-label">EDA source</span>
            <code>{html.escape(source)}</code>
            {note_html}
          </figcaption>
        </figure>"""


def _card(spec: ChartSpec) -> str:
    (
        chart_id,
        figure,
        number,
        title,
        explanation,
        source,
        note,
        revenue,
        full,
    ) = spec
    return _chart_card(
        chart_id=chart_id,
        figure=figure,
        number=number,
        title=title,
        explanation=explanation,
        source=source,
        note=note,
        revenue=revenue,
        full=full,
    )


def build_html(report: Any) -> str:
    validation = _assert_contract(report)
    director_note = _table_text(report.chart_data["director_profile_bar"])

    specs: list[ChartSpec] = [
        (
            "match-status",
            _match_status_figure(report),
            "01",
            "Movie Match Status",
            "Diagnostic matcher outcomes for all 92 movies. These labels are not a data-quality or correctness score.",
            "chart_data.movie_match_status_donut",
            "Counts: 81 matched, 1 needs review, 10 not found.",
            False,
            False,
        ),
        (
            "release-year",
            _release_year_figure(report),
            "02",
            "Release Year Distribution",
            "Descriptive counts by release year. No full release date, revenue result, trend or performance inference is added.",
            "chart_data.release_year_histogram",
            "Year-only distribution of the approved movie records.",
            False,
            False,
        ),
        (
            "release-year-status",
            _release_year_status_figure(report),
            "03",
            "Release Year × Match Status",
            "Matching status within each release-year group. Missing year/status cells are zero for rendering only.",
            "chart_data.release_year_match_status_stacked",
            "No revenue trend is represented.",
            False,
            True,
        ),
        (
            "genre-frequency",
            _genre_figure(report),
            "04",
            "Genre Frequency",
            "Counts of EDA genre tokens. A movie may contribute to several tokens, so these counts are non-additive.",
            "chart_data.genre_frequency_bar",
            "Genre tokens are not mutually exclusive; no composite genre category is implied.",
            False,
            True,
        ),
        (
            "director-profile",
            _director_figure(report),
            "05",
            "Director Profile",
            "Top 10 raw director names are shown; remaining directors are aggregated for presentation only.",
            "chart_data.director_profile_bar",
            director_note,
            False,
            True,
        ),
        (
            "quality-flags",
            _quality_flags_figure(report),
            "06",
            "Independent Data Quality Flags",
            "Each flag is evaluated independently and may overlap. No composite score is calculated.",
            "chart_data.independent_data_quality_flags",
            "True counts are shown; hover for false and missing counts.",
            False,
            True,
        ),
        (
            "dtp-histogram",
            _dtp_histogram_figure(report),
            "07",
            "DTP Revenue Distribution",
            "Precomputed EDA VND bins for 90 rounded DTP observations only. Lower-bound values and BOV revenue are not included.",
            "chart_data.dtp_revenue_histogram",
            "Lower-bound observations are excluded from this histogram and shown separately.",
            True,
            False,
        ),
        (
            "lower-bound-evidence",
            _lower_bound_figure(report),
            "08",
            "DTP Lower-bound Evidence",
            "M0001 and M0024 are preserved separately with ≥ labels. These are lower bounds, not exact values.",
            "tables.lower_bound_revenue_table",
            "No totals, averages or rankings are calculated from lower-bound values.",
            True,
            False,
        ),
        (
            "bov-comparison",
            _bov_scatter_figure(report),
            "09",
            "DTP vs BOV Revenue — Diagnostic Comparison",
            "77 accepted exact-value observations on log axes. Four high-priority pending-review points remain distinguishable.",
            "chart_data.bov_comparison_scatter",
            "The ±10% band and identity line are diagnostic references only, not validation thresholds or proof of conflict.",
            True,
            True,
        ),
    ]
    by_id = {spec[0]: spec for spec in specs}
    movie_cards = "\n".join(_card(by_id[key]) for key in ("match-status", "release-year"))
    movie_full = _card(by_id["release-year-status"])
    genre_cards = "\n".join(
        _card(by_id[key]) for key in ("genre-frequency", "director-profile")
    )
    quality_card = _card(by_id["quality-flags"])
    revenue_cards = "\n".join(
        _card(by_id[key]) for key in ("dtp-histogram", "lower-bound-evidence")
    )
    scatter_card = _card(by_id["bov-comparison"])

    plotly_js = get_plotlyjs().replace("</script>", "<\\/script>")
    validation_text = (
        f"{validation.validation_status} · {validation.validated_movie_count} movies · "
        f"{len(validation.validated_chart_table_names)} chart tables · "
        f"{len(validation.validated_revenue_table_names)} revenue evidence tables"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Interactive Plotly exploratory data analysis of the Vietnamese movie dataset.">
  <title>Vietnamese Movie Data Analysis — Interactive EDA</title>
  <link rel="stylesheet" href="{CSS_PATH}">
  <script>{plotly_js}</script>
</head>
<body>
  <header class="site-header">
    <div class="container site-header__inner">
      <p class="eyebrow">Interactive analytics report · Plotly</p>
      <h1>Vietnamese Movie Data Analysis</h1>
      <p class="site-header__subtitle">Interactive Exploratory Data Analysis</p>
      <p class="site-header__meta">92 movies, 54 columns, 9 interactive charts</p>
      <p class="site-header__lede">
        This report recreates the nine approved Python visualizations as interactive charts.
        Every figure is drawn directly from the read-only EDA tables; no analytical rule is
        recalculated and no source data is modified.
      </p>
      <p class="validation-line"><span class="validation-dot" aria-hidden="true"></span>{html.escape(validation_text)}</p>
    </div>
  </header>

  <nav class="section-nav" aria-label="Report sections">
    <div class="container section-nav__inner">
      <a href="#overview">Overview</a>
      <a href="#movie-release">Movie &amp; Release</a>
      <a href="#genre-director">Genre &amp; Director</a>
      <a href="#data-quality">Data Quality</a>
      <a href="#revenue-analysis">Revenue Analysis</a>
    </div>
  </nav>

  <main class="container">
    <section id="overview" class="section section--overview" aria-labelledby="overview-title">
      <div class="section-heading">
        <p class="section-kicker">01 / Overview</p>
        <h2 id="overview-title">Report overview</h2>
        <p class="section-lede">
          One flat analytical CSV and one validated EDA report support every chart below.
        </p>
      </div>
      <div class="summary-grid">
        <article class="summary-card"><span class="summary-card__value">92</span><span class="summary-card__label">Movies</span><p>Approved analytical records.</p></article>
        <article class="summary-card"><span class="summary-card__value">54</span><span class="summary-card__label">Columns</span><p>Fields in the flat analytical CSV.</p></article>
        <article class="summary-card"><span class="summary-card__value">9</span><span class="summary-card__label">Interactive charts</span><p>Generated from EDA chart-ready tables.</p></article>
        <article class="summary-card"><span class="summary-card__value">1</span><span class="summary-card__label">Source CSV</span><p>No duplicate analytical dataset.</p></article>
      </div>
      <aside class="scope-note">
        <strong>Scope.</strong> Descriptive counts, matcher diagnostics and source-separated revenue evidence only.
        Revenue scope is unverified, match scores are fuzzy similarity rather than identity proof, and ticket
        candidates remain evidence only; no admissions are verified or summed.
      </aside>
    </section>

    <section id="movie-release" class="section" aria-labelledby="movie-release-title">
      <div class="section-heading">
        <p class="section-kicker">02 / Movie &amp; Release</p>
        <h2 id="movie-release-title">Movie &amp; Release</h2>
        <p class="section-lede">Matcher outcomes and year-only release context for the full movie set.</p>
      </div>
      <div class="chart-grid">
{movie_cards}
      </div>
      <div class="chart-grid chart-grid--single">
{movie_full}
      </div>
    </section>

    <section id="genre-director" class="section" aria-labelledby="genre-director-title">
      <div class="section-heading">
        <p class="section-kicker">03 / Genre &amp; Director</p>
        <h2 id="genre-director-title">Genre &amp; Director</h2>
        <p class="section-lede">Categorical profiles with explicit presentation rules.</p>
      </div>
      <div class="chart-grid chart-grid--single">
{genre_cards}
      </div>
    </section>

    <section id="data-quality" class="section" aria-labelledby="data-quality-title">
      <div class="section-heading">
        <p class="section-kicker">04 / Data Quality</p>
        <h2 id="data-quality-title">Data Quality</h2>
        <p class="section-lede">Independent indicators that describe different limitations in the dataset.</p>
      </div>
      <div class="chart-grid chart-grid--single">
{quality_card}
      </div>
    </section>

    <section id="revenue-analysis" class="section" aria-labelledby="revenue-analysis-title">
      <div class="section-heading">
        <p class="section-kicker">05 / Revenue Analysis</p>
        <h2 id="revenue-analysis-title">Revenue Analysis</h2>
        <p class="section-lede">Source-separated exploratory evidence only. No official revenue conclusion is drawn.</p>
      </div>
      <div class="revenue-warning" role="note">
        <span class="revenue-warning__mark" aria-hidden="true">!</span>
        <div>
          <strong>{html.escape(REVENUE_WARNING_LABEL)}</strong>
          <p>
            DTP and BOV are separate source observations. Lower-bound values are not exact values.
            The scatter is diagnostic only, and the ±10% band is a reference band, not a conflict
            classification. No official revenue conclusions can be drawn.
          </p>
        </div>
      </div>
      <div class="chart-grid">
{revenue_cards}
      </div>
      <div class="chart-grid chart-grid--single">
{scatter_card}
      </div>
    </section>
  </main>

  <footer class="site-footer">
    <div class="container site-footer__inner">
      <span>Vietnamese Movie Data Analysis</span>
      <span>Generated from approved EDA tables · Plotly embedded locally · no backend required</span>
    </div>
  </footer>
</body>
</html>
"""


def main() -> None:
    report = build_eda_report()
    html_text = build_html(report)
    OUTPUT_PATH.write_text(html_text, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)} ({len(html_text):,} bytes)")
    print(f"Plotly figures: {html_text.count('Plotly.newPlot')}")
    print(f"Validation: {validate_visualization_report(report).validation_status}")


if __name__ == "__main__":
    main()
