"""Raw input loading and structural validation for the movie analytics build.

This module is standard-library only. It loads the four approved required inputs,
validates their structure and returns an explicit named container. It performs no
cleaning, normalization, joining, ID assignment or analytical transformation.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


def _load_schema_module() -> ModuleType:
    """Load schema.py without importing the parent CLI/pandas chain."""
    schema_path = Path(__file__).resolve().with_name("schema.py")
    spec = importlib.util.spec_from_file_location(
        "analytics_schema_for_load_raw", schema_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load analytics schema from {schema_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


schema = _load_schema_module()


class RawInputError(Exception):
    """Base class for required-input loading and validation failures."""


class MissingInputError(RawInputError):
    """A required input path does not exist."""


class InvalidInputTypeError(RawInputError):
    """A required input path is not a regular file."""


class CsvParseError(RawInputError):
    """Base class for CSV header, row-shape or decoding failures."""


class CsvHeaderError(CsvParseError):
    """A CSV header is missing, duplicated or lacks required columns."""


class CsvRowShapeError(CsvParseError):
    """A CSV data row has extra or missing fields."""


class CsvDecodeError(CsvParseError):
    """A CSV file cannot be decoded using the required encoding."""


class JsonlParseError(RawInputError):
    """A JSONL line is malformed, non-object or undecodable."""


class JsonlSchemaError(RawInputError):
    """A JSONL object lacks required keys or identifiers."""


class RecordCountMismatchError(RawInputError):
    """A source record count differs from the approved baseline."""


class MissingIdentifierError(RawInputError):
    """A required identifier is empty or absent."""


class DuplicateIdentifierError(RawInputError):
    """A source identifier that must be unique appears more than once."""


@dataclass(frozen=True)
class RawInputPaths:
    """External paths for the four required inputs; defaults come from schema.py."""

    movies_csv: Path = schema.MOVIES_CSV_PATH
    collection_log_csv: Path = schema.COLLECTION_LOG_CSV_PATH
    tickets_sold_web_csv: Path = schema.TICKETS_SOLD_WEB_CSV_PATH
    boxoffice_matches_jsonl: Path = schema.BOXOFFICE_MATCHES_JSONL_PATH


@dataclass(frozen=True)
class RawInputs:
    """Named containers for the four loaded required inputs."""

    movies: tuple[dict[str, str], ...]
    collection_log: tuple[dict[str, str], ...]
    tickets_sold_web: tuple[dict[str, str], ...]
    boxoffice_matches: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class CsvSourceSpec:
    """Structural rules for one required CSV source."""

    name: str
    path_field: str
    required_columns: tuple[str, ...]
    identifier_fields: tuple[str, ...]
    unique_identifier_fields: tuple[str, ...]


@dataclass(frozen=True)
class JsonlSourceSpec:
    """Structural rules for one required JSONL source.

    ``required_keys`` is the complete key contract. Keys listed in
    ``conditional_optional_keys_by_status`` may be absent only for that exact
    ``match_status``. ``field_types`` is checked whenever a key is present;
    ``None`` in an allowed-type tuple denotes an explicit JSON null.
    """

    name: str
    path_field: str
    required_keys: tuple[str, ...]
    identifier_fields: tuple[str, ...]
    unique_identifier_fields: tuple[str, ...]
    conditional_optional_keys_by_status: Mapping[str, frozenset[str]] = field(
        default_factory=dict
    )
    field_types: Mapping[str, tuple[type | None, ...]] = field(default_factory=dict)


MOVIES_CSV_SPEC = CsvSourceSpec(
    name="movies.csv",
    path_field="movies_csv",
    required_columns=(
        "movie_name",
        "title_bovn",
        "original_title",
        "release_year",
        "genre",
        "director",
        "revenue_doanhthuphim",
        "revenue_bovn",
        "source_url_doanhthuphim",
        "source_url_bovn",
    ),
    identifier_fields=("movie_name", "source_url_doanhthuphim"),
    unique_identifier_fields=("source_url_doanhthuphim",),
)

COLLECTION_LOG_CSV_SPEC = CsvSourceSpec(
    name="collection_log.csv",
    path_field="collection_log_csv",
    required_columns=(
        "source_url_doanhthuphim",
        "match_status",
        "match_score",
        "match_reason",
    ),
    identifier_fields=("source_url_doanhthuphim",),
    unique_identifier_fields=("source_url_doanhthuphim",),
)

TICKETS_SOLD_WEB_CSV_SPEC = CsvSourceSpec(
    name="tickets_sold_web.csv",
    path_field="tickets_sold_web_csv",
    required_columns=(
        "source_url_doanhthuphim",
        "tickets_sold_web",
        "tickets_display",
        "tickets_basis",
        "ticket_status",
        "source_title",
        "source_url",
        "source_name",
    ),
    identifier_fields=("source_url_doanhthuphim",),
    unique_identifier_fields=(),
)

# A non-match has no BOV detail page, so these four BOV detail/evidence fields
# are not meaningful and may be absent only when match_status == "not_found".
# They remain required for "matched" and "needs_review", where a BOV candidate
# or mapping actually exists. Nullable lineage/revenue fields are still required
# keys and may be explicit JSON nulls.
_NOT_FOUND_OPTIONAL_BOV_KEYS = frozenset(
    {
        "bov_title",
        "bov_release_info",
        "_bov_candidate",
        "_bov_detail_raw",
    }
)

_VALID_JSONL_MATCH_STATUSES = frozenset(schema.MATCH_STATUS_EXPECTED_COUNTS)

_JSONL_NUMERIC_FIELDS = frozenset({"match_score"})

_JSONL_FIELD_TYPES: dict[str, tuple[type | None, ...]] = {
    "movie_name": (str,),
    "source_url_doanhthuphim": (str,),
    "source_url_bovn": (str, None),
    "match_status": (str,),
    "match_score": (float, int, None),
    "match_reason": (str, None),
    "revenue_bovn": (str, None),
    "bov_title": (str, None),
    "bov_release_info": (str, None),
    # The source stores either a candidate dict, a False sentinel or null.
    "_bov_candidate": (dict, bool, None),
    "_bov_detail_raw": (str, None),
}


BOXOFFICE_MATCHES_JSONL_SPEC = JsonlSourceSpec(
    name="boxoffice_matches.jsonl",
    path_field="boxoffice_matches_jsonl",
    required_keys=(
        "movie_name",
        "source_url_doanhthuphim",
        "source_url_bovn",
        "match_status",
        "match_score",
        "match_reason",
        "revenue_bovn",
        "bov_title",
        "bov_release_info",
        "_bov_candidate",
        "_bov_detail_raw",
    ),
    identifier_fields=("movie_name", "source_url_doanhthuphim"),
    unique_identifier_fields=("source_url_doanhthuphim",),
    conditional_optional_keys_by_status={"not_found": _NOT_FOUND_OPTIONAL_BOV_KEYS},
    field_types=_JSONL_FIELD_TYPES,
)

CSV_SPECS = (
    MOVIES_CSV_SPEC,
    COLLECTION_LOG_CSV_SPEC,
    TICKETS_SOLD_WEB_CSV_SPEC,
)
JSONL_SPECS = (BOXOFFICE_MATCHES_JSONL_SPEC,)


def _ensure_regular_file(path: Path, source_name: str) -> None:
    if not path.exists():
        raise MissingInputError(f"Missing required input {source_name}: {path}")
    if not path.is_file():
        raise InvalidInputTypeError(
            f"Required input {source_name} is not a regular file: {path}"
        )


def _validate_all_input_paths(paths: RawInputPaths) -> None:
    for spec in CSV_SPECS + JSONL_SPECS:
        _ensure_regular_file(getattr(paths, spec.path_field), spec.name)


def _missing_identifier(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _validate_csv_identifiers(
    path: Path,
    spec: CsvSourceSpec,
    rows: tuple[dict[str, str], ...],
) -> None:
    for row_number, row in enumerate(rows, start=2):
        for field in spec.identifier_fields:
            if _missing_identifier(row.get(field)):
                raise MissingIdentifierError(
                    f"{path}: {spec.name} row {row_number} has empty identifier "
                    f"field {field!r}"
                )

    # Exact string comparison only; URL normalization and semantic URL equivalence
    # belong to a later processing stage.
    for field in spec.unique_identifier_fields:
        seen: dict[str, int] = {}
        for row_number, row in enumerate(rows, start=2):
            value = row[field]
            if value in seen:
                raise DuplicateIdentifierError(
                    f"{path}: {spec.name} duplicate {field!r} value {value!r} "
                    f"at rows {seen[value]} and {row_number}"
                )
            seen[value] = row_number


def _validate_jsonl_identifiers(
    path: Path,
    spec: JsonlSourceSpec,
    records: tuple[tuple[dict[str, Any], int], ...],
) -> None:
    for record, line_number in records:
        for field in spec.identifier_fields:
            if field not in record:
                raise MissingIdentifierError(
                    f"{path}: {spec.name} line {line_number} has no identifier "
                    f"field {field!r}"
                )
            value = record[field]
            if _missing_identifier(value):
                raise MissingIdentifierError(
                    f"{path}: {spec.name} line {line_number} has empty identifier "
                    f"field {field!r}"
                )
            if not isinstance(value, str):
                raise MissingIdentifierError(
                    f"{path}: {spec.name} line {line_number} identifier "
                    f"field {field!r} must be a string, got {type(value).__name__}"
                )

    # Exact string comparison only; URL normalization and semantic URL equivalence
    # belong to a later processing stage.
    for field in spec.unique_identifier_fields:
        seen: dict[str, int] = {}
        for record, line_number in records:
            value = record[field]
            if value in seen:
                raise DuplicateIdentifierError(
                    f"{path}: {spec.name} duplicate {field!r} value {value!r} "
                    f"at lines {seen[value]} and {line_number}"
                )
            seen[value] = line_number


def _validate_record_count(
    path: Path,
    source_name: str,
    actual_count: int,
    expected_count: int,
) -> None:
    if actual_count != expected_count:
        raise RecordCountMismatchError(
            f"{path}: {source_name} has {actual_count} records; "
            f"expected {expected_count}"
        )


def _jsonl_required_keys(
    obj: Mapping[str, Any], spec: JsonlSourceSpec
) -> tuple[str, ...]:
    """Return the required keys for this record's explicit match status."""
    status = obj.get("match_status")
    optional = (
        spec.conditional_optional_keys_by_status.get(status, frozenset())
        if isinstance(status, str)
        else frozenset()
    )
    return tuple(key for key in spec.required_keys if key not in optional)


