"""Stable movie ID mapping and in-memory assignment for the analytics build.

This module is standard-library only. It loads and validates the approved build
metadata JSON, reuses existing ``movie_id`` values, assigns deterministic IDs for
a first build, and assigns new IDs on later builds without renumbering. It does
not write the mapping JSON, build the analytical CSV, or read the real raw
dataset.

The mapping identity checks deliberately reuse the reporting normalization from
``clean.py``: casefold, accent/``đ`` strip and whitespace collapse, with
punctuation and digits preserved. No fuzzy, positional or BOV-title evidence is
used.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Final, Iterable, Mapping


def _load_module(path: Path, module_name: str) -> ModuleType:
    """Load a sibling module directly to avoid the parent CLI/pandas chain."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


schema = _load_module(
    Path(__file__).resolve().with_name("schema.py"), "analytics_schema_for_ids"
)
clean = _load_module(
    Path(__file__).resolve().with_name("clean.py"), "analytics_clean_for_ids"
)


class MovieIdMappingError(ValueError):
    """Base class for mapping loading, validation and assignment failures."""

    code: str = "ID_MAPPING_INVALID"

    def __init__(self, message: str) -> None:
        super().__init__(f"[{self.code}] {message}")


class MovieIdMappingInvalidError(MovieIdMappingError):
    """The mapping, current input or ID assignment is structurally invalid."""


class MissingMovieIdMappingError(MovieIdMappingInvalidError):
    """A required existing mapping file is absent."""


class MovieIdMappingUnresolvedError(MovieIdMappingError):
    """A URL or identity change cannot be resolved without guessing."""

    code: str = "ID_MAPPING_UNRESOLVED"


SUPPORTED_SCHEMA_VERSION: Final[str] = "1.0"
SUPPORTED_SCHEMA_VERSIONS: Final[frozenset[str]] = frozenset(
    {SUPPORTED_SCHEMA_VERSION}
)
SOURCE_ANCHOR: Final[str] = "source_url_doanhthuphim"
VALID_MOVIE_STATUSES: Final[frozenset[str]] = frozenset({"active", "retired"})
VALID_URL_VERIFICATIONS: Final[frozenset[str]] = frozenset(
    {"initial_seed", "identity_match", "reviewer_alias"}
)

TOP_LEVEL_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "schema_version",
    "generated_at",
    "source_anchor",
    "id_prefix",
    "movies",
)
MOVIE_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "movie_id",
    "source_url_dtp",
    "canonical_title",
    "release_year",
    "director_raw",
    "url_history",
    "status",
    "created_at",
    "last_seen_at",
)
MOVIE_OPTIONAL_FIELDS: Final[tuple[str, ...]] = ("notes", "revenue_review")
VALID_REVENUE_REVIEW_DECISIONS: Final[frozenset[str]] = frozenset(
    {"accepted", "quarantined", "candidate_held", "pending"}
)
REVENUE_REVIEW_DECISIONS_REQUIRING_REASON: Final[frozenset[str]] = frozenset(
    {"quarantined", "candidate_held"}
)
REVENUE_REVIEW_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "decision",
    "reason",
    "reviewed_at",
    "reviewer",
)
URL_HISTORY_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "source_url_dtp",
    "first_seen_at",
    "last_seen_at",
    "verification",
    "approved_by",
    "approved_at",
)

_MOVIE_ID_PATTERN = re.compile(schema.MOVIE_ID_PATTERN)
_ISO_DATETIME_HINT = re.compile(r"\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}")
_FIELD_STATUS_VALUE = clean.FieldStatus.VALID.value

# A tuple is usable as identity evidence only when all three parts are present.
IdentityTuple = tuple[str | None, int | None, str | None]


@dataclass(frozen=True)
class UrlHistoryEntry:
    """One approved observation of a DTP URL for a stable movie ID."""

    source_url_dtp: str
    first_seen_at: str
    last_seen_at: str
    verification: str
    approved_by: str | None
    approved_at: str | None


@dataclass(frozen=True)
class RevenueReview:
    """Explicit revenue-review metadata attached to a stable movie ID."""

    decision: str
    reason: str | None
    reviewed_at: str | None
    reviewer: str | None


@dataclass(frozen=True)
class MappedMovie:
    """One validated persistent movie identity record."""

    movie_id: str
    source_url_dtp: str
    canonical_title: str
    release_year: int | None
    director_raw: str | None
    url_history: tuple[UrlHistoryEntry, ...]
    status: str
    created_at: str
    last_seen_at: str
    notes: str | None = None
    revenue_review: RevenueReview | None = None


@dataclass(frozen=True)
class MovieIdMapping:
    """Validated in-memory representation of the mapping JSON."""

    schema_version: str
    generated_at: str
    source_anchor: str
    id_prefix: str
    movies: tuple[MappedMovie, ...]


@dataclass(frozen=True)
class AssignmentSummary:
    """Counts and identifiers describing what an assignment operation did."""

    reused_ids: tuple[str, ...] = ()
    url_changed_ids: tuple[str, ...] = ()
    new_ids: tuple[str, ...] = ()
    unseen_mapped_urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class IdAssignmentResult:
    """In-memory assignment result for later pipeline stages."""

    movie_ids_by_url: Mapping[str, str]
    updated_mapping: MovieIdMapping
    summary: AssignmentSummary


def _default_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise MovieIdMappingInvalidError(f"{field} must be a non-empty ISO-8601 string")
    if _ISO_DATETIME_HINT.match(value) is None:
        raise MovieIdMappingInvalidError(f"{field} is not an ISO-8601 datetime: {value!r}")

    candidate = value
    if candidate.endswith(("Z", "z")):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        return datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise MovieIdMappingInvalidError(
            f"{field} is not a valid ISO-8601 datetime: {value!r}"
        ) from exc


