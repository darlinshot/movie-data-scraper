"""Read-only, standard-library EDA over the approved analytics CSV.

This module never reloads raw scraper data, never writes files, never renders
charts and never creates another analytical dataset. All chart-ready outputs
are immutable tables that can be inspected directly or recreated manually in
Power BI.
"""

from __future__ import annotations

import csv
import importlib.util
import math
import re
import sys
from collections import Counter
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Iterable, Mapping


def _load_schema_module() -> ModuleType:
    schema_path = Path(__file__).resolve().with_name("schema.py")
    spec = importlib.util.spec_from_file_location(
        "analytics_schema_for_eda", schema_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load analytics schema from {schema_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


schema = _load_schema_module()

REVENUE_WARNING_LABEL = "Exploratory — revenue scope unverified"
EXPLORATORY_WARNING = REVENUE_WARNING_LABEL
REVENUE_SCOPE_VERIFIED = False
GENRE_TOKEN_DELIMITER = "|"
GAP_REFERENCE_PCT = 10

QUARANTINED_MOVIE_ID = "M0016"
CANDIDATE_MOVIE_ID = "M0043"
ACCEPTED_HIGH_PRIORITY_IDS: tuple[str, ...] = (
    "M0020",
    "M0029",
    "M0030",
    "M0077",
)
LOWER_BOUND_IDS: tuple[str, ...] = ("M0001", "M0024")
PENDING_WORKFLOW_IDS: tuple[str, ...] = (
    QUARANTINED_MOVIE_ID,
    "M0020",
    "M0029",
    "M0030",
    CANDIDATE_MOVIE_ID,
    "M0077",
)

_REVENUE_WARNING_METADATA: Mapping[str, Any] = MappingProxyType(
    {
        "revenue_warning_label": REVENUE_WARNING_LABEL,
        "revenue_scope_verified": REVENUE_SCOPE_VERIFIED,
    }
)
_REVENUE_COMPARISON_METADATA: Mapping[str, Any] = MappingProxyType(
    {
        **_REVENUE_WARNING_METADATA,
        "gap_reference_pct": GAP_REFERENCE_PCT,
    }
)

# The real genre_token_path values use "|" and contain no outer whitespace in
# tokens. Tokens are split on that delimiter and empty tokens are ignored; no
# trimming, renaming or genre grouping is performed.
_GENRE_DELIMITER = GENRE_TOKEN_DELIMITER

_INTEGER_FIELDS = frozenset(
    {
        "release_year",
        "raw_source_row_dtp",
        "mapping_human_reviewed",
        "dtp_revenue_vnd",
        "bov_revenue_vnd",
        "bov_quarantined_revenue_vnd",
        "bov_candidate_revenue_vnd",
        "magnitude_gap_warning",
        "revenue_conflict_flag",
        "revenue_scope_verified",
        "bov_evidence_available",
        "include_revenue_comparison",
        "include_revenue_eda",
        "ticket_candidate_count",
        "ticket_found_count",
        "ticket_needs_review_count",
        "ticket_verified_admissions",
        "has_missing_core_data",
        "has_revenue_gap_warning",
        "has_pending_review",
    }
)
_FLOAT_FIELDS = frozenset({"match_score", "revenue_gap_pct"})

_FLAG_FIELDS: tuple[str, ...] = (
    "has_missing_core_data",
    "has_revenue_gap_warning",
    "has_pending_review",
    "magnitude_gap_warning",
    "revenue_conflict_flag",
    "revenue_scope_verified",
    "bov_evidence_available",
    "include_revenue_comparison",
    "include_revenue_eda",
    "mapping_human_reviewed",
)

_STATUS_ORDER: tuple[str, ...] = tuple(schema.MATCH_STATUS_EXPECTED_COUNTS)

# Display labels are humanizations of stored values only. They never replace
# the original machine-readable field beside them.
_FLAG_LABELS: Mapping[str, str] = MappingProxyType(
    {
        "has_missing_core_data": "Has missing core data",
        "has_revenue_gap_warning": "Has revenue gap warning",
        "has_pending_review": "Has pending review",
        "magnitude_gap_warning": "Magnitude gap warning",
        "revenue_conflict_flag": "Revenue conflict flag",
        "revenue_scope_verified": "Revenue scope verified",
        "bov_evidence_available": "BOV evidence available",
        "include_revenue_comparison": "Included in revenue comparison",
        "include_revenue_eda": "Included in revenue EDA",
        "mapping_human_reviewed": "Mapping human reviewed",
        "review_priority_high": "High review priority",
    }
)
_GAP_CATEGORY_LABELS: Mapping[str, str] = MappingProxyType(
    {
        "valid_comparison_warning": "Valid comparison warning",
        "candidate_hold_warning_only": "Candidate-held warning only",
        "above_10pct_warning": "Above 10% reference warning",
        "within_10pct_reference": "Within 10% reference",
    }
)
_MAPPING_STATUS_LABELS: Mapping[str, str] = MappingProxyType(
    {
        "matcher_accepted": "Matcher accepted",
        "known_false_positive_quarantined": "Known false positive, quarantined",
        "candidate_held": "Candidate held, not accepted",
        "no_mapping": "No mapping",
        "no_match": "No match",
    }
)
_REVIEW_STATUS_LABELS: Mapping[str, str] = MappingProxyType(
    {
        "auto_accepted": "Automatically accepted",
        "pending": "Pending review",
        "needs_review": "Needs review",
        "not_applicable": "Not applicable",
        "not_found": "Not found",
    }
)
_REVIEW_PRIORITY_LABELS: Mapping[str, str] = MappingProxyType(
    {
        "high": "High",
        "normal": "Normal",
    }
)

# Fixed display bins in billions of VND. They are presentation buckets only;
# no revenue model, fit, trend or inference is calculated.
_DTP_BINS: tuple[tuple[str, int, int | None], ...] = (
    ("under_10b", 0, 10_000_000_000),
    ("10b_to_under_50b", 10_000_000_000, 50_000_000_000),
    ("50b_to_under_100b", 50_000_000_000, 100_000_000_000),
    ("100b_to_under_200b", 100_000_000_000, 200_000_000_000),
    ("200b_to_under_400b", 200_000_000_000, 400_000_000_000),
    ("400b_or_more", 400_000_000_000, None),
)


class EdaError(ValueError):
    """Base class for EDA loading and validation failures."""


class EdaValidationError(EdaError):
    """The CSV or supplied rows do not satisfy the approved dataset contract."""


@dataclass(frozen=True)
class EdaTable:
    """One immutable, chart-ready or evidence-ready table."""

    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    population: str
    filters: tuple[str, ...]
    exclusions: tuple[str, ...]
    notes: tuple[str, ...]
    metadata: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )


@dataclass(frozen=True)
class EdaReport:
    """Immutable bundle of all approved EDA outputs."""

    source_path: Path | None
    row_count: int
    column_count: int
    summaries: Mapping[str, EdaTable]
    chart_data: Mapping[str, EdaTable]
    tables: Mapping[str, EdaTable]
    warnings: tuple[str, ...]


def _parse_cell(field: str, value: str) -> Any:
    if value == "":
        return None
    if field in _INTEGER_FIELDS:
        try:
            return int(value)
        except ValueError as exc:
            raise EdaValidationError(
                f"field {field!r} is not a valid integer: {value!r}"
            ) from exc
    if field in _FLOAT_FIELDS:
        try:
            parsed = float(value)
        except ValueError as exc:
            raise EdaValidationError(
                f"field {field!r} is not a valid number: {value!r}"
            ) from exc
        if not math.isfinite(parsed):
            raise EdaValidationError(f"field {field!r} is not finite: {value!r}")
        return parsed
    return value


def _validate_dataset_rows(rows: Any) -> tuple[dict[str, Any], ...]:
    try:
        dataset = tuple(rows)
    except TypeError as exc:
        raise EdaValidationError("rows must be an iterable of mappings") from exc

    if len(dataset) != schema.EXPECTED_MOVIE_COUNT:
        raise EdaValidationError(
            f"expected {schema.EXPECTED_MOVIE_COUNT} rows, got {len(dataset)}"
        )

    for index, row in enumerate(dataset):
        if not isinstance(row, MappingABC):
            raise EdaValidationError(
                f"row {index} must be a mapping, got {type(row).__name__}"
            )
        columns = tuple(row.keys())
        if columns != schema.FINAL_COLUMNS:
            raise EdaValidationError(
                f"row {index} columns do not match the approved schema: {columns!r}"
            )

    ids = tuple(row["movie_id"] for row in dataset)
    invalid_ids = tuple(
        movie_id
        for movie_id in ids
        if not isinstance(movie_id, str)
        or re.fullmatch(schema.MOVIE_ID_PATTERN, movie_id) is None
    )
    if invalid_ids:
        raise EdaValidationError(f"invalid movie_id values: {invalid_ids!r}")
    if len(set(ids)) != len(ids):
        duplicates = tuple(
            movie_id for movie_id in dict.fromkeys(ids) if ids.count(movie_id) > 1
        )
        raise EdaValidationError(f"duplicate movie_id values: {duplicates!r}")
    return dataset


def load_eda_dataset(path: str | Path | None = None) -> tuple[dict[str, Any], ...]:
    """Load and validate the single approved CSV without writing any file."""
    source = (
        Path(path) if path is not None else Path(schema.MOVIE_ANALYTICS_CSV_PATH)
    )
    if not source.is_file():
        raise EdaValidationError(f"missing analytical CSV: {source}")

    with source.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = tuple(reader.fieldnames or ())
        if header != schema.FINAL_COLUMNS:
            raise EdaValidationError(
                f"{source}: header must match schema.FINAL_COLUMNS exactly; got {header!r}"
            )

        rows: list[dict[str, Any]] = []
        for line_number, raw_row in enumerate(reader, start=2):
            if None in raw_row:
                raise EdaValidationError(
                    f"{source}: line {line_number} has extra CSV fields"
                )
            if any(value is None for value in raw_row.values()):
                raise EdaValidationError(
                    f"{source}: line {line_number} is missing CSV fields"
                )
            rows.append(
                {
                    field: _parse_cell(field, raw_row[field])
                    for field in schema.FINAL_COLUMNS
                }
            )

    return _validate_dataset_rows(rows)


def _table(
    name: str,
    columns: tuple[str, ...],
    rows: Iterable[tuple[Any, ...]],
    population: str,
    filters: tuple[str, ...] = (),
    exclusions: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
    metadata: Mapping[str, Any] | None = None,
) -> EdaTable:
    resolved_metadata = _REVENUE_WARNING_METADATA if metadata is None else metadata
    return EdaTable(
        name=name,
        columns=columns,
        rows=tuple(tuple(row) for row in rows),
        population=population,
        filters=tuple(filters),
        exclusions=tuple(exclusions),
        notes=tuple(notes),
        metadata=MappingProxyType(dict(resolved_metadata)),
    )


def _is_missing(value: Any) -> bool:
    return value is None or value == ""


def _display_label(value: Any, labels: Mapping[str, str]) -> str | None:
    if _is_missing(value):
        return None
    text = str(value)
    if text in labels:
        return labels[text]
    return text.replace("_", " ").capitalize()


def _as_int(value: Any) -> int | None:
    if _is_missing(value):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _as_float(value: Any) -> float | None:
    if _is_missing(value):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def _is_true_flag(value: Any) -> bool:
    parsed = _as_int(value)
    return parsed == 1


def _status_order(values: Iterable[Any]) -> tuple[Any, ...]:
    seen = tuple(dict.fromkeys(values))
    leading = tuple(status for status in _STATUS_ORDER if status in seen)
    trailing = tuple(value for value in seen if value not in leading)
    return leading + trailing


def _year_sort_key(year: Any) -> tuple[int, int]:
    if _is_missing(year):
        return (1, 0)
    parsed = _as_int(year)
    return (0, parsed if parsed is not None else 0)


def headline_kpis(rows: Any) -> EdaTable:
    """Return approved descriptive KPIs only."""
    dataset = _validate_dataset_rows(rows)
    statuses = Counter(row["bov_match_status"] for row in dataset)
    years = Counter(_as_int(row["release_year"]) for row in dataset)
    genres = {row["genre_raw"] for row in dataset if not _is_missing(row["genre_raw"])}
    directors = {
        row["director_raw"] for row in dataset if not _is_missing(row["director_raw"])
    }
    dtp_quality = Counter(row["dtp_revenue_quality"] for row in dataset)
    mapping_status = Counter(row["mapping_validation_status"] for row in dataset)
    data_quality = Counter(row["data_quality_status"] for row in dataset)

    accepted_bov = sum(
        not _is_missing(row["bov_revenue_vnd"]) for row in dataset
    )
    quarantined = sum(
        not _is_missing(row["bov_quarantined_revenue_vnd"]) for row in dataset
    )
    candidate = sum(
        not _is_missing(row["bov_candidate_revenue_vnd"]) for row in dataset
    )
    comparisons = sum(_is_true_flag(row["include_revenue_comparison"]) for row in dataset)
    gap_warnings = sum(_is_true_flag(row["magnitude_gap_warning"]) for row in dataset)
    conflicts = sum(_is_true_flag(row["revenue_conflict_flag"]) for row in dataset)
    tickets = sum(_as_int(row["ticket_candidate_count"]) or 0 for row in dataset)
    found = sum(_as_int(row["ticket_found_count"]) or 0 for row in dataset)
    needs_review = sum(
        _as_int(row["ticket_needs_review_count"]) or 0 for row in dataset
    )
    verified_values_present = sum(
        not _is_missing(row["ticket_verified_admissions"]) for row in dataset
    )
    pending = sum(_is_true_flag(row["has_pending_review"]) for row in dataset)
    high_priority = sum(row["review_priority"] == "high" for row in dataset)

    metrics: tuple[tuple[str, Any, str], ...] = (
        ("movies", len(dataset), "One row per stable movie_id."),
        ("matched", statuses.get("matched", 0), "Diagnostic matcher result only."),
        (
            "needs_review",
            statuses.get("needs_review", 0),
            "Matcher needs review; not a human decision.",
        ),
        ("not_found", statuses.get("not_found", 0), "No BOV match found."),
        (
            "movies_labelled_2026",
            years.get(2026, 0),
            "Year-only label; no verified release date.",
        ),
        ("distinct_raw_genres", len(genres), "Verbatim genre_raw strings."),
        ("distinct_directors", len(directors), "Non-missing director_raw values."),
        (
            "missing_directors",
            sum(_is_missing(row["director_raw"]) for row in dataset),
            "Missing means unknown, not zero directors.",
        ),
        ("dtp_rounded_rows", dtp_quality.get("rounded", 0), "Rounded DTP display values."),
        (
            "dtp_lower_bound_rows",
            dtp_quality.get("lower_bound", 0),
            "Lower bounds are not exact values.",
        ),
        (
            "stored_bov_revenue_rows",
            accepted_bov + quarantined,
            "Accepted plus quarantined BOV revenue observations.",
        ),
        ("accepted_bov_revenue_rows", accepted_bov, "Separate from DTP revenue."),
        ("quarantined_bov_rows", quarantined, "Quarantined evidence, never accepted."),
        ("candidate_held_bov_rows", candidate, "Candidate-held, never accepted."),
        ("comparison_rows", comparisons, "Rows eligible for diagnostic BOV comparison."),
        ("gap_warning_rows", gap_warnings, "Numerical warnings, not confirmed conflicts."),
        ("confirmed_conflict_rows", conflicts, "No verified scope today."),
        ("ticket_candidate_rows", tickets, "Evidence rows, not admissions."),
        ("ticket_found_rows", found, "Heuristic candidate status."),
        ("ticket_needs_review_rows", needs_review, "Heuristic candidate status."),
        (
            "verified_admission_values_present",
            verified_values_present,
            "NULL is missing evidence, not zero admissions.",
        ),
        ("pending_workflow_rows", pending, "Workflow state, not human review."),
        ("high_priority_rows", high_priority, "Audit priority flag."),
        (
            "mapping_matcher_accepted_rows",
            mapping_status.get("matcher_accepted", 0),
            "Matcher-only mapping state.",
        ),
        (
            "data_quality_pending_review_rows",
            data_quality.get("pending_review", 0),
            "Highest-precedence derived status.",
        ),
    )
    return _table(
        "headline_kpis",
        ("metric", "value", "population", "notes"),
        ((name, value, "All 92 movies", note) for name, value, note in metrics),
        "All 92 movies",
        notes=(
            REVENUE_WARNING_LABEL,
            "Descriptive counts only; no official revenue or admissions conclusion.",
            "Pending workflow is not a recorded human decision.",
        ),
    )


def movie_status_counts(rows: Any) -> EdaTable:
    dataset = _validate_dataset_rows(rows)
    counts = Counter(row["bov_match_status"] for row in dataset)
    ordered = _status_order((*counts.keys(), *_STATUS_ORDER))
    return _table(
        "movie_status_counts",
        ("bov_match_status", "movie_count"),
        ((status, counts[status]) for status in ordered),
        "All 92 movies",
        notes=("bov_match_status is diagnostic only, not identity proof.",),
    )


def release_year_distribution(rows: Any) -> EdaTable:
    dataset = _validate_dataset_rows(rows)
    counts = Counter(_as_int(row["release_year"]) for row in dataset)
    years = sorted(counts, key=_year_sort_key)
    return _table(
        "release_year_distribution",
        ("release_year", "movie_count"),
        ((year, counts[year]) for year in years),
        "All 92 movies with the year value preserved from the CSV",
        notes=(
            "Year-only precision; no verified month or day.",
            "No revenue series, trend, forecast or year-over-year comparison is represented.",
        ),
    )


def release_year_match_matrix(rows: Any) -> EdaTable:
    dataset = _validate_dataset_rows(rows)
    counts: Counter[tuple[Any, Any]] = Counter(
        (_as_int(row["release_year"]), row["bov_match_status"]) for row in dataset
    )
    years = sorted({year for year, _ in counts}, key=_year_sort_key)
    statuses = _status_order(status for _, status in counts)
    rows_out = (
        (year, status, counts[(year, status)])
        for year in years
        for status in statuses
        if counts[(year, status)] > 0
    )
    return _table(
        "release_year_match_matrix",
        ("release_year", "bov_match_status", "movie_count"),
        rows_out,
        "All 92 movies with the year value preserved from the CSV",
        notes=(
            "Year-only precision; no revenue trend is represented.",
            "bov_match_status is diagnostic only.",
        ),
    )


def genre_token_frequency(rows: Any) -> EdaTable:
    dataset = _validate_dataset_rows(rows)
    counts: Counter[str] = Counter()
    missing_paths = 0
    for row in dataset:
        value = row["genre_token_path"]
        if _is_missing(value):
            missing_paths += 1
            continue
        for token in str(value).split(_GENRE_DELIMITER):
            if token != "":
                counts[token] += 1
    ordered = sorted(counts, key=lambda token: (-counts[token], token))
    return _table(
        "genre_token_frequency",
        ("genre_token", "movie_count"),
        ((token, counts[token]) for token in ordered),
        f"{len(dataset) - missing_paths} rows with a non-empty genre_token_path",
        exclusions=(f"{missing_paths} rows with missing genre_token_path",),
        notes=(
            f"Tokens are split on the stored delimiter {_GENRE_DELIMITER!r}; no grouping is invented.",
            "Token counts are non-additive with movie counts because genre_raw is multi-value.",
        ),
    )


def director_profile(rows: Any) -> EdaTable:
    dataset = _validate_dataset_rows(rows)
    counts: Counter[tuple[str, Any]] = Counter()
    missing = 0
    for row in dataset:
        director = row["director_raw"]
        if _is_missing(director):
            missing += 1
            continue
        counts[(str(director), row["director_norm_key"])] += 1
    ordered = sorted(
        counts, key=lambda key: (-counts[key], str(key[0]), str(key[1]))
    )
    return _table(
        "director_profile",
        ("director_raw", "director_norm_key", "director_count"),
        ((raw, norm, counts[(raw, norm)]) for raw, norm in ordered),
        f"{len(dataset) - missing} rows with a non-missing director_raw",
        exclusions=(f"{missing} rows with missing director_raw",),
        notes=(
            "Raw director strings are preserved; director_norm_key is a grouping aid only.",
            "Missing directors are reported separately and are not counted as a director.",
        ),
    )


def data_quality_summary(rows: Any) -> EdaTable:
    dataset = _validate_dataset_rows(rows)
    counts = Counter(row["data_quality_status"] for row in dataset)
    metrics: tuple[tuple[str, Any, str], ...] = (
        (
            "missing_core_data_rows",
            sum(_is_true_flag(row["has_missing_core_data"]) for row in dataset),
            "Independent flag; does not exclude other flags.",
        ),
        (
            "gap_warning_rows",
            sum(_is_true_flag(row["has_revenue_gap_warning"]) for row in dataset),
            "Numerical warning, not a confirmed conflict.",
        ),
        (
            "pending_review_rows",
            sum(_is_true_flag(row["has_pending_review"]) for row in dataset),
            "Workflow state, not a human decision.",
        ),
        (
            "no_bov_match_rows",
            sum(row["bov_match_status"] == "not_found" for row in dataset),
            "Diagnostic matcher result.",
        ),
        (
            "mapping_human_reviewed_rows",
            sum(_is_true_flag(row["mapping_human_reviewed"]) for row in dataset),
            "No mapping is human-reviewed today.",
        ),
        (
            "mapping_quarantined_rows",
            sum(
                row["mapping_validation_status"]
                == "known_false_positive_quarantined"
                for row in dataset
            ),
            "Quarantined BOV evidence is not accepted.",
        ),
        (
            "mapping_candidate_held_rows",
            sum(
                row["mapping_validation_status"] == "candidate_held"
                for row in dataset
            ),
            "Candidate-held BOV evidence is not accepted.",
        ),
    )
    status_metrics = tuple(
        (f"status_{status}", count, "Derived data_quality_status value.")
        for status, count in sorted(counts.items(), key=lambda item: str(item[0]))
    )
    return _table(
        "data_quality_summary",
        ("metric", "value", "population", "notes"),
        (
            (name, value, "All 92 movies", note)
            for name, value, note in metrics + status_metrics
        ),
        "All 92 movies",
        notes=(
            REVENUE_WARNING_LABEL,
            "Flags are independent and may overlap; no artificial combined score is calculated.",
            "Quarantine is pending, not rejected, and no human review is fabricated.",
        ),
    )


def flag_summary(rows: Any) -> EdaTable:
    dataset = _validate_dataset_rows(rows)
    output: list[tuple[Any, ...]] = []
    for field in _FLAG_FIELDS:
        true_count = sum(_is_true_flag(row[field]) for row in dataset)
        missing_count = sum(_is_missing(row[field]) for row in dataset)
        output.append(
            (
                field,
                _display_label(field, _FLAG_LABELS),
                true_count,
                len(dataset) - true_count - missing_count,
                missing_count,
            )
        )
    high_missing = sum(_is_missing(row["review_priority"]) for row in dataset)
    high_true = sum(row["review_priority"] == "high" for row in dataset)
    output.append(
        (
            "review_priority_high",
            _display_label("review_priority_high", _FLAG_LABELS),
            high_true,
            len(dataset) - high_true - high_missing,
            high_missing,
        )
    )
    return _table(
        "flag_summary",
        ("flag", "flag_label", "true_count", "false_count", "missing_count"),
        output,
        "All 92 movies",
        notes=(
            REVENUE_WARNING_LABEL,
            "Each flag is counted independently; flags are not mutually exclusive.",
            "Missing values remain missing and are not counted as false.",
        ),
    )


def missing_value_summary(rows: Any) -> EdaTable:
    dataset = _validate_dataset_rows(rows)
    return _table(
        "missing_value_summary",
        ("column", "missing_count", "present_count", "total_rows"),
        (
            (
                field,
                sum(_is_missing(row[field]) for row in dataset),
                sum(not _is_missing(row[field]) for row in dataset),
                len(dataset),
            )
            for field in schema.FINAL_COLUMNS
        ),
        "All 92 movies and all 54 approved columns",
        notes=(
            REVENUE_WARNING_LABEL,
            "Empty CSV cells are missing values, not zeros or empty facts.",
        ),
    )


def gap_audit_table(rows: Any) -> EdaTable:
    dataset = _validate_dataset_rows(rows)
    selected = tuple(
        row
        for row in dataset
        if _is_true_flag(row["magnitude_gap_warning"])
        and row["movie_id"] != QUARANTINED_MOVIE_ID
    )
    columns = (
        "movie_id",
        "canonical_title",
        "dtp_revenue_raw",
        "dtp_revenue_vnd",
        "bov_revenue_raw",
        "bov_revenue_vnd",
        "bov_candidate_revenue_raw",
        "bov_candidate_revenue_vnd",
        "revenue_gap_pct",
        "magnitude_gap_warning",
        "include_revenue_comparison",
        "mapping_validation_status",
        "mapping_validation_status_label",
        "review_status",
        "review_status_label",
        "review_priority",
        "review_priority_label",
        "warning_type",
        "warning_type_label",
        "evidence_note",
    )
    output: list[tuple[Any, ...]] = []
    for row in sorted(selected, key=lambda row: str(row["movie_id"])):
        candidate = not _is_missing(row["bov_candidate_revenue_vnd"])
        warning_type = (
            "candidate_hold_warning_only" if candidate else "valid_comparison_warning"
        )
        note = (
            "Candidate-held warning only; revenue_gap_pct is missing and no BOV value is accepted."
            if candidate
            else "Numerical gap warning; scope remains unverified and no conflict is confirmed."
        )
        output.append(
            (
                row["movie_id"],
                row["canonical_title"],
                row["dtp_revenue_raw"],
                row["dtp_revenue_vnd"],
                row["bov_revenue_raw"],
                row["bov_revenue_vnd"],
                row["bov_candidate_revenue_raw"],
                row["bov_candidate_revenue_vnd"],
                row["revenue_gap_pct"],
                row["magnitude_gap_warning"],
                row["include_revenue_comparison"],
                row["mapping_validation_status"],
                _display_label(
                    row["mapping_validation_status"], _MAPPING_STATUS_LABELS
                ),
                row["review_status"],
                _display_label(row["review_status"], _REVIEW_STATUS_LABELS),
                row["review_priority"],
                _display_label(row["review_priority"], _REVIEW_PRIORITY_LABELS),
                warning_type,
                _display_label(warning_type, _GAP_CATEGORY_LABELS),
                note,
            )
        )
    return _table(
        "gap_audit_table",
        columns,
        output,
        f"{len(output)} rows with magnitude_gap_warning=1, excluding {QUARANTINED_MOVIE_ID}",
        filters=("magnitude_gap_warning == 1",),
        exclusions=(f"{QUARANTINED_MOVIE_ID} is quarantined from gap calculation",),
        notes=(
            REVENUE_WARNING_LABEL,
            "20 valid comparison warnings plus 1 candidate-only warning.",
            "Gaps are numerical warnings, not confirmed conflicts.",
            f"{GAP_REFERENCE_PCT}% is reference metadata only; it is not a statistical threshold or proof of conflict.",
        ),
        metadata=_REVENUE_COMPARISON_METADATA,
    )


def quarantine_audit_table(rows: Any) -> EdaTable:
    dataset = _validate_dataset_rows(rows)
    selected = tuple(
        row
        for row in dataset
        if row["movie_id"] == QUARANTINED_MOVIE_ID
        or not _is_missing(row["bov_quarantined_revenue_vnd"])
        or not _is_missing(row["bov_quarantined_revenue_raw"])
    )
    columns = (
        "movie_id",
        "canonical_title",
        "raw_source_row_dtp",
        "bov_url",
        "bov_title_raw",
        "bov_quarantined_revenue_raw",
        "bov_quarantined_revenue_vnd",
        "bov_revenue_raw",
        "bov_revenue_vnd",
        "bov_match_status",
        "bov_match_status_label",
        "mapping_validation_status",
        "mapping_validation_status_label",
        "mapping_validation_reason",
        "review_status",
        "review_status_label",
        "review_priority",
        "review_priority_label",
        "include_revenue_comparison",
        "audit_note",
    )
    output = tuple(
        (
            row["movie_id"],
            row["canonical_title"],
            row["raw_source_row_dtp"],
            row["bov_url"],
            row["bov_title_raw"],
            row["bov_quarantined_revenue_raw"],
            row["bov_quarantined_revenue_vnd"],
            row["bov_revenue_raw"],
            row["bov_revenue_vnd"],
            row["bov_match_status"],
            _display_label(row["bov_match_status"], _REVIEW_STATUS_LABELS),
            row["mapping_validation_status"],
            _display_label(
                row["mapping_validation_status"], _MAPPING_STATUS_LABELS
            ),
            row["mapping_validation_reason"],
            row["review_status"],
            _display_label(row["review_status"], _REVIEW_STATUS_LABELS),
            row["review_priority"],
            _display_label(row["review_priority"], _REVIEW_PRIORITY_LABELS),
            row["include_revenue_comparison"],
            "Known sequel-number false positive; pending, not rejected; BOV value retained only as quarantined evidence.",
        )
        for row in sorted(selected, key=lambda row: str(row["movie_id"]))
    )
    return _table(
        "quarantine_audit_table",
        columns,
        output,
        f"{len(output)} quarantined BOV evidence row(s)",
        filters=("bov_quarantined_revenue_raw or bov_quarantined_revenue_vnd is present",),
        notes=(
            REVENUE_WARNING_LABEL,
            "Quarantined BOV revenue never enters accepted comparison, scatter or gap calculation.",
            "The movie remains in the base universe; only its BOV evidence is quarantined.",
        ),
    )


def ticket_evidence_table(rows: Any) -> EdaTable:
    dataset = _validate_dataset_rows(rows)
    selected = tuple(
        row
        for row in dataset
        if (_as_int(row["ticket_candidate_count"]) or 0) > 0
    )
    columns = (
        "movie_id",
        "canonical_title",
        "ticket_candidate_count",
        "ticket_found_count",
        "ticket_needs_review_count",
        "ticket_data_status",
        "ticket_context_status",
        "ticket_evidence_urls",
        "ticket_verified_admissions",
        "evidence_note",
    )
    output = tuple(
        (
            row["movie_id"],
            row["canonical_title"],
            row["ticket_candidate_count"],
            row["ticket_found_count"],
            row["ticket_needs_review_count"],
            row["ticket_data_status"],
            row["ticket_context_status"],
            row["ticket_evidence_urls"],
            row["ticket_verified_admissions"],
            "Evidence only; no ticket values are summed and no cinema admissions are inferred.",
        )
        for row in sorted(selected, key=lambda row: str(row["movie_id"]))
    )
    return _table(
        "ticket_evidence_table",
        columns,
        output,
        f"{len(output)} movies with at least one deduplicated ticket candidate",
        filters=("ticket_candidate_count > 0",),
        notes=(
            "ticket_verified_admissions remains NULL; NULL is not zero admissions.",
            "event_attendance_quarantined rows are preserved and never treated as cinema attendance.",
        ),
    )


def high_priority_review_table(rows: Any) -> EdaTable:
    dataset = _validate_dataset_rows(rows)
    selected = tuple(
        row
        for row in dataset
        if row["review_priority"] == "high"
        and row["movie_id"] != QUARANTINED_MOVIE_ID
    )
    columns = (
        "movie_id",
        "canonical_title",
        "raw_source_row_dtp",
        "bov_match_status",
        "mapping_validation_status",
        "mapping_validation_reason",
        "review_status",
        "review_priority",
        "include_revenue_comparison",
        "include_revenue_eda",
        "dtp_revenue_raw",
        "dtp_revenue_vnd",
        "dtp_revenue_quality",
        "bov_revenue_raw",
        "bov_revenue_vnd",
        "bov_candidate_revenue_raw",
        "bov_candidate_revenue_vnd",
        "bov_quarantined_revenue_raw",
        "bov_quarantined_revenue_vnd",
        "magnitude_gap_warning",
        "revenue_gap_pct",
    )
    label_columns = (
        "mapping_validation_status_label",
        "review_status_label",
        "review_priority_label",
    )
    output = tuple(
        tuple(row[field] for field in columns)
        + (
            _display_label(
                row["mapping_validation_status"], _MAPPING_STATUS_LABELS
            ),
            _display_label(row["review_status"], _REVIEW_STATUS_LABELS),
            _display_label(row["review_priority"], _REVIEW_PRIORITY_LABELS),
        )
        for row in sorted(selected, key=lambda row: str(row["movie_id"]))
    )
    return _table(
        "high_priority_review_table",
        columns + label_columns,
        output,
        f"{len(output)} high-priority workflow rows",
        filters=("review_priority == 'high'",),
        exclusions=(
            f"{QUARANTINED_MOVIE_ID} BOV evidence appears only in the quarantine audit",
        ),
        notes=(
            REVENUE_WARNING_LABEL,
            "Pending workflow rows are not human review decisions.",
            f"{CANDIDATE_MOVIE_ID} is candidate-held and ineligible for accepted BOV comparison.",
        ),
    )


def pending_workflow_table(rows: Any) -> EdaTable:
    """Return the general pending/high-priority workflow view without BOV values."""
    dataset = _validate_dataset_rows(rows)
    selected = tuple(
        row
        for row in dataset
        if row["movie_id"] in PENDING_WORKFLOW_IDS
        or row["review_priority"] == "high"
        or _is_true_flag(row["has_pending_review"])
        or row["mapping_validation_status"]
        in {"known_false_positive_quarantined", "candidate_held"}
    )
    columns = (
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
    output: list[tuple[Any, ...]] = []
    for row in sorted(selected, key=lambda row: str(row["movie_id"])):
        if row["movie_id"] == QUARANTINED_MOVIE_ID:
            note = (
                "Quarantine status and reason only; no quarantined BOV revenue value "
                "is exposed in this general workflow table."
            )
        elif row["movie_id"] == CANDIDATE_MOVIE_ID:
            note = "Candidate-held mapping; no accepted BOV revenue comparison."
        else:
            note = "Pending or high-priority workflow state; not a recorded human decision."
        output.append(
            (
                row["movie_id"],
                row["canonical_title"],
                row["raw_source_row_dtp"],
                row["bov_match_status"],
                row["mapping_validation_status"],
                _display_label(
                    row["mapping_validation_status"], _MAPPING_STATUS_LABELS
                ),
                row["mapping_validation_reason"],
                row["review_status"],
                _display_label(row["review_status"], _REVIEW_STATUS_LABELS),
                row["review_priority"],
                _display_label(row["review_priority"], _REVIEW_PRIORITY_LABELS),
                row["data_quality_status"],
                row["has_pending_review"],
                row["include_revenue_comparison"],
                row["include_revenue_eda"],
                row["dtp_revenue_raw"],
                row["dtp_revenue_vnd"],
                row["dtp_revenue_quality"],
                note,
            )
        )
    return _table(
        "pending_workflow_table",
        columns,
        output,
        f"{len(output)} pending/high-priority workflow row(s)",
        notes=(
            REVENUE_WARNING_LABEL,
            "Quarantined and candidate-held BOV values remain in their dedicated audit tables.",
            "No BOV revenue value is included in this general workflow view.",
        ),
    )


def lower_bound_revenue_table(rows: Any) -> EdaTable:
    dataset = _validate_dataset_rows(rows)
    selected = tuple(
        row for row in dataset if row["dtp_revenue_quality"] == "lower_bound"
    )
    columns = (
        "movie_id",
        "canonical_title",
        "dtp_revenue_raw",
        "dtp_revenue_vnd",
        "dtp_revenue_quality",
        "display_value",
        "include_revenue_eda",
    )
    output = tuple(
        (
            row["movie_id"],
            row["canonical_title"],
            row["dtp_revenue_raw"],
            row["dtp_revenue_vnd"],
            row["dtp_revenue_quality"],
            f"≥{row['dtp_revenue_vnd']}" if not _is_missing(row["dtp_revenue_vnd"]) else None,
            row["include_revenue_eda"],
        )
        for row in sorted(selected, key=lambda row: str(row["movie_id"]))
    )
    return _table(
        "lower_bound_revenue_table",
        columns,
        output,
        f"{len(output)} lower-bound DTP revenue row(s)",
        filters=("dtp_revenue_quality == 'lower_bound'",),
        notes=(
            REVENUE_WARNING_LABEL,
            "Lower-bound values are shown with ≥ and excluded from the exact-value histogram and diagnostic scatter.",
            "No mean, total or ranking is calculated here.",
        ),
    )


def dtp_revenue_population(rows: Any) -> EdaTable:
    dataset = _validate_dataset_rows(rows)
    eligible = tuple(row for row in dataset if _is_true_flag(row["include_revenue_eda"]))
    lower_bound = tuple(
        row for row in eligible if row["dtp_revenue_quality"] == "lower_bound"
    )
    rounded_exact = tuple(
        row
        for row in eligible
        if row["dtp_revenue_quality"] == "rounded"
        and _as_int(row["dtp_revenue_vnd"]) is not None
    )
    missing_invalid = len(eligible) - len(lower_bound) - len(rounded_exact)
    metrics: tuple[tuple[str, int, str], ...] = (
        ("eligible_rows", len(eligible), "include_revenue_eda == 1"),
        (
            "rounded_exact_rows",
            len(rounded_exact),
            "Rounded quality with a valid numeric dtp_revenue_vnd",
        ),
        ("lower_bound_rows", len(lower_bound), "Shown with ≥; not exact values"),
        (
            "missing_invalid_rows",
            missing_invalid,
            "Missing or invalid values are never treated as zero",
        ),
    )
    return _table(
        "dtp_revenue_population",
        ("metric", "value", "population", "notes"),
        ((name, value, "DTP exploratory population", note) for name, value, note in metrics),
        f"eligible={len(eligible)}, rounded_exact={len(rounded_exact)}, "
        f"lower_bound={len(lower_bound)}, missing_invalid={missing_invalid}",
        filters=(
            "include_revenue_eda == 1",
            "dtp_revenue_quality == 'rounded'",
            "dtp_revenue_vnd is numeric",
        ),
        exclusions=(
            f"{len(lower_bound)} lower-bound row(s) are reported separately with ≥",
            "Missing or invalid values are never treated as zero",
        ),
        notes=(
            REVENUE_WARNING_LABEL,
            "No mean, total, ranking or revenue scope is inferred.",
        ),
    )


def dtp_revenue_distribution(rows: Any) -> EdaTable:
    dataset = _validate_dataset_rows(rows)
    eligible = tuple(row for row in dataset if _is_true_flag(row["include_revenue_eda"]))
    lower_bound = tuple(
        row for row in eligible if row["dtp_revenue_quality"] == "lower_bound"
    )
    rounded_exact = tuple(
        row
        for row in eligible
        if row["dtp_revenue_quality"] == "rounded"
        and _as_int(row["dtp_revenue_vnd"]) is not None
    )
    missing_invalid = len(eligible) - len(lower_bound) - len(rounded_exact)

    output: list[tuple[Any, ...]] = []
    for label, lower, upper in _DTP_BINS:
        count = sum(
            1
            for row in rounded_exact
            if (amount := _as_int(row["dtp_revenue_vnd"])) is not None
            and amount >= lower
            and (upper is None or amount < upper)
        )
        output.append((label, count))

    population = (
        f"eligible={len(eligible)}, rounded_exact={len(rounded_exact)}, "
        f"lower_bound={len(lower_bound)}, missing_invalid={missing_invalid}"
    )
    return _table(
        "dtp_revenue_distribution",
        ("revenue_bin_vnd", "movie_count"),
        output,
        population,
        filters=(
            "include_revenue_eda == 1",
            "dtp_revenue_quality == 'rounded'",
            "dtp_revenue_vnd is numeric",
        ),
        exclusions=(
            f"{len(lower_bound)} lower-bound row(s) are reported in lower_bound_revenue_table with ≥",
            "Missing or invalid values are reported in the population metadata, not binned as zero",
            "No BOV revenue is used",
        ),
        notes=(
            REVENUE_WARNING_LABEL,
            "Fixed display bins only; no mean, total, ranking, fitted line or forecast is calculated.",
            "Only rounded, numeric exact-value observations enter these bins.",
        ),
    )


def bov_comparison_scatter(rows: Any) -> EdaTable:
    dataset = _validate_dataset_rows(rows)
    eligible = tuple(
        row
        for row in dataset
        if _is_true_flag(row["include_revenue_comparison"])
        and row["movie_id"] not in {QUARANTINED_MOVIE_ID, CANDIDATE_MOVIE_ID}
    )
    expected_eligible = int(schema.COMPARISON_ELIGIBLE_ROWS)
    if len(eligible) != expected_eligible:
        raise EdaValidationError(
            f"diagnostic scatter requires exactly {expected_eligible} eligible rows, "
            f"got {len(eligible)}"
        )
    excluded_lower_bound = tuple(
        row for row in eligible if row["movie_id"] in LOWER_BOUND_IDS
    )
    if len(excluded_lower_bound) != len(LOWER_BOUND_IDS):
        raise EdaValidationError(
            f"diagnostic scatter requires {len(LOWER_BOUND_IDS)} eligible lower-bound "
            f"rows to exclude, got {len(excluded_lower_bound)}"
        )
    selected = tuple(
        row for row in eligible if row["movie_id"] not in LOWER_BOUND_IDS
    )
    expected = expected_eligible - len(LOWER_BOUND_IDS)
    if len(selected) != expected:
        raise EdaValidationError(
            f"diagnostic scatter requires exactly {expected} exact-value rows, "
            f"got {len(selected)}"
        )
    for row in selected:
        if _is_missing(row["dtp_revenue_vnd"]) or _is_missing(row["bov_revenue_vnd"]):
            raise EdaValidationError(
                f"{row['movie_id']} has include_revenue_comparison=1 but a missing revenue value"
            )
        if row["dtp_revenue_quality"] != "rounded":
            raise EdaValidationError(
                f"{row['movie_id']} is not a rounded exact-value DTP row"
            )

    columns = (
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
    output: list[tuple[Any, ...]] = []
    for row in sorted(selected, key=lambda row: str(row["movie_id"])):
        gap_band = (
            "above_10pct_warning"
            if _is_true_flag(row["magnitude_gap_warning"])
            else "within_10pct_reference"
        )
        output.append(
            (
                row["movie_id"],
                row["canonical_title"],
                row["dtp_revenue_vnd"],
                row["dtp_revenue_quality"],
                row["bov_revenue_vnd"],
                _as_float(row["revenue_gap_pct"]),
                row["magnitude_gap_warning"],
                gap_band,
                _display_label(gap_band, _GAP_CATEGORY_LABELS),
                row["review_priority"],
                _display_label(row["review_priority"], _REVIEW_PRIORITY_LABELS),
                row["review_status"],
                _display_label(row["review_status"], _REVIEW_STATUS_LABELS),
                row["mapping_validation_status"],
                _display_label(
                    row["mapping_validation_status"], _MAPPING_STATUS_LABELS
                ),
            )
        )
    return _table(
        "bov_comparison_scatter",
        columns,
        output,
        f"{len(selected)} exact-value diagnostic BOV comparison rows "
        f"from {len(eligible)} eligible comparisons",
        filters=(
            "include_revenue_comparison == 1",
            "dtp_revenue_quality == 'rounded'",
        ),
        exclusions=(
            f"{QUARANTINED_MOVIE_ID} quarantined false positive",
            f"{CANDIDATE_MOVIE_ID} candidate-held, warning-only row",
            f"{', '.join(LOWER_BOUND_IDS)} lower-bound DTP values",
        ),
        notes=(
            REVENUE_WARNING_LABEL,
            f"{GAP_REFERENCE_PCT}% magnitude-gap reference only; not a statistical threshold "
            "or proof of conflict; no fitted line or statistical model.",
            "DTP and BOV revenues remain separate columns; all rows remain insufficient_evidence.",
            "Lower-bound DTP rows are excluded here and shown in lower_bound_revenue_table with ≥.",
            "Accepted high-priority rows are included and visibly flagged by review_priority.",
        ),
        metadata=_REVENUE_COMPARISON_METADATA,
    )


def _mapping_proxy(mapping: Mapping[str, EdaTable]) -> Mapping[str, EdaTable]:
    return MappingProxyType(dict(mapping))


def build_eda_report(rows: Any = None, path: str | Path | None = None) -> EdaReport:
    """Build all approved EDA outputs from supplied rows or the approved CSV."""
    if rows is None:
        dataset = load_eda_dataset(path)
        source_path: Path | None = Path(path) if path is not None else Path(
            schema.MOVIE_ANALYTICS_CSV_PATH
        )
    else:
        dataset = _validate_dataset_rows(rows)
        source_path = None

    summaries = {
        "headline_kpis": headline_kpis(dataset),
        "movie_status_counts": movie_status_counts(dataset),
        "release_year_distribution": release_year_distribution(dataset),
        "release_year_match_matrix": release_year_match_matrix(dataset),
        "genre_token_frequency": genre_token_frequency(dataset),
        "director_profile": director_profile(dataset),
        "data_quality_summary": data_quality_summary(dataset),
        "flag_summary": flag_summary(dataset),
        "missing_value_summary": missing_value_summary(dataset),
        "dtp_revenue_population": dtp_revenue_population(dataset),
    }
    chart_data = {
        "movie_match_status_donut": movie_status_counts(dataset),
        "release_year_histogram": release_year_distribution(dataset),
        "release_year_match_status_stacked": release_year_match_matrix(dataset),
        "genre_frequency_bar": genre_token_frequency(dataset),
        "director_profile_bar": director_profile(dataset),
        "independent_data_quality_flags": flag_summary(dataset),
        "dtp_revenue_histogram": dtp_revenue_distribution(dataset),
        "bov_comparison_scatter": bov_comparison_scatter(dataset),
    }
    tables = {
        "gap_audit_table": gap_audit_table(dataset),
        "quarantine_audit_table": quarantine_audit_table(dataset),
        "ticket_evidence_table": ticket_evidence_table(dataset),
        "high_priority_review_table": high_priority_review_table(dataset),
        "pending_workflow_table": pending_workflow_table(dataset),
        "lower_bound_revenue_table": lower_bound_revenue_table(dataset),
    }
    warnings: tuple[str, ...] = (
        REVENUE_WARNING_LABEL,
        "All available DTP records; not a designed sample.",
        f"{GAP_REFERENCE_PCT}% is diagnostic reference metadata only, not a statistical threshold.",
        "Lower-bound DTP values are excluded from exact-value charts and shown separately with ≥.",
        "match_score is fuzzy similarity, not a film rating or identity proof.",
        "Pending workflow rows are not recorded human decisions.",
        "Ticket candidates are evidence only; no admissions, summing, rankings or screening efficiency are produced.",
        "No official revenue, forecast, statistical conclusion or revenue trend by release year is produced.",
    )
    return EdaReport(
        source_path=source_path,
        row_count=len(dataset),
        column_count=len(schema.FINAL_COLUMNS),
        summaries=_mapping_proxy(summaries),
        chart_data=_mapping_proxy(chart_data),
        tables=_mapping_proxy(tables),
        warnings=warnings,
    )


__all__ = [
    "EdaError",
    "EdaReport",
    "EdaTable",
    "EdaValidationError",
    "EXPLORATORY_WARNING",
    "GAP_REFERENCE_PCT",
    "LOWER_BOUND_IDS",
    "PENDING_WORKFLOW_IDS",
    "REVENUE_SCOPE_VERIFIED",
    "REVENUE_WARNING_LABEL",
    "bov_comparison_scatter",
    "build_eda_report",
    "data_quality_summary",
    "director_profile",
    "dtp_revenue_distribution",
    "dtp_revenue_population",
    "flag_summary",
    "gap_audit_table",
    "genre_token_frequency",
    "headline_kpis",
    "high_priority_review_table",
    "load_eda_dataset",
    "lower_bound_revenue_table",
    "missing_value_summary",
    "movie_status_counts",
    "pending_workflow_table",
    "quarantine_audit_table",
    "release_year_distribution",
    "release_year_match_matrix",
    "ticket_evidence_table",
]