def _allowed_type_names(allowed: tuple[type | None, ...]) -> str:
    return " or ".join("null" if item is None else item.__name__ for item in allowed)


def _value_matches_allowed_types(
    field: str, value: Any, allowed: tuple[type | None, ...]
) -> bool:
    if value is None:
        return None in allowed
    # bool is a subclass of int, but it is never a valid numeric score.
    if field in _JSONL_NUMERIC_FIELDS and isinstance(value, bool):
        return False
    return any(
        expected is not None and isinstance(value, expected) for expected in allowed
    )


def _validate_jsonl_record_shape(
    path: Path, spec: JsonlSourceSpec, obj: Mapping[str, Any], line_number: int
) -> None:
    """Validate status-dependent keys and present-field types for one record."""
    location = f"{path}: {spec.name} line {line_number}"

    if "match_status" in spec.required_keys and "match_status" not in obj:
        raise JsonlSchemaError(
            f"{location} is missing required keys {['match_status']!r}"
        )

    if "match_status" in spec.required_keys:
        status = obj["match_status"]
        if not isinstance(status, str):
            raise JsonlSchemaError(
                f"{location} field 'match_status' must be a string, "
                f"got {type(status).__name__}"
            )
        if status not in _VALID_JSONL_MATCH_STATUSES:
            raise JsonlSchemaError(
                f"{location} has invalid match_status {status!r}; "
                f"expected one of {sorted(_VALID_JSONL_MATCH_STATUSES)}"
            )

    required_keys = _jsonl_required_keys(obj, spec)
    missing_keys = [key for key in required_keys if key not in obj]
    if missing_keys:
        raise JsonlSchemaError(
            f"{location} is missing required keys {missing_keys!r} "
            f"for match_status {obj.get('match_status')!r}"
        )

    for field_name, allowed in spec.field_types.items():
        if field_name not in obj:
            continue
        if field_name in spec.identifier_fields or field_name == "match_status":
            # Identifiers keep their dedicated MissingIdentifierError contract.
            continue
        value = obj[field_name]
        if not _value_matches_allowed_types(field_name, value, allowed):
            raise JsonlSchemaError(
                f"{location} field {field_name!r} has invalid type "
                f"{type(value).__name__}; expected {_allowed_type_names(allowed)}"
            )