def _validate_timestamp(value: Any, field: str) -> str:
    _parse_timestamp(value, field)
    return value


def _comparable_timestamps(
    first: str,
    first_field: str,
    second: str,
    second_field: str,
) -> tuple[datetime, datetime]:
    """Return directly comparable datetimes without changing source strings.

    Naive timestamps compare only with naive timestamps. Aware timestamps are
    normalized to UTC for comparison. Mixed awareness is an explicit error.
    """
    first_dt = _parse_timestamp(first, first_field)
    second_dt = _parse_timestamp(second, second_field)
    if (first_dt.tzinfo is None) != (second_dt.tzinfo is None):
        raise MovieIdMappingInvalidError(
            f"cannot compare timezone-aware and timezone-naive timestamps: "
            f"{first_field}={first!r}, {second_field}={second!r}"
        )
    if first_dt.tzinfo is not None:
        first_dt = first_dt.astimezone(timezone.utc)
        second_dt = second_dt.astimezone(timezone.utc)
    return first_dt, second_dt


def _later_timestamp(
    existing: str,
    candidate: str,
    *,
    existing_field: str = "last_seen_at",
    candidate_field: str = "seen_at",
) -> str:
    existing_dt, candidate_dt = _comparable_timestamps(
        existing, existing_field, candidate, candidate_field
    )
    return candidate if candidate_dt >= existing_dt else existing


def _require_mapping_keys(
    value: MappingABC[str, Any],
    required: tuple[str, ...],
    optional: tuple[str, ...],
    label: str,
) -> None:
    missing = [field for field in required if field not in value]
    if missing:
        raise MovieIdMappingInvalidError(
            f"{label} is missing required field(s): {', '.join(missing)}"
        )
    allowed = set(required) | set(optional)
    extra = sorted(str(field) for field in value if field not in allowed)
    if extra:
        raise MovieIdMappingInvalidError(
            f"{label} has unsupported field(s): {', '.join(extra)}"
        )


def _require_text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise MovieIdMappingInvalidError(
            f"{field} must be a string, got {type(value).__name__}"
        )
    if not allow_empty and not value.strip():
        raise MovieIdMappingInvalidError(f"{field} must be a non-empty string")
    return value


def _require_optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field)


def _require_optional_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise MovieIdMappingInvalidError(
            f"{field} must be an integer or null, got {type(value).__name__}"
        )
    return value


def _movie_id_ordinal(value: Any, field: str) -> int:
    movie_id = _require_text(value, field)
    if _MOVIE_ID_PATTERN.fullmatch(movie_id) is None:
        raise MovieIdMappingInvalidError(
            f"{field} does not match {schema.MOVIE_ID_PATTERN}: {movie_id!r}"
        )
    if not movie_id.startswith(schema.ID_PREFIX):
        raise MovieIdMappingInvalidError(
            f"{field} does not use required prefix {schema.ID_PREFIX!r}: {movie_id!r}"
        )
    ordinal = int(movie_id[len(schema.ID_PREFIX) :])
    if ordinal < 1:
        raise MovieIdMappingInvalidError(f"{field} has invalid ordinal: {movie_id!r}")
    return ordinal


def _format_movie_id(ordinal: int) -> str:
    maximum = 10**schema.ID_DIGIT_WIDTH - 1
    if ordinal < 1 or ordinal > maximum:
        raise MovieIdMappingInvalidError(
            f"movie_id ordinal {ordinal} is outside 1..{maximum}"
        )
    return f"{schema.ID_PREFIX}{ordinal:0{schema.ID_DIGIT_WIDTH}d}"


