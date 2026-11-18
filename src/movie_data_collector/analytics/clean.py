"""Cleaning and normalization for the movie analytics pipeline.

This module is standard-library only. It consumes the ``RawInputs`` structure
from ``load_raw.py`` and returns a cleaned intermediate representation. It does
not assign IDs, join datasets, aggregate tickets, calculate revenue, generate
final data-quality flags or export CSV files.

The approved design keeps DTP URLs and DTP titles verbatim. URL normalization
here is therefore limited to ticket evidence URLs used by the later ticket
deduplication stage.
"""

from __future__ import annotations

import copy
import importlib.util
import ipaddress
import re
import sys
import unicodedata
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit


def _load_module(path: Path, module_name: str) -> ModuleType:
    """Load a sibling module directly to avoid the parent CLI/pandas chain."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


load_raw = _load_module(
    Path(__file__).resolve().with_name("load_raw.py"),
    "analytics_load_raw_for_clean",
)
RawInputs = load_raw.RawInputs


class CleaningInputError(ValueError):
    """Raised when a required cleaning source or field has an invalid shape."""


class FieldStatus(str, Enum):
    """Interpretation status retained beside each derived value."""

    VALID = "valid"
    MISSING = "missing"
    INVALID = "invalid"


@dataclass(frozen=True)
class CleanedMovie:
    """One cleaned movie row with raw values and derived grouping helpers."""

    raw_source_row_dtp: int
    movie_name_raw: str | None
    canonical_title: str | None
    title_status: FieldStatus
    original_title_source: str | None
    original_title_raw: str | None
    original_title_status: FieldStatus
    release_year_source: str | None
    release_year: int | None
    release_year_status: FieldStatus
    genre_source: str | None
    genre_raw: str | None
    genre_status: FieldStatus
    genre_tokens: tuple[str, ...]
    genre_token_path: str | None
    genre_grouped: None
    director_source: str | None
    director_raw: str | None
    director_status: FieldStatus
    director_norm_key: str | None
    source_url_dtp: str | None
    source_url_dtp_status: FieldStatus


@dataclass(frozen=True)
class CleanedTicketCandidate:
    """One ticket evidence row with raw values and deduplication helpers."""

    raw_source_row_tickets: int
    raw: Mapping[str, str]
    source_url_doanhthuphim: str | None
    source_url_raw: str | None
    source_url_normalized: str | None
    source_url_status: FieldStatus
    source_title_raw: str | None
    source_title_normalized: str | None
    source_title_status: FieldStatus


@dataclass(frozen=True)
class CleanedInputs:
    """Named cleaned sources; corresponding rows retain source order."""

    movies: tuple[CleanedMovie, ...]
    collection_log: tuple[Mapping[str, str], ...]
    tickets_sold_web: tuple[CleanedTicketCandidate, ...]
    boxoffice_matches: tuple[Mapping[str, Any], ...]


MOVIE_REQUIRED_FIELDS = (
    "movie_name",
    "original_title",
    "release_year",
    "genre",
    "director",
    "source_url_doanhthuphim",
)
TICKET_REQUIRED_FIELDS = (
    "source_url_doanhthuphim",
    "source_url",
    "source_title",
)

# The design says to remove tracking parameters but does not enumerate them.
# Only the conventional UTM family is removed here; no broader vocabulary is
# inferred without approval.
_TRACKING_QUERY_PREFIXES = ("utm_",)
_YEAR_PATTERN = re.compile(r"[0-9]{4}")
_GOOGLE_NEWS_HOST = "news.google.com"
_VALID_TICKET_URL_SCHEMES = frozenset({"http", "https"})
_HOSTNAME_LABEL_PATTERN = re.compile(r"[A-Za-z0-9-]+")
_MAX_HOSTNAME_LENGTH = 253
_MAX_HOSTNAME_LABEL_LENGTH = 63


def _require_source(raw: RawInputs, name: str) -> tuple[Any, ...]:
    if not hasattr(raw, name):
        raise CleaningInputError(f"RawInputs is missing required source {name!r}")
    value = getattr(raw, name)
    if isinstance(value, (str, bytes)) or value is None:
        raise CleaningInputError(
            f"RawInputs source {name!r} must be an ordered collection of records, "
            f"got {type(value).__name__}"
        )
    try:
        return tuple(value)
    except TypeError as exc:
        raise CleaningInputError(
            f"RawInputs source {name!r} is not iterable: {exc}"
        ) from exc


def _require_mapping(row: Any, source_name: str, row_number: int) -> Mapping[Any, Any]:
    if not isinstance(row, MappingABC):
        raise CleaningInputError(
            f"{source_name} record at source position {row_number - 1} must be a "
            f"mapping, got {type(row).__name__}"
        )
    return row


def _field_text(
    row: Mapping[Any, Any],
    field: str,
    source_name: str,
    row_number: int,
) -> str | None:
    if field not in row:
        raise CleaningInputError(
            f"{source_name} row {row_number} is missing required field {field!r}"
        )
    value = row[field]
    if value is None:
        return None
    if not isinstance(value, str):
        raise CleaningInputError(
            f"{source_name} row {row_number} field {field!r} must be a string or "
            f"None, got {type(value).__name__}"
        )
    return value


def _text_status(value: str | None) -> FieldStatus:
    if value is None or not value.strip():
        return FieldStatus.MISSING
    return FieldStatus.VALID


def _normalize_grouping_key(value: str | None) -> str | None:
    """Casefold, strip accents/đ and collapse whitespace; keep punctuation."""
    if value is None:
        return None
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    without_d_stroke = without_marks.replace("đ", "d")
    collapsed = re.sub(r"\s+", " ", without_d_stroke).strip()
    return collapsed or None


def _split_genre_tokens(genre_raw: str | None) -> tuple[str, ...]:
    if genre_raw is None:
        return ()
    tokens: list[str] = []
    seen: set[str] = set()
    for part in genre_raw.split(","):
        token = part.strip()
        if not token or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tuple(tokens)


def _parse_release_year(raw: str | None) -> tuple[int | None, FieldStatus]:
    status = _text_status(raw)
    if status is FieldStatus.MISSING:
        return None, FieldStatus.MISSING
    candidate = (raw or "").strip()
    if _YEAR_PATTERN.fullmatch(candidate) is None:
        return None, FieldStatus.INVALID
    return int(candidate), FieldStatus.VALID


def _is_valid_hostname(host: str) -> bool:
    if not host or any(char.isspace() for char in host):
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass

    candidate = host[:-1] if host.endswith(".") else host
    if not candidate or len(candidate) > _MAX_HOSTNAME_LENGTH:
        return False
    for label in candidate.split("."):
        if not label or len(label) > _MAX_HOSTNAME_LABEL_LENGTH:
            return False
        if label.startswith("-") or label.endswith("-"):
            return False
        if _HOSTNAME_LABEL_PATTERN.fullmatch(label) is None:
            return False
    return True


def _has_empty_port(netloc: str) -> bool:
    hostport = netloc.rsplit("@", 1)[-1]
    if hostport.startswith("["):
        closing = hostport.find("]")
        return closing != -1 and hostport[closing + 1 :] == ":"
    return hostport.endswith(":")


def _valid_ticket_url_parts(candidate: str) -> tuple[Any, str] | None:
    try:
        parts = urlsplit(candidate)
        if parts.scheme.casefold() not in _VALID_TICKET_URL_SCHEMES:
            return None
        if not parts.netloc:
            return None
        host = parts.hostname
        if not host or not _is_valid_hostname(host):
            return None
        _ = parts.port
        if _has_empty_port(parts.netloc):
            return None
        return parts, host
    except ValueError:
        return None


def _is_google_news_rss_parts(parts: Any, host: str) -> bool:
    return (
        host.casefold() == _GOOGLE_NEWS_HOST
        and parts.path.casefold().startswith("/rss/")
    )


def _lowercase_netloc_host(netloc: str, host: str) -> str:
    userinfo = ""
    hostport = netloc
    if "@" in netloc:
        userinfo, hostport = netloc.rsplit("@", 1)
        userinfo += "@"

    port_suffix = ""
    if hostport.startswith("["):
        closing = hostport.find("]")
        if closing != -1:
            port_suffix = hostport[closing + 1 :]
    else:
        colon = hostport.rfind(":")
        if colon != -1:
            port_suffix = hostport[colon:]

    lowered_host = host.lower()
    if ":" in lowered_host and not lowered_host.startswith("["):
        lowered_host = f"[{lowered_host}]"
    return f"{userinfo}{lowered_host}{port_suffix}"


def _remove_utm_query_parameters(query: str) -> str:
    kept_pairs: list[str] = []
    for pair in query.split("&") if query else ():
        name = pair.split("=", 1)[0]
        if name.casefold().startswith(_TRACKING_QUERY_PREFIXES):
            continue
        kept_pairs.append(pair)
    return "&".join(kept_pairs)


def _normalized_ticket_url(raw: str | None) -> tuple[str | None, FieldStatus]:
    status = _text_status(raw)
    if status is FieldStatus.MISSING:
        return None, FieldStatus.MISSING

    candidate = (raw or "").strip()
    validated = _valid_ticket_url_parts(candidate)
    if validated is None:
        return None, FieldStatus.INVALID
    parts, host = validated

    if _is_google_news_rss_parts(parts, host):
        return candidate, FieldStatus.VALID

    normalized = urlunsplit(
        (
            parts.scheme,
            _lowercase_netloc_host(parts.netloc, host),
            parts.path.rstrip("/"),
            _remove_utm_query_parameters(parts.query),
            "",
        )
    )
    return normalized or None, FieldStatus.VALID


def _clean_movie(row: Mapping[Any, Any], row_number: int) -> CleanedMovie:
    source_name = "movies.csv"
    mapping = _require_mapping(row, source_name, row_number)
    values = {
        field: _field_text(mapping, field, source_name, row_number)
        for field in MOVIE_REQUIRED_FIELDS
    }

    movie_name_raw = values["movie_name"]
    title_status = _text_status(movie_name_raw)

    original_title_source = values["original_title"]
    original_title_status = _text_status(original_title_source)

    release_year_source = values["release_year"]
    release_year, release_year_status = _parse_release_year(release_year_source)

    genre_source = values["genre"]
    genre_status = _text_status(genre_source)
    genre_tokens = _split_genre_tokens(genre_source)
    genre_token_path = "|".join(genre_tokens) if genre_tokens else None

    director_source = values["director"]
    director_status = _text_status(director_source)
    director_norm_key = (
        _normalize_grouping_key(director_source)
        if director_status is FieldStatus.VALID
        else None
    )

    source_url_dtp = values["source_url_doanhthuphim"]
    source_url_dtp_status = _text_status(source_url_dtp)

    return CleanedMovie(
        raw_source_row_dtp=row_number,
        movie_name_raw=movie_name_raw,
        canonical_title=movie_name_raw,
        title_status=title_status,
        original_title_source=original_title_source,
        original_title_raw=(
            original_title_source
            if original_title_status is FieldStatus.VALID
            else None
        ),
        original_title_status=original_title_status,
        release_year_source=release_year_source,
        release_year=release_year,
        release_year_status=release_year_status,
        genre_source=genre_source,
        genre_raw=genre_source if genre_status is FieldStatus.VALID else None,
        genre_status=genre_status,
        genre_tokens=genre_tokens,
        genre_token_path=genre_token_path,
        genre_grouped=None,
        director_source=director_source,
        director_raw=(
            director_source if director_status is FieldStatus.VALID else None
        ),
        director_status=director_status,
        director_norm_key=director_norm_key,
        source_url_dtp=source_url_dtp,
        source_url_dtp_status=source_url_dtp_status,
    )


def _clean_ticket_candidate(
    row: Mapping[Any, Any], row_number: int
) -> CleanedTicketCandidate:
    source_name = "tickets_sold_web.csv"
    mapping = _require_mapping(row, source_name, row_number)
    values = {
        field: _field_text(mapping, field, source_name, row_number)
        for field in TICKET_REQUIRED_FIELDS
    }

    source_url_raw = values["source_url"]
    source_url_normalized, source_url_status = _normalized_ticket_url(source_url_raw)

    source_title_raw = values["source_title"]
    source_title_status = _text_status(source_title_raw)
    source_title_normalized = (
        _normalize_grouping_key(source_title_raw)
        if source_title_status is FieldStatus.VALID
        else None
    )

    return CleanedTicketCandidate(
        raw_source_row_tickets=row_number,
        raw=copy.deepcopy(dict(mapping)),
        source_url_doanhthuphim=values["source_url_doanhthuphim"],
        source_url_raw=source_url_raw,
        source_url_normalized=source_url_normalized,
        source_url_status=source_url_status,
        source_title_raw=source_title_raw,
        source_title_normalized=source_title_normalized,
        source_title_status=source_title_status,
    )


def _copy_records(records: tuple[Any, ...], source_name: str) -> tuple[Mapping[Any, Any], ...]:
    copied: list[Mapping[Any, Any]] = []
    for index, row in enumerate(records, start=1):
        mapping = _require_mapping(row, source_name, index + 1)
        copied.append(copy.deepcopy(dict(mapping)))
    return tuple(copied)


def clean_raw_inputs(raw: RawInputs) -> CleanedInputs:
    """Clean and normalize the four raw sources without changing source order."""
    movie_rows = _require_source(raw, "movies")
    collection_rows = _require_source(raw, "collection_log")
    ticket_rows = _require_source(raw, "tickets_sold_web")
    boxoffice_rows = _require_source(raw, "boxoffice_matches")

    movies = tuple(
        _clean_movie(row, row_number)
        for row_number, row in enumerate(movie_rows, start=2)
    )
    tickets = tuple(
        _clean_ticket_candidate(row, row_number)
        for row_number, row in enumerate(ticket_rows, start=2)
    )

    return CleanedInputs(
        movies=movies,
        collection_log=_copy_records(collection_rows, "collection_log.csv"),
        tickets_sold_web=tickets,
        boxoffice_matches=_copy_records(boxoffice_rows, "boxoffice_matches.jsonl"),
    )


__all__ = [
    "CleanedInputs",
    "CleanedMovie",
    "CleanedTicketCandidate",
    "CleaningInputError",
    "FieldStatus",
    "RawInputs",
    "clean_raw_inputs",
]