def _load_csv(path: Path, spec: CsvSourceSpec) -> tuple[dict[str, str], ...]:
    _ensure_regular_file(path, spec.name)
    rows: list[dict[str, str]] = []

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames

            if not fieldnames:
                raise CsvHeaderError(f"{path}: {spec.name} has no CSV header")
            if len(fieldnames) != len(set(fieldnames)):
                raise CsvHeaderError(
                    f"{path}: {spec.name} has duplicate header names: {fieldnames!r}"
                )

            invalid_headers = [
                name
                for name in fieldnames
                if not isinstance(name, str)
                or name == ""
                or not name.strip()
                or name != name.strip()
            ]
            if invalid_headers:
                raise CsvHeaderError(
                    f"{path}: {spec.name} has invalid header names "
                    f"{invalid_headers!r}; header={fieldnames!r}"
                )

            missing_columns = [
                column for column in spec.required_columns if column not in fieldnames
            ]
            if missing_columns:
                raise CsvHeaderError(
                    f"{path}: {spec.name} is missing required columns "
                    f"{missing_columns!r}; header={fieldnames!r}"
                )

            for row_number, row in enumerate(reader, start=2):
                if None in row:
                    raise CsvRowShapeError(
                        f"{path}: {spec.name} row {row_number} has extra fields "
                        f"{row[None]!r}; header={fieldnames!r}"
                    )
                missing_values = [
                    column
                    for column in fieldnames
                    if row.get(column) is None
                ]
                if missing_values:
                    raise CsvRowShapeError(
                        f"{path}: {spec.name} row {row_number} has missing fields "
                        f"{missing_values!r}; header={fieldnames!r}"
                    )
                rows.append({column: row[column] for column in fieldnames})
    except UnicodeDecodeError as exc:
        raise CsvDecodeError(
            f"{path}: {spec.name} could not be decoded as UTF-8 with BOM support"
        ) from exc
    except csv.Error as exc:
        raise CsvParseError(f"{path}: {spec.name} CSV parse error: {exc}") from exc

    result = tuple(rows)
    _validate_csv_identifiers(path, spec, result)
    _validate_record_count(
        path, spec.name, len(result), schema.EXPECTED_MOVIE_COUNT
    )
    return result