def _normalize_identity_text(value: Any, field: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise MovieIdMappingInvalidError(
            f"{field} must be a string or null, got {type(value).__name__}"
        )
    return clean._normalize_grouping_key(value)


def _identity_key(
    canonical_title: Any,
    release_year: Any,
    director_raw: Any,
    label: str,
) -> IdentityTuple:
    title_key = _normalize_identity_text(canonical_title, f"{label}.canonical_title")
    director_key = _normalize_identity_text(director_raw, f"{label}.director_raw")
    return title_key, release_year, director_key


def _complete_identity(
    canonical_title: Any,
    release_year: Any,
    director_raw: Any,
    label: str,
) -> IdentityTuple | None:
    """Return a key only when every identity component is present."""
    key = _identity_key(canonical_title, release_year, director_raw, label)
    if key[0] is None or key[1] is None or key[2] is None:
        return None
    return key


def _record_complete_identity(record: MappedMovie) -> IdentityTuple | None:
    return _complete_identity(
        record.canonical_title,
        record.release_year,
        record.director_raw,
        record.movie_id,
    )


def _movie_complete_identity(movie: Any) -> IdentityTuple | None:
    return _complete_identity(
        movie.canonical_title,
        movie.release_year,
        movie.director_raw,
        f"current URL {movie.source_url_dtp!r}",
    )


def _parse_url_history_entry(value: Any, label: str) -> UrlHistoryEntry:
    if not isinstance(value, MappingABC):
        raise MovieIdMappingInvalidError(
            f"{label} must be an object, got {type(value).__name__}"
        )
    _require_mapping_keys(
        value, URL_HISTORY_REQUIRED_FIELDS, (), label
    )

    source_url_dtp = _require_text(
        value["source_url_dtp"], f"{label}.source_url_dtp"
    )
    verification = _require_text(value["verification"], f"{label}.verification")
    if verification not in VALID_URL_VERIFICATIONS:
        raise MovieIdMappingInvalidError(
            f"{label}.verification has unsupported value: {verification!r}"
        )

    first_seen_at = _validate_timestamp(value["first_seen_at"], f"{label}.first_seen_at")
    last_seen_at = _validate_timestamp(value["last_seen_at"], f"{label}.last_seen_at")
    first_dt, last_dt = _comparable_timestamps(
        first_seen_at,
        f"{label}.first_seen_at",
        last_seen_at,
        f"{label}.last_seen_at",
    )
    if first_dt > last_dt:
        raise MovieIdMappingInvalidError(
            f"{label}.first_seen_at is later than {label}.last_seen_at"
        )

    approved_by = _require_optional_text(value["approved_by"], f"{label}.approved_by")
    approved_at_raw = value["approved_at"]
    approved_at = (
        None
        if approved_at_raw is None
        else _validate_timestamp(approved_at_raw, f"{label}.approved_at")
    )

    return UrlHistoryEntry(
        source_url_dtp=source_url_dtp,
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at,
        verification=verification,
        approved_by=approved_by,
        approved_at=approved_at,
    )


def _parse_revenue_review(value: Any, label: str) -> RevenueReview:
    if not isinstance(value, MappingABC):
        raise MovieIdMappingInvalidError(
            f"{label} must be an object, got {type(value).__name__}"
        )
    _require_mapping_keys(value, REVENUE_REVIEW_REQUIRED_FIELDS, (), label)

    decision = _require_text(value["decision"], f"{label}.decision")
    if decision not in VALID_REVENUE_REVIEW_DECISIONS:
        raise MovieIdMappingInvalidError(
            f"{label}.decision has unsupported value: {decision!r}"
        )

    reason = _require_optional_text(value["reason"], f"{label}.reason")
    if decision in REVENUE_REVIEW_DECISIONS_REQUIRING_REASON and reason is None:
        raise MovieIdMappingInvalidError(
            f"{label}.reason is required for decision {decision!r}"
        )

    reviewed_at_raw = value["reviewed_at"]
    reviewed_at = (
        None
        if reviewed_at_raw is None
        else _validate_timestamp(reviewed_at_raw, f"{label}.reviewed_at")
    )
    reviewer = _require_optional_text(value["reviewer"], f"{label}.reviewer")

    return RevenueReview(
        decision=decision,
        reason=reason,
        reviewed_at=reviewed_at,
        reviewer=reviewer,
    )


def _parse_mapped_movie(value: Any, label: str) -> MappedMovie:
    if not isinstance(value, MappingABC):
        raise MovieIdMappingInvalidError(
            f"{label} must be an object, got {type(value).__name__}"
        )
    _require_mapping_keys(
        value, MOVIE_REQUIRED_FIELDS, MOVIE_OPTIONAL_FIELDS, label
    )

    movie_id = _require_text(value["movie_id"], f"{label}.movie_id")
    detailed_label = f"{label} (movie_id={movie_id!r})"
    _movie_id_ordinal(movie_id, f"{detailed_label}.movie_id")

    source_url_dtp = _require_text(
        value["source_url_dtp"], f"{detailed_label}.source_url_dtp"
    )
    canonical_title = _require_text(
        value["canonical_title"],
        f"{detailed_label}.canonical_title",
        allow_empty=True,
    )
    release_year = _require_optional_int(
        value["release_year"], f"{detailed_label}.release_year"
    )
    director_raw = _require_optional_text(
        value["director_raw"], f"{detailed_label}.director_raw"
    )

    history_payload = value["url_history"]
    if not isinstance(history_payload, list):
        raise MovieIdMappingInvalidError(
            f"{detailed_label}.url_history must be a list, got "
            f"{type(history_payload).__name__}"
        )
    if not history_payload:
        raise MovieIdMappingInvalidError(
            f"{detailed_label}.url_history must contain at least one entry"
        )
    history = tuple(
        _parse_url_history_entry(entry, f"{detailed_label}.url_history[{index}]")
        for index, entry in enumerate(history_payload)
    )
    for index in range(1, len(history)):
        previous = history[index - 1]
        current = history[index]
        previous_first_label = (
            f"{detailed_label}.url_history[{index - 1}].first_seen_at"
        )
        previous_last_label = f"{detailed_label}.url_history[{index - 1}].last_seen_at"
        current_first_label = f"{detailed_label}.url_history[{index}].first_seen_at"
        current_last_label = f"{detailed_label}.url_history[{index}].last_seen_at"

        previous_first_dt, previous_last_dt = _comparable_timestamps(
            previous.first_seen_at,
            previous_first_label,
            previous.last_seen_at,
            previous_last_label,
        )
        current_first_dt, current_last_dt = _comparable_timestamps(
            current.first_seen_at,
            current_first_label,
            current.last_seen_at,
            current_last_label,
        )
        if current_first_dt < previous_first_dt:
            raise MovieIdMappingInvalidError(
                f"{current_first_label} is earlier than {previous_first_label}"
            )
        if current_last_dt < previous_last_dt:
            raise MovieIdMappingInvalidError(
                f"{current_last_label} is earlier than {previous_last_label}"
            )

    if history[-1].source_url_dtp != source_url_dtp:
        raise MovieIdMappingInvalidError(
            f"{detailed_label}.url_history last entry must equal "
            f"source_url_dtp {source_url_dtp!r}"
        )

    status = _require_text(value["status"], f"{detailed_label}.status")
    if status not in VALID_MOVIE_STATUSES:
        raise MovieIdMappingInvalidError(
            f"{detailed_label}.status has unsupported value: {status!r}"
        )

    created_at = _validate_timestamp(value["created_at"], f"{detailed_label}.created_at")
    last_seen_at = _validate_timestamp(
        value["last_seen_at"], f"{detailed_label}.last_seen_at"
    )
    created_dt, last_seen_dt = _comparable_timestamps(
        created_at,
        f"{detailed_label}.created_at",
        last_seen_at,
        f"{detailed_label}.last_seen_at",
    )
    if created_dt > last_seen_dt:
        raise MovieIdMappingInvalidError(
            f"{detailed_label}.created_at is later than {detailed_label}.last_seen_at"
        )

    notes = _require_optional_text(value.get("notes"), f"{detailed_label}.notes")
    revenue_review = (
        None
        if value.get("revenue_review") is None
        else _parse_revenue_review(
            value["revenue_review"], f"{detailed_label}.revenue_review"
        )
    )

    return MappedMovie(
        movie_id=movie_id,
        source_url_dtp=source_url_dtp,
        canonical_title=canonical_title,
        release_year=release_year,
        director_raw=director_raw,
        url_history=history,
        status=status,
        created_at=created_at,
        last_seen_at=last_seen_at,
        notes=notes,
        revenue_review=revenue_review,
    )


def validate_movie_id_mapping(payload: Any, *, source: str | Path | None = None) -> MovieIdMapping:
    """Validate a decoded mapping object and return an immutable representation."""
    label = f"mapping at {source}" if source is not None else "mapping"
    if not isinstance(payload, MappingABC):
        raise MovieIdMappingInvalidError(
            f"{label} top level must be an object, got {type(payload).__name__}"
        )
    _require_mapping_keys(payload, TOP_LEVEL_REQUIRED_FIELDS, (), label)

    schema_version = _require_text(
        payload["schema_version"], f"{label}.schema_version"
    )
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise MovieIdMappingInvalidError(
            f"{label}.schema_version is unsupported: {schema_version!r}"
        )

    generated_at = _validate_timestamp(payload["generated_at"], f"{label}.generated_at")
    source_anchor = _require_text(payload["source_anchor"], f"{label}.source_anchor")
    if source_anchor != SOURCE_ANCHOR:
        raise MovieIdMappingInvalidError(
            f"{label}.source_anchor must be {SOURCE_ANCHOR!r}, got {source_anchor!r}"
        )
    id_prefix = _require_text(payload["id_prefix"], f"{label}.id_prefix")
    if id_prefix != schema.ID_PREFIX:
        raise MovieIdMappingInvalidError(
            f"{label}.id_prefix must be {schema.ID_PREFIX!r}, got {id_prefix!r}"
        )

    movies_payload = payload["movies"]
    if not isinstance(movies_payload, list):
        raise MovieIdMappingInvalidError(
            f"{label}.movies must be a list, got {type(movies_payload).__name__}"
        )
    movies = tuple(
        _parse_mapped_movie(movie, f"{label}.movies[{index}]")
        for index, movie in enumerate(movies_payload)
    )

    seen_ids: dict[str, int] = {}
    seen_ordinals: dict[int, str] = {}
    seen_urls: dict[str, str] = {}
    history_owner: dict[str, str] = {}
    identity_owner: dict[IdentityTuple, str] = {}

    for index, movie in enumerate(movies):
        record_label = f"{label}.movies[{index}] ({movie.movie_id})"
        if movie.movie_id in seen_ids:
            raise MovieIdMappingInvalidError(
                f"{record_label}.movie_id duplicates ID first used at "
                f"movies[{seen_ids[movie.movie_id]}]"
            )
        seen_ids[movie.movie_id] = index

        ordinal = _movie_id_ordinal(movie.movie_id, f"{record_label}.movie_id")
        if ordinal in seen_ordinals:
            raise MovieIdMappingInvalidError(
                f"{record_label}.movie_id ordinal {ordinal} collides with "
                f"{seen_ordinals[ordinal]}"
            )
        seen_ordinals[ordinal] = movie.movie_id

        if movie.source_url_dtp in seen_urls:
            raise MovieIdMappingInvalidError(
                f"{record_label}.source_url_dtp duplicates URL first used by "
                f"{seen_urls[movie.source_url_dtp]}"
            )
        seen_urls[movie.source_url_dtp] = movie.movie_id

        for entry in movie.url_history:
            owner = history_owner.setdefault(entry.source_url_dtp, movie.movie_id)
            if owner != movie.movie_id:
                raise MovieIdMappingInvalidError(
                    f"{record_label}.url_history source_url_dtp "
                    f"{entry.source_url_dtp!r} is also owned by {owner}"
                )

        identity = _record_complete_identity(movie)
        if identity is not None:
            identity_owner_id = identity_owner.setdefault(identity, movie.movie_id)
            if identity_owner_id != movie.movie_id:
                raise MovieIdMappingInvalidError(
                    f"{record_label} duplicates identity: complete identity key "
                    f"{identity!r} already claimed by {identity_owner_id}"
                )

    return MovieIdMapping(
        schema_version=schema_version,
        generated_at=generated_at,
        source_anchor=source_anchor,
        id_prefix=id_prefix,
        movies=movies,
    )


def load_movie_id_mapping(path: str | Path | None = None) -> MovieIdMapping:
    """Load and validate an existing mapping JSON file; never create one."""
    target = schema.ID_MAP_JSON_PATH if path is None else Path(path)
    if not target.exists():
        raise MissingMovieIdMappingError(f"Missing existing mapping file: {target}")
    if not target.is_file():
        raise MovieIdMappingInvalidError(
            f"Mapping path is not a regular file: {target}"
        )

    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise MovieIdMappingInvalidError(
            f"Mapping file is not valid UTF-8: {target}"
        ) from exc
    except OSError as exc:
        raise MovieIdMappingInvalidError(
            f"Could not read mapping file: {target}: {exc}"
        ) from exc

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MovieIdMappingInvalidError(
            f"Mapping file contains invalid JSON: {target}: {exc}"
        ) from exc

    return validate_movie_id_mapping(payload, source=str(target))


def serialize_movie_id_mapping(mapping: MovieIdMapping) -> dict[str, Any]:
    """Return a plain JSON-ready representation of a validated mapping."""
    if not isinstance(mapping, MovieIdMapping):
        raise MovieIdMappingInvalidError(
            "mapping must be a validated MovieIdMapping instance"
        )

    movies: list[dict[str, Any]] = []
    for record in mapping.movies:
        movie_payload: dict[str, Any] = {
            "movie_id": record.movie_id,
            "source_url_dtp": record.source_url_dtp,
            "canonical_title": record.canonical_title,
            "release_year": record.release_year,
            "director_raw": record.director_raw,
            "url_history": [
                {
                    "source_url_dtp": entry.source_url_dtp,
                    "first_seen_at": entry.first_seen_at,
                    "last_seen_at": entry.last_seen_at,
                    "verification": entry.verification,
                    "approved_by": entry.approved_by,
                    "approved_at": entry.approved_at,
                }
                for entry in record.url_history
            ],
            "status": record.status,
            "created_at": record.created_at,
            "last_seen_at": record.last_seen_at,
        }
        if record.notes is not None:
            movie_payload["notes"] = record.notes
        if record.revenue_review is not None:
            movie_payload["revenue_review"] = {
                "decision": record.revenue_review.decision,
                "reason": record.revenue_review.reason,
                "reviewed_at": record.revenue_review.reviewed_at,
                "reviewer": record.revenue_review.reviewer,
            }
        movies.append(movie_payload)

    return {
        "schema_version": mapping.schema_version,
        "generated_at": mapping.generated_at,
        "source_anchor": mapping.source_anchor,
        "id_prefix": mapping.id_prefix,
        "movies": movies,
    }


def _mapping_json_text(mapping: MovieIdMapping) -> str:
    payload = serialize_movie_id_mapping(mapping)
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _atomic_write_text(
    target: Path,
    text: str,
    *,
    overwrite: bool,
) -> None:
    parent = target.parent
    if not parent.is_dir():
        raise MovieIdMappingInvalidError(
            f"Mapping destination directory does not exist: {parent}"
        )
    if _path_exists(target) and not overwrite:
        raise MovieIdMappingInvalidError(
            f"Mapping destination already exists: {target}"
        )

    fd: int | None = None
    temp_path: Path | None = None
    try:
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=str(parent)
        )
        temp_path = Path(temp_name)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            fd = None
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    except OSError as exc:
        raise MovieIdMappingInvalidError(
            f"Could not write mapping file: {target}: {exc}"
        ) from exc
    finally:
        if fd is not None:
            os.close(fd)
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def save_movie_id_mapping(
    mapping: MovieIdMapping,
    path: str | Path | None = None,
    *,
    overwrite: bool = False,
) -> MovieIdMapping:
    """Validate, serialize and atomically write a mapping JSON file."""
    target = schema.ID_MAP_JSON_PATH if path is None else Path(path)
    if not isinstance(mapping, MovieIdMapping):
        raise MovieIdMappingInvalidError(
            "mapping must be a validated MovieIdMapping instance"
        )

    payload = serialize_movie_id_mapping(mapping)
    validated = validate_movie_id_mapping(payload, source=str(target))
    _atomic_write_text(target, _mapping_json_text(validated), overwrite=overwrite)
    return validated


