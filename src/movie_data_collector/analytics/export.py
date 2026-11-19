"""Atomic CSV export for the approved flat movie analytics dataset.

This module is standard-library only. It writes exactly one CSV file and
performs no EDA, chart, Power BI, CLI or transformation work.
"""

from __future__ import annotations

import csv
import importlib.util
import math
import os
import sys
import tempfile
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


def _load_module(path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load analytics module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ANALYTICS_DIR = Path(__file__).resolve().parent
build_dataset = _load_module(
    ANALYTICS_DIR / "build_dataset.py", "analytics_build_dataset_for_export"
)
schema = build_dataset.schema


class ExportError(ValueError):
    """Base class for export and export-validation failures."""


class ExportValidationError(ExportError):
    """The supplied in-memory dataset cannot be exported safely."""


class ExportReadBackError(ExportError):
    """The written CSV does not round-trip the validated dataset."""


@dataclass(frozen=True)
class ExportResult:
    """Read-only summary of one successful atomic export."""

    output_path: Path
    row_count: int
    column_count: int
    validation: Mapping[str, Any]
    readback_validation: Mapping[str, Any]


_IMPORTANT_READBACK_FIELDS = (
    "dtp_revenue_raw",
    "dtp_revenue_vnd",
    "bov_revenue_vnd",
    "bov_quarantined_revenue_vnd",
    "bov_candidate_revenue_vnd",
    "revenue_gap_pct",
    "include_revenue_comparison",
    "magnitude_gap_warning",
    "revenue_conflict_flag",
    "revenue_scope_verified",
    "ticket_candidate_count",
    "ticket_found_count",
    "ticket_needs_review_count",
    "ticket_verified_admissions",
)


def _validate_source_rows(rows: Any) -> tuple[tuple[dict[str, Any], ...], dict[str, Any]]:
    """Require an exact schema match before any file is created or replaced."""
    try:
        dataset = tuple(rows)
    except TypeError as exc:
        raise ExportValidationError("rows must be an iterable of mappings") from exc

    for index, row in enumerate(dataset):
        if not isinstance(row, MappingABC):
            raise ExportValidationError(
                f"row {index} must be a mapping, got {type(row).__name__}"
            )
        columns = tuple(row.keys())
        if columns != schema.FINAL_COLUMNS:
            actual = set(columns)
            expected = set(schema.FINAL_COLUMNS)
            raise ExportValidationError(
                f"row {index} columns do not match the approved schema: "
                f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}, "
                f"ordered={columns == schema.FINAL_COLUMNS}"
            )

    try:
        validation = build_dataset.validate_dataset(dataset)
    except build_dataset.DatasetValidationError as exc:
        raise ExportValidationError(str(exc)) from exc

    return tuple(dict(row) for row in dataset), dict(validation)


def _serialize_cell(value: Any) -> str:
    """Use a stable CSV representation without changing string values."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float) and not math.isfinite(value):
        raise ExportValidationError(f"non-finite float cannot be exported: {value!r}")
    return str(value)


def _write_temp_csv(
    dataset: tuple[dict[str, Any], ...], destination: Path
) -> Path:
    """Write and fsync one temporary CSV in the destination directory."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=schema.FINAL_COLUMNS,
                lineterminator="\n",
                extrasaction="raise",
            )
            writer.writeheader()
            for row in dataset:
                writer.writerow(
                    {field: _serialize_cell(row[field]) for field in schema.FINAL_COLUMNS}
                )
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def _convert_readback_value(
    field: str, source_value: Any, actual: str
) -> Any:
    """Convert one exported cell back using its already-validated source type."""
    if source_value is None:
        return None
    if isinstance(source_value, str):
        return actual
    if isinstance(source_value, bool):
        if actual not in {"1", "0"}:
            raise ExportReadBackError(
                f"field {field!r} read back as {actual!r}; expected '1' or '0'"
            )
        return actual == "1"
    if actual == "":
        raise ExportReadBackError(f"field {field!r} read back as an empty value")
    if isinstance(source_value, int):
        try:
            return int(actual)
        except ValueError as exc:
            raise ExportReadBackError(
                f"field {field!r} read back as non-integer {actual!r}"
            ) from exc
    if isinstance(source_value, float):
        try:
            converted = float(actual)
        except ValueError as exc:
            raise ExportReadBackError(
                f"field {field!r} read back as non-float {actual!r}"
            ) from exc
        if not math.isfinite(converted):
            raise ExportReadBackError(f"field {field!r} read back as non-finite")
        return converted
    return actual