def _load_jsonl(
    path: Path, spec: JsonlSourceSpec
) -> tuple[tuple[dict[str, Any], int], ...]:
    _ensure_regular_file(path, spec.name)
    records: list[tuple[dict[str, Any], int]] = []

    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise JsonlParseError(
                        f"{path}: {spec.name} malformed JSON on line {line_number}: "
                        f"{exc.msg}"
                    ) from exc
                if not isinstance(obj, dict):
                    raise JsonlParseError(
                        f"{path}: {spec.name} line {line_number} contains "
                        f"{type(obj).__name__}, expected a JSON object"
                    )

                _validate_jsonl_record_shape(path, spec, obj, line_number)
                records.append((obj, line_number))
    except UnicodeDecodeError as exc:
        raise JsonlParseError(
            f"{path}: {spec.name} could not be decoded as UTF-8 with BOM support"
        ) from exc

    result = tuple(records)
    _validate_jsonl_identifiers(path, spec, result)
    _validate_record_count(
        path, spec.name, len(result), schema.EXPECTED_MOVIE_COUNT
    )
    return result


def load_raw_inputs(paths: RawInputPaths | None = None) -> RawInputs:
    """Load and structurally validate the four required analytics inputs."""
    if paths is None:
        active_paths = RawInputPaths()
    else:
        active_paths = paths
    _validate_all_input_paths(active_paths)

    movies = _load_csv(getattr(active_paths, MOVIES_CSV_SPEC.path_field), MOVIES_CSV_SPEC)
    collection_log = _load_csv(
        getattr(active_paths, COLLECTION_LOG_CSV_SPEC.path_field),
        COLLECTION_LOG_CSV_SPEC,
    )
    tickets_sold_web = _load_csv(
        getattr(active_paths, TICKETS_SOLD_WEB_CSV_SPEC.path_field),
        TICKETS_SOLD_WEB_CSV_SPEC,
    )
    jsonl_records = _load_jsonl(
        getattr(active_paths, BOXOFFICE_MATCHES_JSONL_SPEC.path_field),
        BOXOFFICE_MATCHES_JSONL_SPEC,
    )
    boxoffice_matches = tuple(record for record, _ in jsonl_records)

    return RawInputs(
        movies=movies,
        collection_log=collection_log,
        tickets_sold_web=tickets_sold_web,
        boxoffice_matches=boxoffice_matches,
    )


__all__ = [
    "BOXOFFICE_MATCHES_JSONL_SPEC",
    "COLLECTION_LOG_CSV_SPEC",
    "CsvDecodeError",
    "CsvHeaderError",
    "CsvParseError",
    "CsvRowShapeError",
    "DuplicateIdentifierError",
    "InvalidInputTypeError",
    "JsonlParseError",
    "JsonlSchemaError",
    "MissingIdentifierError",
    "MissingInputError",
    "MOVIES_CSV_SPEC",
    "RawInputError",
    "RawInputPaths",
    "RawInputs",
    "RecordCountMismatchError",
    "TICKETS_SOLD_WEB_CSV_SPEC",
    "load_raw_inputs",
]