def _revenue_review_payload(value: Any, label: str) -> dict[str, Any]:
    if isinstance(value, RevenueReview):
        return {
            "decision": value.decision,
            "reason": value.reason,
            "reviewed_at": value.reviewed_at,
            "reviewer": value.reviewer,
        }
    if isinstance(value, MappingABC):
        return dict(value)
    raise MovieIdMappingInvalidError(
        f"{label} must be a RevenueReview instance or an object, "
        f"got {type(value).__name__}"
    )


def _with_revenue_reviews(
    mapping: MovieIdMapping,
    revenue_reviews: Any,
) -> MovieIdMapping:
    if revenue_reviews is None:
        return mapping
    if not isinstance(revenue_reviews, MappingABC):
        raise MovieIdMappingInvalidError(
            "revenue_reviews must be an object keyed by movie_id"
        )

    parsed: dict[str, RevenueReview] = {}
    for movie_id, value in revenue_reviews.items():
        label = f"revenue_reviews[{movie_id!r}]"
        _movie_id_ordinal(movie_id, label)
        parsed[movie_id] = _parse_revenue_review(
            _revenue_review_payload(value, label), label
        )

    known_ids = {record.movie_id for record in mapping.movies}
    unknown_ids = sorted(set(parsed) - known_ids)
    if unknown_ids:
        raise MovieIdMappingInvalidError(
            "revenue_reviews contains unknown movie_id(s): "
            + ", ".join(unknown_ids)
        )

    movies = tuple(
        replace(
            record,
            revenue_review=parsed.get(record.movie_id, record.revenue_review),
        )
        for record in mapping.movies
    )
    return replace(mapping, movies=movies)