def _validate_readback(
    path: Path,
    source_rows: tuple[dict[str, Any], ...],
    expected_ids: tuple[str, ...],
) -> dict[str, Any]:
    """Reopen one written CSV and verify exact round-trip and invariants."""
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            header = tuple(reader.fieldnames or ())
            if header != schema.FINAL_COLUMNS:
                raise ExportReadBackError(
                    f"{path}: header does not match the approved column order: "
                    f"{header!r}"
                )

            exported_rows: list[dict[str, str]] = []
            for row_number, row in enumerate(reader, start=2):
                if None in row:
                    raise ExportReadBackError(
                        f"{path}: row {row_number} has extra fields "
                        f"{row[None]!r}; an index column may have been written"
                    )
                if any(value is None for value in row.values()):
                    raise ExportReadBackError(
                        f"{path}: row {row_number} has missing fields"
                    )
                if tuple(row.keys()) != schema.FINAL_COLUMNS:
                    raise ExportReadBackError(
                        f"{path}: row {row_number} has unexpected columns"
                    )
                exported_rows.append(
                    {field: row[field] for field in schema.FINAL_COLUMNS}
                )
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ExportReadBackError(f"{path}: CSV read-back failed: {exc}") from exc

    if len(exported_rows) != schema.EXPECTED_MOVIE_COUNT:
        raise ExportReadBackError(
            f"{path}: expected {schema.EXPECTED_MOVIE_COUNT} rows, "
            f"got {len(exported_rows)}"
        )

    empty_field_count = 0
    converted_rows: list[dict[str, Any]] = []
    for row_number, (source, exported) in enumerate(
        zip(source_rows, exported_rows), start=2
    ):
        converted: dict[str, Any] = {}
        for field in schema.FINAL_COLUMNS:
            expected_cell = _serialize_cell(source[field])
            actual_cell = exported[field]
            if actual_cell != expected_cell:
                raise ExportReadBackError(
                    f"{path}: row {row_number} field {field!r} read back as "
                    f"{actual_cell!r}; expected {expected_cell!r}"
                )
            if actual_cell == "":
                empty_field_count += 1
            converted[field] = _convert_readback_value(
                field, source[field], actual_cell
            )
        converted_rows.append(converted)

    exported_ids = tuple(row["movie_id"] for row in converted_rows)
    if exported_ids != expected_ids:
        raise ExportReadBackError(f"{path}: exported movie_id values changed")

    try:
        structural_validation = build_dataset.validate_dataset(
            converted_rows, expected_movie_ids=expected_ids
        )
    except build_dataset.DatasetValidationError as exc:
        raise ExportReadBackError(f"{path}: read-back validation failed: {exc}") from exc

    return {
        "path": str(path),
        "row_count": len(exported_rows),
        "column_count": len(header),
        "cell_count": len(exported_rows) * len(schema.FINAL_COLUMNS),
        "empty_field_count": empty_field_count,
        "important_fields_checked": len(_IMPORTANT_READBACK_FIELDS),
        "structural_validation": dict(structural_validation),
    }


def export_analytics_dataset(
    rows: Any, output_path: str | Path | None = None
) -> ExportResult:
    """Validate, atomically write and read back the single analytics CSV."""
    dataset, validation = _validate_source_rows(rows)
    expected_ids = tuple(row["movie_id"] for row in dataset)

    destination = (
        schema.MOVIE_ANALYTICS_CSV_PATH
        if output_path is None
        else Path(output_path)
    )
    if destination.exists() and not destination.is_file():
        raise ExportValidationError(
            f"output path is not a regular file: {destination}"
        )

    temp_path: Path | None = None
    try:
        temp_path = _write_temp_csv(dataset, destination)
        temporary_readback = _validate_readback(temp_path, dataset, expected_ids)
        os.replace(temp_path, destination)
        temp_path = None
        final_readback = _validate_readback(destination, dataset, expected_ids)
    except BaseException:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise

    return ExportResult(
        output_path=destination,
        row_count=validation["row_count"],
        column_count=validation["column_count"],
        validation=validation,
        readback_validation={
            "temporary": temporary_readback,
            "final": final_readback,
        },
    )


__all__ = [
    "ExportError",
    "ExportReadBackError",
    "ExportResult",
    "ExportValidationError",
    "export_analytics_dataset",
]
