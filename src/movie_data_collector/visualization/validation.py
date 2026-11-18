"""Strict preflight validation for Python visualization inputs.

This module adapts immutable :class:`EdaTable` objects to plain dictionaries and
validates an :class:`EdaReport` against the approved EDA contract. It never
reads CSV files, recalculates analytics, renders charts or imports dataframe or
plotting libraries.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

try:  # Normal package import.
    from ..analytics import eda as _eda
except ImportError:  # Direct module loading, as used by the focused tests.
    def _load_eda_contract_module() -> Any:
        """Load the authoritative EDA module by path without importing the CLI."""
        eda_path = Path(__file__).resolve().parents[1] / "analytics" / "eda.py"
        module_name = "_visualization_eda_contract"
        existing = sys.modules.get(module_name)
        if existing is not None:
            return existing
        spec = importlib.util.spec_from_file_location(module_name, eda_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load EDA contract from {eda_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    _eda = _load_eda_contract_module()


EXPECTED_MOVIE_COUNT = int(_eda.schema.EXPECTED_MOVIE_COUNT)
EXPECTED_COLUMN_COUNT = int(_eda.schema.EXPECTED_COLUMN_COUNT)
REVENUE_WARNING_LABEL = str(_eda.REVENUE_WARNING_LABEL)
REVENUE_SCOPE_VERIFIED = _eda.REVENUE_SCOPE_VERIFIED
GAP_REFERENCE_PCT = int(_eda.GAP_REFERENCE_PCT)

LOWER_BOUND_IDS: tuple[str, ...] = tuple(str(value) for value in _eda.LOWER_BOUND_IDS)
QUARANTINED_MOVIE_ID = str(_eda.QUARANTINED_MOVIE_ID)
CANDIDATE_MOVIE_ID = str(_eda.CANDIDATE_MOVIE_ID)
ACCEPTED_HIGH_PRIORITY_IDS: tuple[str, ...] = tuple(
    str(value) for value in _eda.ACCEPTED_HIGH_PRIORITY_IDS
)

EXPECTED_DTP_ROUNDED_ROWS = int(
    _eda.schema.DTP_REVENUE_QUALITY_EXPECTED_COUNTS["rounded"]
)
EXPECTED_DTP_LOWER_BOUND_ROWS = int(
    _eda.schema.DTP_REVENUE_QUALITY_EXPECTED_COUNTS["lower_bound"]
)
EXPECTED_DTP_MISSING_INVALID_ROWS = 0
EXPECTED_SCATTER_ROWS = (
    int(_eda.schema.COMPARISON_ELIGIBLE_ROWS) - EXPECTED_DTP_LOWER_BOUND_ROWS
)

EXPECTED_DIRECTOR_ROWS = 50
EXPECTED_DIRECTOR_COUNT_SUM = 89
EXPECTED_FLAG_ROWS = 11

VALIDATION_STATUS = "validated"


_CHART_COLUMNS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "movie_match_status_donut": ("bov_match_status", "movie_count"),
        "release_year_histogram": ("release_year", "movie_count"),
        "release_year_match_status_stacked": (
            "release_year",
            "bov_match_status",
            "movie_count",
        ),
        "genre_frequency_bar": ("genre_token", "movie_count"),
        "director_profile_bar": (
            "director_raw",
            "director_norm_key",
            "director_count",
        ),
        "independent_data_quality_flags": (
            "flag",
            "flag_label",
            "true_count",
            "false_count",
            "missing_count",
        ),
        "dtp_revenue_histogram": ("revenue_bin_vnd", "movie_count"),
        "bov_comparison_scatter": (
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
    }
)

_REVENUE_TABLE_COLUMNS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "lower_bound_revenue_table": (
            "movie_id",
            "canonical_title",
            "dtp_revenue_raw",
            "dtp_revenue_vnd",
            "dtp_revenue_quality",
            "display_value",
            "include_revenue_eda",
        ),
        "pending_workflow_table": (
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
        ),
    }
)

_REVENUE_SUMMARY_COLUMNS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "dtp_revenue_population": ("metric", "value", "population", "notes"),
    }
)

_REQUIRED_COLUMNS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        **_CHART_COLUMNS,
        **_REVENUE_TABLE_COLUMNS,
        **_REVENUE_SUMMARY_COLUMNS,
    }
)

CHART_TABLE_NAMES: tuple[str, ...] = tuple(_CHART_COLUMNS)
REVENUE_TABLE_NAMES: tuple[str, ...] = tuple(_REVENUE_TABLE_COLUMNS)
REVENUE_SUMMARY_NAMES: tuple[str, ...] = tuple(_REVENUE_SUMMARY_COLUMNS)

_EXPECTED_SCATTER_EXCLUSIONS: tuple[str, ...] = (
    *LOWER_BOUND_IDS,
    QUARANTINED_MOVIE_ID,
    CANDIDATE_MOVIE_ID,
)

_EXPECTED_POPULATION_METRICS: Mapping[str, int] = MappingProxyType(
    {
        "eligible_rows": EXPECTED_MOVIE_COUNT,
        "rounded_exact_rows": EXPECTED_DTP_ROUNDED_ROWS,
        "lower_bound_rows": EXPECTED_DTP_LOWER_BOUND_ROWS,
        "missing_invalid_rows": EXPECTED_DTP_MISSING_INVALID_ROWS,
    }
)

_MISSING = object()


class VisualizationValidationError(ValueError):
    """The supplied EDA output does not satisfy the visualization contract."""


@dataclass(frozen=True)
class VisualizationValidationResult:
    """Successful preflight result; all reported names were actually validated."""

    validated_movie_count: int
    validated_chart_table_names: tuple[str, ...]
    validated_revenue_table_names: tuple[str, ...]
    validation_status: str = VALIDATION_STATUS


def _table_label(table: Any, fallback: str) -> str:
    """Describe a table using the report key plus its source name when different."""
    source_name = getattr(table, "name", None)
    if isinstance(source_name, str) and source_name and source_name != fallback:
        return f"{fallback!r} (source table {source_name!r})"
    return f"{fallback!r}"


def _rows_as_dicts(table: Any, label: str) -> tuple[dict[str, Any], ...]:
    """Adapt one EdaTable to row dictionaries without changing any value."""
    if not hasattr(table, "columns") or not hasattr(table, "rows"):
        raise VisualizationValidationError(
            f"table {label}: expected an EdaTable with 'columns' and 'rows'"
        )

    try:
        columns = tuple(table.columns)
    except TypeError as exc:
        raise VisualizationValidationError(
            f"table {label}: 'columns' must be an iterable of column names"
        ) from exc

    duplicates: list[Any] = []
    for column in columns:
        if columns.count(column) > 1 and column not in duplicates:
            duplicates.append(column)
    if duplicates:
        raise VisualizationValidationError(
            f"table {label}: duplicate column names {tuple(duplicates)!r}; "
            f"expected unique columns {columns!r}"
        )

    try:
        rows = tuple(table.rows)
    except TypeError as exc:
        raise VisualizationValidationError(
            f"table {label}: 'rows' must be an iterable of row sequences"
        ) from exc

    records: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        if isinstance(row, (str, bytes)):
            raise VisualizationValidationError(
                f"table {label}: row {row_index} must be a sequence of values, "
                f"got {type(row).__name__}"
            )
        try:
            values = tuple(row)
        except TypeError as exc:
            raise VisualizationValidationError(
                f"table {label}: row {row_index} is not iterable"
            ) from exc
        if len(values) != len(columns):
            raise VisualizationValidationError(
                f"table {label}: row {row_index} has {len(values)} value(s); "
                f"expected {len(columns)} to match columns {columns!r}"
            )
        records.append(dict(zip(columns, values)))
    return tuple(records)


def rows_as_dicts(table: Any) -> tuple[dict[str, Any], ...]:
    """Convert an immutable EdaTable into a sequence of fresh row dictionaries.

    Original values and types are preserved. Duplicate columns, non-iterable
    rows and rows whose length differs from the column count are rejected.
    """
    fallback = getattr(table, "name", None)
    label = (
        f"{fallback!r}"
        if isinstance(fallback, str) and fallback
        else type(table).__name__
    )
    return _rows_as_dicts(table, label)


def _get_report_group(report: Any, group_name: str) -> Mapping[str, Any]:
    if not hasattr(report, group_name):
        raise VisualizationValidationError(
            f"report field {group_name!r}: missing required EDA table group"
        )
    group = getattr(report, group_name)
    if not isinstance(group, MappingABC):
        raise VisualizationValidationError(
            f"report field {group_name!r}: expected a mapping of tables, "
            f"got {type(group).__name__}"
        )
    return group


def _get_table(report: Any, group_name: str, table_name: str) -> Any:
    group = _get_report_group(report, group_name)
    if table_name not in group:
        raise VisualizationValidationError(
            f"report field {group_name!r}: missing required table {table_name!r}"
        )
    table = group[table_name]
    if not hasattr(table, "columns") or not hasattr(table, "rows"):
        raise VisualizationValidationError(
            f"table {table_name!r} in report field {group_name!r}: "
            "expected an EdaTable with 'columns' and 'rows'"
        )
    return table


def _validate_columns(table: Any, table_name: str, expected: tuple[str, ...]) -> None:
    try:
        actual = tuple(table.columns)
    except TypeError as exc:
        raise VisualizationValidationError(
            f"table {table_name!r} column 'columns': expected an iterable of names"
        ) from exc
    if actual == expected:
        return

    details: list[str] = []
    if len(actual) == len(expected):
        index = next(
            index
            for index, (expected_name, actual_name) in enumerate(
                zip(expected, actual)
            )
            if expected_name != actual_name
        )
        details.append(
            f"column {index}: expected {expected[index]!r}, got {actual[index]!r}"
        )
    else:
        missing = tuple(column for column in expected if column not in actual)
        unexpected = tuple(column for column in actual if column not in expected)
        if missing:
            details.append(f"missing columns {missing!r}")
        if unexpected:
            details.append(f"unexpected columns {unexpected!r}")
        details.append(f"expected {len(expected)} columns, got {len(actual)}")
    raise VisualizationValidationError(
        f"table {table_name!r}: column schema mismatch; {'; '.join(details)}; "
        f"expected {expected!r}, got {actual!r}"
    )


def _validate_metadata(table: Any, table_name: str) -> None:
    metadata = getattr(table, "metadata", None)
    if not isinstance(metadata, MappingABC):
        raise VisualizationValidationError(
            f"table {table_name!r} metadata: expected a mapping, "
            f"got {type(metadata).__name__}"
        )

    expected_fields: tuple[tuple[str, Any], ...] = (
        ("revenue_warning_label", REVENUE_WARNING_LABEL),
        ("revenue_scope_verified", REVENUE_SCOPE_VERIFIED),
    )
    if table_name == "bov_comparison_scatter":
        expected_fields += (("gap_reference_pct", GAP_REFERENCE_PCT),)

    for field, expected in expected_fields:
        if field not in metadata:
            raise VisualizationValidationError(
                f"table {table_name!r} metadata field {field!r}: missing; "
                f"expected {expected!r}"
            )
        actual = metadata[field]
        invalid = (
            actual is not False
            if field == "revenue_scope_verified" and expected is False
            else actual != expected
        )
        if invalid:
            raise VisualizationValidationError(
                f"table {table_name!r} metadata field {field!r}: "
                f"expected {expected!r}, got {actual!r}"
            )


def _validate_schema(table: Any, table_name: str) -> None:
    _validate_columns(table, table_name, _REQUIRED_COLUMNS[table_name])
    _validate_metadata(table, table_name)


def _expect_population(
    table_name: str, field: str, actual: Any, expected: Any
) -> None:
    if actual != expected:
        raise VisualizationValidationError(
            f"table {table_name!r} population for {field!r}: "
            f"expected {expected!r}, got {actual!r}"
        )


def _sum_column(
    table_name: str, records: tuple[dict[str, Any], ...], column: str
) -> int:
    try:
        return sum(record[column] for record in records)
    except KeyError as exc:
        raise VisualizationValidationError(
            f"table {table_name!r} column {column!r}: missing while checking population"
        ) from exc
    except TypeError as exc:
        raise VisualizationValidationError(
            f"table {table_name!r} column {column!r}: values must be numeric "
            "for a population sum"
        ) from exc


def _metric_values(
    table_name: str, records: tuple[dict[str, Any], ...]
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for record in records:
        metric = record.get("metric")
        if not isinstance(metric, str) or not metric:
            raise VisualizationValidationError(
                f"table {table_name!r} column 'metric': expected a non-empty string, "
                f"got {metric!r}"
            )
        if metric in metrics:
            raise VisualizationValidationError(
                f"table {table_name!r} column 'metric': duplicate metric {metric!r}"
            )
        metrics[metric] = record.get("value")
    return metrics


def validate_visualization_report(report: Any) -> VisualizationValidationResult:
    """Validate an EdaReport without repairing or recalculating any EDA value."""
    row_count = getattr(report, "row_count", None)
    if row_count != EXPECTED_MOVIE_COUNT:
        raise VisualizationValidationError(
            f"report field 'row_count': expected {EXPECTED_MOVIE_COUNT}, got {row_count!r}"
        )
    column_count = getattr(report, "column_count", None)
    if column_count != EXPECTED_COLUMN_COUNT:
        raise VisualizationValidationError(
            f"report field 'column_count': expected {EXPECTED_COLUMN_COUNT}, "
            f"got {column_count!r}"
        )

    chart_tables: dict[str, Any] = {}
    for table_name in CHART_TABLE_NAMES:
        table = _get_table(report, "chart_data", table_name)
        _validate_schema(table, table_name)
        chart_tables[table_name] = table

    revenue_tables: dict[str, Any] = {}
    for table_name in REVENUE_TABLE_NAMES:
        table = _get_table(report, "tables", table_name)
        _validate_schema(table, table_name)
        revenue_tables[table_name] = table

    revenue_summary_tables: dict[str, Any] = {}
    for table_name in REVENUE_SUMMARY_NAMES:
        table = _get_table(report, "summaries", table_name)
        _validate_schema(table, table_name)
        revenue_summary_tables[table_name] = table

    chart_records = {
        table_name: _rows_as_dicts(
            table, _table_label(table, table_name)
        )
        for table_name, table in chart_tables.items()
    }
    revenue_records = {
        table_name: _rows_as_dicts(
            table, _table_label(table, table_name)
        )
        for table_name, table in revenue_tables.items()
    }
    population_records = {
        table_name: _rows_as_dicts(
            table, _table_label(table, table_name)
        )
        for table_name, table in revenue_summary_tables.items()
    }

    _expect_population(
        "movie_match_status_donut",
        "movie_count sum",
        _sum_column("movie_match_status_donut", chart_records["movie_match_status_donut"], "movie_count"),
        EXPECTED_MOVIE_COUNT,
    )
    _expect_population(
        "release_year_histogram",
        "movie_count sum",
        _sum_column("release_year_histogram", chart_records["release_year_histogram"], "movie_count"),
        EXPECTED_MOVIE_COUNT,
    )
    _expect_population(
        "release_year_match_status_stacked",
        "movie_count sum",
        _sum_column(
            "release_year_match_status_stacked",
            chart_records["release_year_match_status_stacked"],
            "movie_count",
        ),
        EXPECTED_MOVIE_COUNT,
    )

    director_records = chart_records["director_profile_bar"]
    _expect_population(
        "director_profile_bar", "row count", len(director_records), EXPECTED_DIRECTOR_ROWS
    )
    _expect_population(
        "director_profile_bar",
        "director_count sum",
        _sum_column("director_profile_bar", director_records, "director_count"),
        EXPECTED_DIRECTOR_COUNT_SUM,
    )
    _expect_population(
        "independent_data_quality_flags",
        "row count",
        len(chart_records["independent_data_quality_flags"]),
        EXPECTED_FLAG_ROWS,
    )
    _expect_population(
        "dtp_revenue_histogram",
        "movie_count sum",
        _sum_column("dtp_revenue_histogram", chart_records["dtp_revenue_histogram"], "movie_count"),
        EXPECTED_DTP_ROUNDED_ROWS,
    )

    population_metrics = _metric_values(
        "dtp_revenue_population", population_records["dtp_revenue_population"]
    )
    for metric, expected in _EXPECTED_POPULATION_METRICS.items():
        actual = population_metrics.get(metric, _MISSING)
        if actual is _MISSING:
            raise VisualizationValidationError(
                f"table 'dtp_revenue_population' column 'metric': "
                f"missing expected metric {metric!r}"
            )
        if actual != expected:
            raise VisualizationValidationError(
                f"table 'dtp_revenue_population' metric {metric!r}: "
                f"expected {expected!r}, got {actual!r}"
            )

    lower_records = revenue_records["lower_bound_revenue_table"]
    lower_ids = tuple(record["movie_id"] for record in lower_records)
    if len(lower_ids) != len(LOWER_BOUND_IDS) or set(lower_ids) != set(LOWER_BOUND_IDS):
        raise VisualizationValidationError(
            "table 'lower_bound_revenue_table' column 'movie_id': "
            f"expected exactly {LOWER_BOUND_IDS!r}, got {lower_ids!r}"
        )
    for record in lower_records:
        display_value = record["display_value"]
        if not isinstance(display_value, str) or not display_value.startswith("≥"):
            raise VisualizationValidationError(
                "table 'lower_bound_revenue_table' column 'display_value' for "
                f"movie_id {record['movie_id']!r}: expected a string beginning '≥', "
                f"got {display_value!r}"
            )

    scatter_records = chart_records["bov_comparison_scatter"]
    _expect_population(
        "bov_comparison_scatter",
        "row count",
        len(scatter_records),
        EXPECTED_SCATTER_ROWS,
    )
    scatter_ids = tuple(record["movie_id"] for record in scatter_records)
    present_exclusions = tuple(
        movie_id
        for movie_id in dict.fromkeys(scatter_ids)
        if movie_id in _EXPECTED_SCATTER_EXCLUSIONS
    )
    if present_exclusions:
        raise VisualizationValidationError(
            "table 'bov_comparison_scatter' column 'movie_id': "
            f"expected exclusions {_EXPECTED_SCATTER_EXCLUSIONS!r}, "
            f"found {present_exclusions!r}"
        )
    for movie_id in ACCEPTED_HIGH_PRIORITY_IDS:
        matches = tuple(
            record for record in scatter_records if record["movie_id"] == movie_id
        )
        if len(matches) != 1:
            raise VisualizationValidationError(
                "table 'bov_comparison_scatter' column 'movie_id': "
                f"expected exactly one retained row for high-priority {movie_id!r}, "
                f"got {len(matches)}"
            )
        priority = matches[0]["review_priority"]
        if priority != "high":
            raise VisualizationValidationError(
                "table 'bov_comparison_scatter' row with movie_id "
                f"{movie_id!r} column 'review_priority': expected 'high', "
                f"got {priority!r}"
            )

    return VisualizationValidationResult(
        validated_movie_count=EXPECTED_MOVIE_COUNT,
        validated_chart_table_names=CHART_TABLE_NAMES,
        validated_revenue_table_names=REVENUE_TABLE_NAMES,
        validation_status=VALIDATION_STATUS,
    )


__all__ = [
    "VisualizationValidationError",
    "VisualizationValidationResult",
    "rows_as_dicts",
    "validate_visualization_report",
]