def initialize_movie_id_mapping(
    movies: Any,
    *,
    revenue_reviews: Mapping[str, Any] | None,
    confirm_initialize: bool = False,
    destination: str | Path | None = None,
    analytics_output_path: str | Path | None = None,
    generated_at: str | None = None,
    seen_at: str | None = None,
) -> MovieIdMapping:
    """Explicitly initialize a new mapping file after all safety gates pass."""
    if confirm_initialize is not True:
        raise MovieIdMappingInvalidError(
            "explicit confirm_initialize=True is required for first-time "
            "mapping initialization"
        )

    target = schema.ID_MAP_JSON_PATH if destination is None else Path(destination)
    analytics = (
        schema.MOVIE_ANALYTICS_CSV_PATH
        if analytics_output_path is None
        else Path(analytics_output_path)
    )
    if _path_exists(target):
        raise MovieIdMappingInvalidError(
            f"cannot initialize mapping: destination already exists: {target}"
        )
    if _path_exists(analytics):
        raise MovieIdMappingInvalidError(
            "cannot initialize mapping: analytical CSV already exists: "
            f"{analytics}"
        )

    result = assign_initial_movie_ids(
        movies, generated_at=generated_at, seen_at=seen_at
    )
    intended = _with_revenue_reviews(result.updated_mapping, revenue_reviews)
    validated = validate_movie_id_mapping(
        serialize_movie_id_mapping(intended), source=str(target)
    )
    if validated != intended:
        raise MovieIdMappingInvalidError(
            "intended mapping changed during validation; refusing to persist"
        )

    saved = save_movie_id_mapping(validated, target, overwrite=False)
    loaded = load_movie_id_mapping(target)
    if loaded != saved:
        raise MovieIdMappingInvalidError(
            f"persisted mapping does not match intended mapping: {target}"
        )
    return loaded


