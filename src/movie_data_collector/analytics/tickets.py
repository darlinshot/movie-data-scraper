"""Ticket candidate linking, deduplication and aggregation for the analytics build.

This module is standard-library only. It consumes the existing ``RawInputs``,
``CleanedInputs`` and ``IdAssignmentResult`` shapes without modifying them.

A ticket candidate is linked to a movie only by an exact
``source_url_doanhthuphim`` match. Titles, match scores, BOV titles, physical row
positions and fuzzy similarity are never used for identity. Candidate evidence is
deduplicated with the normalization already produced by ``clean.py``, and movie
summaries contain only the approved Group D fields.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any


def _load_schema_module() -> ModuleType:
    """Load schema.py directly to avoid the parent CLI/pandas import chain."""
    schema_path = Path(__file__).resolve().with_name("schema.py")
    spec = importlib.util.spec_from_file_location(
        "analytics_schema_for_tickets", schema_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load analytics schema from {schema_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


schema = _load_schema_module()


class TicketProcessingError(ValueError):
    """Base class for ticket-linking and aggregation failures."""


class TicketLinkUnresolvedError(TicketProcessingError):
    """A populated candidate has no exact DTP URL in the stable ID assignment."""

    code = "TICKET_LINK_UNRESOLVED"

    def __init__(self, message: str) -> None:
        super().__init__(f"[{self.code}] {message}")


TICKET_DATA_UNVERIFIED = "unverified_candidates"
TICKET_DATA_NONE = "no_candidates"
TICKET_CONTEXT_CINEMA = "cinema_candidate_unverified"
TICKET_CONTEXT_EVENT = "event_attendance_quarantined"
TICKET_CONTEXT_NONE = "no_candidate"

TICKET_STATUS_FOUND = "found"
TICKET_STATUS_NEEDS_REVIEW = "needs_review"
POPULATED_TICKET_STATUSES = frozenset({TICKET_STATUS_FOUND, TICKET_STATUS_NEEDS_REVIEW})

# The approved design identifies this audit row by its CSV line number.
EVENT_ATTENDANCE_SOURCE_ROW = 49


@dataclass(frozen=True)
class LinkedTicketCandidate:
    """One preserved ticket evidence row after the exact DTP URL join."""

    movie_id: str
    raw_source_row_tickets: int
    raw: MappingABC[str, Any]
    source_url_doanhthuphim: str | None
    source_url_raw: str | None
    source_url_normalized: str | None
    source_title_raw: str | None
    source_title_normalized: str | None
    tickets_display: str | None
    ticket_status: str | None
    context_status: str


@dataclass(frozen=True)
class TicketProcessingResult:
    """Movie-grain summaries plus the retained linked/deduplicated evidence."""

    summaries: MappingABC[str, MappingABC[str, Any]]
    linked_candidates: tuple[LinkedTicketCandidate, ...]
    deduplicated_candidates: tuple[LinkedTicketCandidate, ...]


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _populated_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _has_evidence(candidate: Any) -> bool:
    """Return True only for populated candidate rows, not empty search results."""
    raw = getattr(candidate, "raw", None)
    if not isinstance(raw, MappingABC):
        raw = {}
    status = _text(raw.get("ticket_status"))
    return (
        _populated_text(getattr(candidate, "source_url_raw", None))
        or _populated_text(getattr(candidate, "source_title_raw", None))
        or _populated_text(raw.get("tickets_display"))
        or _populated_text(raw.get("tickets_sold_web"))
        or _populated_text(raw.get("snippet"))
        or status in POPULATED_TICKET_STATUSES
    )


def _assignment_index(id_assignment: Any) -> tuple[dict[str, str], tuple[str, ...]]:
    assignments = getattr(id_assignment, "movie_ids_by_url", None)
    if not isinstance(assignments, MappingABC):
        raise TicketProcessingError("id_assignment is missing movie_ids_by_url")

    mapping = getattr(id_assignment, "updated_mapping", None)
    if mapping is None:
        raise TicketProcessingError("id_assignment is missing updated_mapping")

    mapped_by_id: dict[str, Any] = {}
    all_movie_ids: list[str] = []
    for mapped in getattr(mapping, "movies", ()):
        movie_id = getattr(mapped, "movie_id", None)
        url = getattr(mapped, "source_url_dtp", None)
        if not isinstance(movie_id, str) or not movie_id:
            raise TicketProcessingError("mapping record is missing movie_id")
        if movie_id in mapped_by_id:
            raise TicketProcessingError(f"mapping has duplicate movie_id: {movie_id}")
        if not isinstance(url, str) or not url:
            raise TicketProcessingError(f"{movie_id} mapping is missing source_url_dtp")
        mapped_by_id[movie_id] = mapped
        all_movie_ids.append(movie_id)

    for url, movie_id in assignments.items():
        if not isinstance(url, str) or not url:
            raise TicketProcessingError("assignment contains an empty DTP URL")
        if not isinstance(movie_id, str) or not movie_id:
            raise TicketProcessingError(f"assignment has no movie_id for URL: {url!r}")
        mapped = mapped_by_id.get(movie_id)
        if mapped is None:
            raise TicketProcessingError(
                f"assignment references unmapped movie_id: {movie_id}"
            )
        if getattr(mapped, "source_url_dtp", None) != url:
            raise TicketProcessingError(
                f"{movie_id} mapping URL does not match assigned URL: {url!r}"
            )

    for mapped in getattr(mapping, "movies", ()):
        movie_id = getattr(mapped, "movie_id")
        url = getattr(mapped, "source_url_dtp")
        if assignments.get(url) != movie_id:
            raise TicketProcessingError(
                f"mapping URL is not assigned to {movie_id}: {url!r}"
            )

    return dict(assignments), tuple(all_movie_ids)


def _context_status(raw_source_row_tickets: Any) -> str:
    if raw_source_row_tickets == EVENT_ATTENDANCE_SOURCE_ROW:
        return TICKET_CONTEXT_EVENT
    return TICKET_CONTEXT_CINEMA


def link_ticket_candidates(
    cleaned_inputs: Any, assignments: MappingABC[str, str]
) -> tuple[LinkedTicketCandidate, ...]:
    """Link populated candidates by exact DTP URL; reject unresolved evidence."""
    candidates = getattr(cleaned_inputs, "tickets_sold_web", ())
    try:
        iterator = iter(candidates)
    except TypeError as exc:
        raise TicketProcessingError("cleaned_inputs.tickets_sold_web is not iterable") from exc

    linked: list[LinkedTicketCandidate] = []
    for candidate in iterator:
        if not hasattr(candidate, "source_url_doanhthuphim"):
            raise TicketProcessingError("ticket candidate lacks cleaned fields")
        if not _has_evidence(candidate):
            continue

        dtp_url = _text(getattr(candidate, "source_url_doanhthuphim", None))
        row_number = getattr(candidate, "raw_source_row_tickets", None)
        if not _populated_text(dtp_url):
            raise TicketLinkUnresolvedError(
                f"tickets row {row_number!r} has no source_url_doanhthuphim"
            )
        movie_id = assignments.get(dtp_url)
        if movie_id is None:
            raise TicketLinkUnresolvedError(
                f"tickets row {row_number!r} DTP URL is unresolved: {dtp_url!r}"
            )

        raw = getattr(candidate, "raw", {})
        if not isinstance(raw, MappingABC):
            raw = {}
        linked.append(
            LinkedTicketCandidate(
                movie_id=movie_id,
                raw_source_row_tickets=row_number,
                raw=raw,
                source_url_doanhthuphim=dtp_url,
                source_url_raw=_text(getattr(candidate, "source_url_raw", None)),
                source_url_normalized=_text(
                    getattr(candidate, "source_url_normalized", None)
                ),
                source_title_raw=_text(getattr(candidate, "source_title_raw", None)),
                source_title_normalized=_text(
                    getattr(candidate, "source_title_normalized", None)
                ),
                tickets_display=_text(raw.get("tickets_display")),
                ticket_status=_text(raw.get("ticket_status")),
                context_status=_context_status(row_number),
            )
        )
    return tuple(linked)


def _url_key(candidate: LinkedTicketCandidate) -> str | None:
    """Use the clean.py normalization when available, otherwise the raw URL."""
    return candidate.source_url_normalized or candidate.source_url_raw


def _title_key(candidate: LinkedTicketCandidate) -> str | None:
    """Use the clean.py normalization when available, otherwise the raw title."""
    return candidate.source_title_normalized or candidate.source_title_raw


def _variation(candidate: LinkedTicketCandidate) -> tuple[str | None, str | None]:
    return candidate.tickets_display, candidate.ticket_status


def deduplicate_ticket_candidates(
    linked: tuple[LinkedTicketCandidate, ...],
) -> tuple[LinkedTicketCandidate, ...]:
    """Collapse identical evidence; retain distinct display/status observations."""
    grouped: dict[tuple[str, str | None, str | None], list[LinkedTicketCandidate]] = {}
    deduplicated: list[LinkedTicketCandidate] = []

    for candidate in linked:
        key = (candidate.movie_id, _url_key(candidate), _title_key(candidate))
        kept_for_key = grouped.setdefault(key, [])
        variation = _variation(candidate)
        if any(_variation(existing) == variation for existing in kept_for_key):
            continue
        kept_for_key.append(candidate)
        deduplicated.append(candidate)

    return tuple(deduplicated)


def serialize_evidence_urls(
    candidates: tuple[LinkedTicketCandidate, ...],
) -> str | None:
    """Deduplicate by normalized URL, sort raw URLs and join with '|'."""
    first_raw_by_url: dict[str, str] = {}
    for candidate in candidates:
        url = candidate.source_url_raw
        if not _populated_text(url):
            continue
        key = _url_key(candidate) or url
        first_raw_by_url.setdefault(key, url)
    if not first_raw_by_url:
        return None
    return "|".join(sorted(first_raw_by_url.values()))


def aggregate_ticket_summaries(
    deduplicated: tuple[LinkedTicketCandidate, ...],
    all_movie_ids: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """Build one approved Group D record per stable movie ID."""
    seen_ids: set[str] = set()
    by_movie: dict[str, list[LinkedTicketCandidate]] = {}
    for movie_id in all_movie_ids:
        if movie_id in seen_ids:
            raise TicketProcessingError(f"duplicate movie_id in assignment: {movie_id}")
        seen_ids.add(movie_id)
        by_movie[movie_id] = []

    for candidate in deduplicated:
        if candidate.movie_id not in by_movie:
            raise TicketProcessingError(
                f"deduplicated candidate has unknown movie_id: {candidate.movie_id}"
            )
        by_movie[candidate.movie_id].append(candidate)

    summaries: dict[str, dict[str, Any]] = {}
    for movie_id in all_movie_ids:
        candidates = by_movie[movie_id]
        if candidates:
            context_status = (
                TICKET_CONTEXT_EVENT
                if any(
                    candidate.context_status == TICKET_CONTEXT_EVENT
                    for candidate in candidates
                )
                else TICKET_CONTEXT_CINEMA
            )
        else:
            context_status = TICKET_CONTEXT_NONE

        summary = {
            "ticket_candidate_count": len(candidates),
            "ticket_found_count": sum(
                candidate.ticket_status == TICKET_STATUS_FOUND
                for candidate in candidates
            ),
            "ticket_needs_review_count": sum(
                candidate.ticket_status == TICKET_STATUS_NEEDS_REVIEW
                for candidate in candidates
            ),
            "ticket_verified_admissions": None,
            "ticket_data_status": (
                TICKET_DATA_UNVERIFIED if candidates else TICKET_DATA_NONE
            ),
            "ticket_context_status": context_status,
            "ticket_evidence_urls": serialize_evidence_urls(candidates),
        }
        summaries[movie_id] = {
            field: summary[field] for field in schema.GROUP_D_TICKET_COLUMNS
        }
    return summaries


def process_tickets(
    raw_inputs: Any,
    cleaned_inputs: Any,
    id_assignment: Any,
) -> TicketProcessingResult:
    """Return Group D summaries and preserved candidate evidence.

    ``raw_inputs`` is accepted for interface symmetry with the other analytics
    stages. Raw ticket values used here come from ``CleanedTicketCandidate.raw``,
    which ``clean.py`` copied from the original source without modification.
    """
    if raw_inputs is None:
        raise TicketProcessingError("raw_inputs is required")
    assignments, all_movie_ids = _assignment_index(id_assignment)
    linked = link_ticket_candidates(cleaned_inputs, assignments)
    deduplicated = deduplicate_ticket_candidates(linked)
    summaries = aggregate_ticket_summaries(deduplicated, all_movie_ids)
    return TicketProcessingResult(
        summaries=summaries,
        linked_candidates=linked,
        deduplicated_candidates=deduplicated,
    )


def apply_ticket_fields(
    rows: Any,
    ticket_by_id: MappingABC[str, MappingABC[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Return copied rows with only Group D ticket fields replaced or added."""
    updated_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, MappingABC):
            raise TicketProcessingError("base rows must be objects")
        movie_id = row.get("movie_id")
        ticket = ticket_by_id.get(movie_id)
        if ticket is None:
            raise TicketProcessingError(f"no ticket record for movie_id: {movie_id!r}")
        updated = dict(row)
        updated.update(ticket)
        updated_rows.append(updated)
    return tuple(updated_rows)


def ticket_field_names() -> tuple[str, ...]:
    """Return the authoritative Group D field names in schema order."""
    return tuple(schema.GROUP_D_TICKET_COLUMNS)


__all__ = [
    "EVENT_ATTENDANCE_SOURCE_ROW",
    "POPULATED_TICKET_STATUSES",
    "TICKET_CONTEXT_CINEMA",
    "TICKET_CONTEXT_EVENT",
    "TICKET_CONTEXT_NONE",
    "TICKET_DATA_NONE",
    "TICKET_DATA_UNVERIFIED",
    "TICKET_STATUS_FOUND",
    "TICKET_STATUS_NEEDS_REVIEW",
    "LinkedTicketCandidate",
    "TicketLinkUnresolvedError",
    "TicketProcessingError",
    "TicketProcessingResult",
    "aggregate_ticket_summaries",
    "apply_ticket_fields",
    "deduplicate_ticket_candidates",
    "link_ticket_candidates",
    "process_tickets",
    "serialize_evidence_urls",
    "schema",
    "ticket_field_names",
]
