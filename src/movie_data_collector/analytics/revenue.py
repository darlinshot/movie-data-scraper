"""Revenue parsing, segregation and eligibility for the analytics build.

This module is standard-library only. It consumes the existing ``RawInputs``,
``CleanedInputs`` and ``IdAssignmentResult`` shapes without modifying them, and
returns one revenue record per current stable ``movie_id``.

Raw DTP and BOV strings remain separate. BOV classification comes only from the
persistent ``revenue_review`` decision attached to the stable movie ID; no
matcher score, title similarity, physical row position or movie-specific rule is
used to infer acceptance.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from types import ModuleType
from typing import Any


def _load_schema_module() -> ModuleType:
    """Load schema.py directly to avoid the parent CLI/pandas import chain."""
    schema_path = Path(__file__).resolve().with_name("schema.py")
    spec = importlib.util.spec_from_file_location(
        "analytics_schema_for_revenue", schema_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load analytics schema from {schema_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


schema = _load_schema_module()


class RevenueProcessingError(ValueError):
    """Raised when revenue inputs cannot be joined safely by stable movie ID."""


DTP_QUALITY_ROUNDED = "rounded"
DTP_QUALITY_LOWER_BOUND = "lower_bound"
BOV_QUALITY_EXACT = "exact"

REVENUE_REVIEW_DECISIONS = frozenset(
    {"accepted", "quarantined", "candidate_held", "pending"}
)
COMPARABILITY_INSUFFICIENT_EVIDENCE = "insufficient_evidence"
COMPARABILITY_NOT_APPLICABLE = "not_applicable"

GAP_WARNING_THRESHOLD_PCT = 10.0

_LOWER_BOUND_PREFIX = re.compile(r"^(?:hơn|trên|>=|≥|>)\s*", re.IGNORECASE)
_NUMBER_TOKEN = re.compile(r"(?<!\d)(\d[\d.,\s\u00a0]*)(?!\d)")
_K_UNIT = re.compile(r"^k(?:đ|vnd)?$", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedRevenue:
    """One safely parsed raw revenue observation."""

    raw: str | None
    value: int | None
    quality: str | None


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_decimal(token: str) -> Decimal | None:
    """Normalize Vietnamese/English digit grouping without float rounding."""
    candidate = token.replace("\u00a0", " ").replace(" ", "").strip()
    if not candidate or not re.fullmatch(r"[0-9.,]+", candidate):
        return None

    commas = candidate.count(",")
    dots = candidate.count(".")
    if commas and dots:
        decimal_separator = "," if candidate.rfind(",") > candidate.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        trailing = len(candidate) - candidate.rfind(decimal_separator) - 1
        if trailing in (1, 2):
            candidate = candidate.replace(thousands_separator, "")
            candidate = candidate.replace(decimal_separator, ".")
        else:
            candidate = candidate.replace(".", "").replace(",", "")
    elif commas:
        trailing = len(candidate) - candidate.rfind(",") - 1
        if commas == 1 and trailing in (1, 2):
            candidate = candidate.replace(",", ".")
        else:
            candidate = candidate.replace(",", "")
    elif dots:
        trailing = len(candidate) - candidate.rfind(".") - 1
        if dots == 1 and trailing in (1, 2):
            pass
        else:
            candidate = candidate.replace(".", "")

    try:
        return Decimal(candidate)
    except InvalidOperation:
        return None


def _multiplier(unit_text: str) -> int:
    unit = unit_text.strip().lower()
    if "tỷ" in unit or "ty" in unit:
        return 1_000_000_000
    if "triệu" in unit or "trieu" in unit or "mn" in unit:
        return 1_000_000
    if "nghìn" in unit or "nghin" in unit or _K_UNIT.fullmatch(unit):
        return 1_000
    return 1


def _parse_revenue_value(raw: Any, *, allow_lower_bound: bool) -> int | None:
    text = _text(raw)
    if text is None:
        return None
    if not allow_lower_bound and _LOWER_BOUND_PREFIX.match(text):
        return None

    match = _NUMBER_TOKEN.search(text)
    if match is None:
        return None
    number = _normalize_decimal(match.group(1))
    if number is None:
        return None

    multiplier = _multiplier(text[match.end() :])
    try:
        value = number * Decimal(multiplier)
        return int(value.to_integral_value(rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, OverflowError):
        return None


def parse_dtp_revenue(raw: Any) -> ParsedRevenue:
    """Parse a DTP display value while preserving rounded/lower-bound quality."""
    raw_text = raw if isinstance(raw, str) else None
    value = _parse_revenue_value(raw, allow_lower_bound=True)
    if value is None:
        return ParsedRevenue(raw=raw_text, value=None, quality=None)
    text = _text(raw)
    quality = (
        DTP_QUALITY_LOWER_BOUND
        if text is not None and _LOWER_BOUND_PREFIX.match(text)
        else DTP_QUALITY_ROUNDED
    )
    return ParsedRevenue(raw=raw_text, value=value, quality=quality)


def parse_bov_revenue(raw: Any) -> ParsedRevenue:
    """Parse a BOV value; BOV quality is exact or unusable, never lower-bound."""
    raw_text = raw if isinstance(raw, str) else None
    value = _parse_revenue_value(raw, allow_lower_bound=False)
    quality = BOV_QUALITY_EXACT if value is not None else None
    return ParsedRevenue(raw=raw_text, value=value, quality=quality)


def compute_gap_pct(dtp_vnd: Any, bov_vnd: Any) -> float | None:
    """Return the DTP-referenced absolute percentage gap, or None if unusable."""
    if isinstance(dtp_vnd, bool) or isinstance(bov_vnd, bool):
        return None
    if not isinstance(dtp_vnd, int) or not isinstance(bov_vnd, int):
        return None
    if dtp_vnd == 0:
        return None
    return abs(dtp_vnd - bov_vnd) / dtp_vnd * 100.0


def _index_by_url(records: Any, field: str, label: str) -> dict[str, MappingABC[str, Any]]:
    indexed: dict[str, MappingABC[str, Any]] = {}
    if records is None:
        return indexed
    try:
        iterator = iter(records)
    except TypeError as exc:
        raise RevenueProcessingError(f"{label} must be iterable") from exc
    for row in iterator:
        if not isinstance(row, MappingABC):
            raise RevenueProcessingError(f"{label} records must be objects")
        url = _text(row.get(field))
        if url is None:
            raise RevenueProcessingError(f"{label} record is missing {field}")
        if url in indexed:
            raise RevenueProcessingError(f"{label} has duplicate {field}: {url}")
        indexed[url] = row
    return indexed


def _decision_for_mapped_movie(mapped: Any, movie_id: str) -> str | None:
    review = getattr(mapped, "revenue_review", None)
    if review is None:
        return None
    if isinstance(review, MappingABC):
        decision = review.get("decision")
    else:
        decision = getattr(review, "decision", None)
    if not isinstance(decision, str) or decision not in REVENUE_REVIEW_DECISIONS:
        raise RevenueProcessingError(
            f"{movie_id} has an unsupported revenue_review decision: {decision!r}"
        )
    return decision


def _mapped_movies_by_id(id_assignment: Any) -> dict[str, Any]:
    mapping = getattr(id_assignment, "updated_mapping", None)
    if mapping is None:
        raise RevenueProcessingError("id_assignment is missing updated_mapping")
    indexed: dict[str, Any] = {}
    for mapped in getattr(mapping, "movies", ()):
        movie_id = getattr(mapped, "movie_id", None)
        if not isinstance(movie_id, str) or not movie_id:
            raise RevenueProcessingError("mapping record is missing movie_id")
        if movie_id in indexed:
            raise RevenueProcessingError(f"mapping has duplicate movie_id: {movie_id}")
        indexed[movie_id] = mapped
    return indexed


def _boxoffice_evidence(row: MappingABC[str, Any] | None) -> int:
    if row is None:
        return 0
    detail = _text(row.get("_bov_detail_raw"))
    if detail is None:
        return 0
    return 0 if detail.casefold() in {"none", "null", "n/a", "na"} else 1


def _comparability_reason(
    *,
    decision: str | None,
    has_bov_url: bool,
    match_status: str | None,
    bov_raw: str | None,
    bov_parsed: ParsedRevenue,
    dtp_parsed: ParsedRevenue,
) -> str:
    if decision == "quarantined":
        return "mapping_quarantined_false_positive"
    if decision == "candidate_held":
        return "candidate_held"
    if not has_bov_url:
        return "no_bov_mapping"
    if match_status != "matched":
        return "bov_match_not_accepted"
    if bov_raw is None or bov_parsed.value is None:
        return "no_bov_revenue"
    if dtp_parsed.value is None:
        return "no_dtp_revenue"
    if decision == "pending":
        return "pending_revenue_review"
    if decision is None:
        return "missing_revenue_review"
    return "scope_unknown"


def _eda_basis(
    *,
    dtp_parsed: ParsedRevenue,
    eligible: bool,
    gap_pct: float | None,
) -> str | None:
    if dtp_parsed.value is None:
        return None
    if dtp_parsed.quality == DTP_QUALITY_LOWER_BOUND:
        return "dtp_lower_bound"
    if eligible and gap_pct is not None and gap_pct <= GAP_WARNING_THRESHOLD_PCT:
        return "dtp_rounded_numeric_agreement"
    return "dtp_rounded_single_source"


def _build_revenue_record(
    *,
    raw_movie: MappingABC[str, Any],
    match_status: str | None,
    boxoffice_row: MappingABC[str, Any] | None,
    decision: str | None,
) -> dict[str, Any]:
    dtp_parsed = parse_dtp_revenue(raw_movie.get("revenue_doanhthuphim"))
    bov_raw = _text(raw_movie.get("revenue_bovn"))
    bov_parsed = parse_bov_revenue(bov_raw)
    has_bov_url = _text(raw_movie.get("source_url_bovn")) is not None

    accepted_raw: str | None = None
    accepted_value: int | None = None
    accepted_quality: str | None = None
    quarantined_raw: str | None = None
    quarantined_value: int | None = None
    candidate_raw: str | None = None
    candidate_value: int | None = None

    if decision == "quarantined":
        quarantined_raw = bov_raw
        quarantined_value = bov_parsed.value
    elif decision == "candidate_held":
        candidate_raw = bov_raw
        candidate_value = bov_parsed.value
    elif (
        decision == "accepted"
        and has_bov_url
        and match_status == "matched"
        and bov_parsed.value is not None
    ):
        accepted_raw = bov_raw
        accepted_value = bov_parsed.value
        accepted_quality = BOV_QUALITY_EXACT

    eligible = accepted_value is not None and dtp_parsed.value is not None
    gap_pct = (
        compute_gap_pct(dtp_parsed.value, accepted_value) if eligible else None
    )

    magnitude_warning = 0
    if eligible and gap_pct is not None and gap_pct > GAP_WARNING_THRESHOLD_PCT:
        magnitude_warning = 1
    elif (
        decision == "candidate_held"
        and candidate_value is not None
        and dtp_parsed.value is not None
    ):
        candidate_gap = compute_gap_pct(dtp_parsed.value, candidate_value)
        if candidate_gap is not None and candidate_gap > GAP_WARNING_THRESHOLD_PCT:
            magnitude_warning = 1

    reason = _comparability_reason(
        decision=decision,
        has_bov_url=has_bov_url,
        match_status=match_status,
        bov_raw=bov_raw,
        bov_parsed=bov_parsed,
        dtp_parsed=dtp_parsed,
    )

    record = {
        "dtp_revenue_raw": dtp_parsed.raw,
        "dtp_revenue_vnd": dtp_parsed.value,
        "dtp_revenue_quality": dtp_parsed.quality,
        "bov_revenue_raw": accepted_raw,
        "bov_revenue_vnd": accepted_value,
        "bov_revenue_quality": accepted_quality,
        "bov_quarantined_revenue_raw": quarantined_raw,
        "bov_quarantined_revenue_vnd": quarantined_value,
        "bov_candidate_revenue_raw": candidate_raw,
        "bov_candidate_revenue_vnd": candidate_value,
        "revenue_gap_pct": gap_pct,
        "magnitude_gap_warning": magnitude_warning,
        "revenue_conflict_flag": 0,
        "revenue_comparability_class": (
            COMPARABILITY_INSUFFICIENT_EVIDENCE
            if eligible
            else COMPARABILITY_NOT_APPLICABLE
        ),
        "comparability_reason": reason,
        "revenue_scope_verified": 0,
        "bov_evidence_available": _boxoffice_evidence(boxoffice_row),
        "include_revenue_comparison": 1 if eligible else 0,
        "include_revenue_eda": 1 if dtp_parsed.value is not None else 0,
        "revenue_eda_basis": _eda_basis(
            dtp_parsed=dtp_parsed, eligible=eligible, gap_pct=gap_pct
        ),
    }
    return {field: record[field] for field in schema.GROUP_C_REVENUE_COLUMNS}


def process_revenue(
    raw_inputs: Any,
    cleaned_inputs: Any,
    id_assignment: Any,
) -> dict[str, dict[str, Any]]:
    """Return Group C revenue fields keyed by stable ``movie_id``.

    The three inputs are read only. Joining is performed exclusively through the
    exact DTP URL and its assigned stable ID.
    """
    raw_movies = _index_by_url(
        getattr(raw_inputs, "movies", ()),
        "source_url_doanhthuphim",
        "movies.csv",
    )
    boxoffice_rows = _index_by_url(
        getattr(raw_inputs, "boxoffice_matches", ()),
        "source_url_doanhthuphim",
        "boxoffice_matches.jsonl",
    )
    collection_rows = _index_by_url(
        getattr(cleaned_inputs, "collection_log", ()),
        "source_url_doanhthuphim",
        "collection_log.csv",
    )
    assignments = getattr(id_assignment, "movie_ids_by_url", None)
    if not isinstance(assignments, MappingABC):
        raise RevenueProcessingError("id_assignment is missing movie_ids_by_url")
    mapped_by_id = _mapped_movies_by_id(id_assignment)

    cleaned_movies = tuple(getattr(cleaned_inputs, "movies", ()))
    seen_urls: set[str] = set()
    results: dict[str, dict[str, Any]] = {}

    for movie in cleaned_movies:
        url = _text(getattr(movie, "source_url_dtp", None))
        if url is None:
            raise RevenueProcessingError("cleaned movie is missing source_url_dtp")
        if url in seen_urls:
            raise RevenueProcessingError(f"cleaned movies have duplicate URL: {url}")
        seen_urls.add(url)

        movie_id = assignments.get(url)
        if not isinstance(movie_id, str) or not movie_id:
            raise RevenueProcessingError(
                f"no stable movie_id assigned for DTP URL: {url}"
            )
        if movie_id in results:
            raise RevenueProcessingError(f"duplicate assigned movie_id: {movie_id}")

        mapped = mapped_by_id.get(movie_id)
        if mapped is None:
            raise RevenueProcessingError(
                f"mapping is missing assigned movie_id: {movie_id}"
            )
        mapped_url = _text(getattr(mapped, "source_url_dtp", None))
        if mapped_url != url:
            raise RevenueProcessingError(
                f"{movie_id} mapping URL {mapped_url!r} does not match {url!r}"
            )

        raw_movie = raw_movies.get(url)
        if raw_movie is None:
            raise RevenueProcessingError(f"no raw movie row for DTP URL: {url}")

        collection_row = collection_rows.get(url)
        if collection_row is not None:
            match_status = _text(collection_row.get("match_status"))
        else:
            match_status = _text(raw_movie.get("match_status"))

        decision = _decision_for_mapped_movie(mapped, movie_id)
        results[movie_id] = _build_revenue_record(
            raw_movie=raw_movie,
            match_status=match_status,
            boxoffice_row=boxoffice_rows.get(url),
            decision=decision,
        )

    return results


def apply_revenue_fields(
    rows: Any,
    revenue_by_id: MappingABC[str, MappingABC[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Return copied rows with only Group C revenue fields replaced or added."""
    updated_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, MappingABC):
            raise RevenueProcessingError("base rows must be objects")
        movie_id = row.get("movie_id")
        revenue = revenue_by_id.get(movie_id)
        if revenue is None:
            raise RevenueProcessingError(
                f"no revenue record for movie_id: {movie_id!r}"
            )
        updated = dict(row)
        updated.update(revenue)
        updated_rows.append(updated)
    return tuple(updated_rows)


def revenue_field_names() -> tuple[str, ...]:
    """Return the authoritative Group C field names in schema order."""
    return tuple(schema.GROUP_C_REVENUE_COLUMNS)


__all__ = [
    "BOV_QUALITY_EXACT",
    "COMPARABILITY_INSUFFICIENT_EVIDENCE",
    "COMPARABILITY_NOT_APPLICABLE",
    "DTP_QUALITY_LOWER_BOUND",
    "DTP_QUALITY_ROUNDED",
    "GAP_WARNING_THRESHOLD_PCT",
    "REVENUE_REVIEW_DECISIONS",
    "ParsedRevenue",
    "RevenueProcessingError",
    "apply_revenue_fields",
    "compute_gap_pct",
    "parse_bov_revenue",
    "parse_dtp_revenue",
    "process_revenue",
    "revenue_field_names",
    "schema",
]