def update_movie_id_mapping(
    movies: Any,
    *,
    path: str | Path | None = None,
    seen_at: str | None = None,
    revenue_reviews: Mapping[str, Any] | None = None,
) -> MovieIdMapping:
    """Validate an existing mapping, update IDs in memory, then persist safely."""
    target = schema.ID_MAP_JSON_PATH if path is None else Path(path)
    if not _path_exists(target):
        raise MissingMovieIdMappingError(f"Missing existing mapping file: {target}")

    existing = load_movie_id_mapping(target)
    result = assign_stable_movie_ids(movies, existing, seen_at=seen_at)
    intended = _with_revenue_reviews(result.updated_mapping, revenue_reviews)
    validated = validate_movie_id_mapping(
        serialize_movie_id_mapping(intended), source=str(target)
    )
    saved = save_movie_id_mapping(validated, target, overwrite=True)
    loaded = load_movie_id_mapping(target)
    if loaded != saved:
        raise MovieIdMappingInvalidError(
            f"persisted mapping does not match intended mapping: {target}"
        )
    return loaded


def _coerce_movies(movies: Any) -> tuple[Any, ...]:
    if hasattr(movies, "movies") and not isinstance(movies, (str, bytes, MappingABC)):
        iterable = movies.movies
    else:
        iterable = movies
    if isinstance(iterable, (str, bytes, MappingABC)):
        raise MovieIdMappingInvalidError(
            "current movies must be an iterable of cleaned movie records"
        )
    try:
        return tuple(iterable)
    except TypeError as exc:
        raise MovieIdMappingInvalidError(
            "current movies must be an iterable of cleaned movie records"
        ) from exc


def _validate_current_movies(movies: tuple[Any, ...]) -> None:
    required_attributes = (
        "source_url_dtp",
        "canonical_title",
        "release_year",
        "director_raw",
    )
    seen_urls: dict[str, int] = {}
    seen_identities: dict[IdentityTuple, str] = {}

    for index, movie in enumerate(movies):
        label = f"current movie at position {index}"
        for attribute in required_attributes:
            if not hasattr(movie, attribute):
                raise MovieIdMappingInvalidError(
                    f"{label} is missing field {attribute!r}"
                )

        status = getattr(movie, "source_url_dtp_status", None)
        if status is not None and getattr(status, "value", status) != _FIELD_STATUS_VALUE:
            raise MovieIdMappingInvalidError(
                f"{label}.source_url_dtp_status is not valid"
            )

        source_url_dtp = _require_text(
            movie.source_url_dtp, f"{label}.source_url_dtp"
        )
        if source_url_dtp in seen_urls:
            raise MovieIdMappingInvalidError(
                f"{label}.source_url_dtp duplicates URL first used at position "
                f"{seen_urls[source_url_dtp]}: {source_url_dtp!r}"
            )
        seen_urls[source_url_dtp] = index

        canonical_title = _require_text(
            movie.canonical_title, f"{label}.canonical_title", allow_empty=True
        )
        release_year = _require_optional_int(movie.release_year, f"{label}.release_year")
        director_raw = _require_optional_text(movie.director_raw, f"{label}.director_raw")
        identity = _complete_identity(
            canonical_title, release_year, director_raw, source_url_dtp
        )
        if identity is not None:
            if identity in seen_identities:
                raise MovieIdMappingInvalidError(
                    f"{label} duplicates identity: complete identity key "
                    f"{identity!r} already held by {seen_identities[identity]!r}"
                )
            seen_identities[identity] = source_url_dtp


def _history_with_last_seen_updated(
    history: tuple[UrlHistoryEntry, ...], seen_at: str
) -> tuple[UrlHistoryEntry, ...]:
    last = history[-1]
    updated_last = replace(
        last,
        last_seen_at=_later_timestamp(
            last.last_seen_at,
            seen_at,
            existing_field="url_history.last_seen_at",
        ),
    )
    return history[:-1] + (updated_last,)


def _with_current_snapshot(
    record: MappedMovie, movie: Any, seen_at: str
) -> MappedMovie:
    return replace(
        record,
        canonical_title=movie.canonical_title,
        release_year=movie.release_year,
        director_raw=movie.director_raw,
        last_seen_at=_later_timestamp(record.last_seen_at, seen_at),
        url_history=_history_with_last_seen_updated(record.url_history, seen_at),
    )


def _reviewer_alias_entry(
    record: MappedMovie, source_url_dtp: str
) -> UrlHistoryEntry | None:
    for entry in record.url_history:
        if (
            entry.verification == "reviewer_alias"
            and entry.source_url_dtp == source_url_dtp
        ):
            return entry
    return None


def _with_url_change(
    record: MappedMovie,
    movie: Any,
    seen_at: str,
    verification: str,
    alias_entry: UrlHistoryEntry | None,
) -> MappedMovie:
    previous = record.url_history[-1]
    previous_last_dt, seen_dt = _comparable_timestamps(
        previous.last_seen_at,
        "previous url_history.last_seen_at",
        seen_at,
        "seen_at",
    )
    if seen_dt < previous_last_dt:
        raise MovieIdMappingInvalidError(
            f"cannot append URL {movie.source_url_dtp!r}: seen_at {seen_at!r} is "
            f"earlier than previous last_seen_at {previous.last_seen_at!r}"
        )
    new_entry = UrlHistoryEntry(
        source_url_dtp=movie.source_url_dtp,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        verification=verification,
        approved_by=alias_entry.approved_by if alias_entry is not None else None,
        approved_at=alias_entry.approved_at if alias_entry is not None else None,
    )
    return replace(
        record,
        source_url_dtp=movie.source_url_dtp,
        canonical_title=movie.canonical_title,
        release_year=movie.release_year,
        director_raw=movie.director_raw,
        status="active",
        last_seen_at=_later_timestamp(record.last_seen_at, seen_at),
        url_history=record.url_history + (new_entry,),
    )


def _identity_owner(
    records: Iterable[MappedMovie],
) -> dict[IdentityTuple, MappedMovie]:
    owner: dict[IdentityTuple, MappedMovie] = {}
    for record in records:
        key = _record_complete_identity(record)
        if key is None:
            continue
        if key in owner:
            raise MovieIdMappingUnresolvedError(
                f"complete identity key {key!r} is claimed by both "
                f"{owner[key].movie_id} and {record.movie_id}"
            )
        owner[key] = record
    return owner


def _new_mapped_movie(movie: Any, movie_id: str, seen_at: str) -> MappedMovie:
    return MappedMovie(
        movie_id=movie_id,
        source_url_dtp=movie.source_url_dtp,
        canonical_title=movie.canonical_title,
        release_year=movie.release_year,
        director_raw=movie.director_raw,
        url_history=(
            UrlHistoryEntry(
                source_url_dtp=movie.source_url_dtp,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                verification="initial_seed",
                approved_by=None,
                approved_at=None,
            ),
        ),
        status="active",
        created_at=seen_at,
        last_seen_at=seen_at,
    )


def assign_initial_movie_ids(
    movies: Any,
    *,
    generated_at: str | None = None,
    seen_at: str | None = None,
) -> IdAssignmentResult:
    """Assign M0001.. sequentially by ascending DTP URL, in memory only."""
    cleaned = _coerce_movies(movies)
    _validate_current_movies(cleaned)

    seen = _validate_timestamp(seen_at, "seen_at") if seen_at is not None else _default_timestamp()
    generated = (
        _validate_timestamp(generated_at, "generated_at")
        if generated_at is not None
        else seen
    )

    ordered = tuple(sorted(cleaned, key=lambda movie: movie.source_url_dtp))
    if len(ordered) > 10**schema.ID_DIGIT_WIDTH - 1:
        raise MovieIdMappingInvalidError(
            f"too many movies for {schema.ID_DIGIT_WIDTH}-digit movie_id values"
        )

    records: list[MappedMovie] = []
    assignments: dict[str, str] = {}
    for ordinal, movie in enumerate(ordered, start=1):
        movie_id = _format_movie_id(ordinal)
        records.append(_new_mapped_movie(movie, movie_id, seen))
        assignments[movie.source_url_dtp] = movie_id

    mapping = MovieIdMapping(
        schema_version=SUPPORTED_SCHEMA_VERSION,
        generated_at=generated,
        source_anchor=SOURCE_ANCHOR,
        id_prefix=schema.ID_PREFIX,
        movies=tuple(records),
    )
    summary = AssignmentSummary(new_ids=tuple(record.movie_id for record in records))
    return IdAssignmentResult(
        movie_ids_by_url=MappingProxyType(assignments),
        updated_mapping=mapping,
        summary=summary,
    )


def assign_stable_movie_ids(
    movies: Any,
    mapping: MovieIdMapping,
    *,
    seen_at: str | None = None,
) -> IdAssignmentResult:
    """Reuse, URL-match and add IDs using a validated mapping, in memory only."""
    if not isinstance(mapping, MovieIdMapping):
        raise MovieIdMappingInvalidError(
            "mapping must be a validated MovieIdMapping instance"
        )

    cleaned = _coerce_movies(movies)
    _validate_current_movies(cleaned)
    seen = _validate_timestamp(seen_at, "seen_at") if seen_at is not None else _default_timestamp()

    current_by_url = {movie.source_url_dtp: movie for movie in cleaned}
    updated_by_id = {record.movie_id: record for record in mapping.movies}
    active_by_url = {
        record.source_url_dtp: record
        for record in mapping.movies
        if record.status == "active"
    }
    retired_by_url = {
        record.source_url_dtp: record
        for record in mapping.movies
        if record.status == "retired"
    }

    for url in current_by_url:
        retired_record = retired_by_url.get(url)
        if retired_record is not None and url not in active_by_url:
            raise MovieIdMappingUnresolvedError(
                f"current URL {url!r} belongs to retired movie_id "
                f"{retired_record.movie_id}; operator action is required"
            )

    assignments: dict[str, str] = {}
    reused_ids: list[str] = []
    url_changed_ids: list[str] = []

    for movie in cleaned:
        record = active_by_url.get(movie.source_url_dtp)
        if record is None:
            continue
        updated = _with_current_snapshot(record, movie, seen)
        updated_by_id[record.movie_id] = updated
        _identity_owner(updated_by_id.values())
        assignments[movie.source_url_dtp] = record.movie_id
        reused_ids.append(record.movie_id)

    unmatched_movies = [
        movie for movie in cleaned if movie.source_url_dtp not in assignments
    ]
    unmatched_records = [
        record
        for record in mapping.movies
        if record.status == "active" and record.movie_id not in reused_ids
    ]
    identity_owner = _identity_owner(updated_by_id.values())

    candidates_by_url: dict[str, tuple[MappedMovie, tuple[str, ...]]] = {}
    candidate_urls_by_id: dict[str, list[str]] = defaultdict(list)

    for movie in unmatched_movies:
        key = _movie_complete_identity(movie)
        owner = identity_owner.get(key) if key is not None else None
        candidates: list[tuple[MappedMovie, tuple[str, ...]]] = []
        for record in unmatched_records:
            record_key = _record_complete_identity(record)
            reasons: list[str] = []
            if key is not None and record_key is not None and key == record_key:
                reasons.append("identity_match")
            if _reviewer_alias_entry(record, movie.source_url_dtp) is not None:
                reasons.append("reviewer_alias")
            if reasons:
                candidates.append((record, tuple(reasons)))

        if len(candidates) > 1:
            ids = ", ".join(record.movie_id for record, _ in candidates)
            raise MovieIdMappingUnresolvedError(
                f"current URL {movie.source_url_dtp!r} has {len(candidates)} "
                f"possible movie IDs: {ids}"
            )

        if len(candidates) == 1:
            record, reasons = candidates[0]
            if owner is not None and owner.movie_id != record.movie_id:
                raise MovieIdMappingUnresolvedError(
                    f"current URL {movie.source_url_dtp!r} complete identity {key!r} "
                    f"is claimed by {owner.movie_id}, but URL evidence points to "
                    f"{record.movie_id}"
                )
            candidates_by_url[movie.source_url_dtp] = (record, reasons)
            candidate_urls_by_id[record.movie_id].append(movie.source_url_dtp)
        elif owner is not None:
            raise MovieIdMappingUnresolvedError(
                f"current URL {movie.source_url_dtp!r} complete identity {key!r} "
                f"conflicts with existing movie_id {owner.movie_id}"
            )

    for movie_id, urls in candidate_urls_by_id.items():
        if len(urls) > 1:
            raise MovieIdMappingUnresolvedError(
                f"movie_id {movie_id} has {len(urls)} possible replacement URLs: "
                f"{', '.join(sorted(urls))}"
            )

    for movie in unmatched_movies:
        candidate = candidates_by_url.get(movie.source_url_dtp)
        if candidate is None:
            continue
        record, reasons = candidate
        if "identity_match" in reasons:
            verification = "identity_match"
            alias_entry = None
        else:
            verification = "reviewer_alias"
            alias_entry = _reviewer_alias_entry(record, movie.source_url_dtp)
        updated_by_id[record.movie_id] = _with_url_change(
            record, movie, seen, verification, alias_entry
        )
        assignments[movie.source_url_dtp] = record.movie_id
        url_changed_ids.append(record.movie_id)

    _identity_owner(updated_by_id.values())

    new_movies = [
        movie for movie in cleaned if movie.source_url_dtp not in assignments
    ]
    existing_ordinals = {
        _movie_id_ordinal(record.movie_id, f"{record.movie_id}")
        for record in mapping.movies
    }
    next_ordinal = max(existing_ordinals, default=0) + 1
    new_ids: list[str] = []

    for movie in sorted(new_movies, key=lambda item: item.source_url_dtp):
        while next_ordinal in existing_ordinals:
            next_ordinal += 1
        movie_id = _format_movie_id(next_ordinal)
        updated_by_id[movie_id] = _new_mapped_movie(movie, movie_id, seen)
        assignments[movie.source_url_dtp] = movie_id
        existing_ordinals.add(next_ordinal)
        new_ids.append(movie_id)
        next_ordinal += 1

    updated_movies = tuple(
        updated_by_id[record.movie_id] for record in mapping.movies
    ) + tuple(updated_by_id[movie_id] for movie_id in new_ids)
    updated_mapping = replace(mapping, movies=updated_movies)

    unseen_mapped_urls = tuple(
        record.source_url_dtp
        for record in mapping.movies
        if record.status == "active" and record.source_url_dtp not in current_by_url
    )

    return IdAssignmentResult(
        movie_ids_by_url=MappingProxyType(assignments),
        updated_mapping=updated_mapping,
        summary=AssignmentSummary(
            reused_ids=tuple(reused_ids),
            url_changed_ids=tuple(url_changed_ids),
            new_ids=tuple(new_ids),
            unseen_mapped_urls=unseen_mapped_urls,
        ),
    )
