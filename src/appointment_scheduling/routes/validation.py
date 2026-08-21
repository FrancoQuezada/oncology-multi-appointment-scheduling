"""Validation and domain errors for public route preprocessing."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

import numpy as np
import pandas as pd

from appointment_scheduling.routes.models import PatientRoute, PathwayTemplate
from appointment_scheduling.synthetic.schemas import ROUTE_COLUMNS


class RouteValidationError(ValueError):
    """Base error for an invalid route input or structure."""


class DependencyValidationError(RouteValidationError):
    """Raised for malformed or invalid dependency data."""


class RouteCycleError(RouteValidationError):
    """Raised when route dependency arcs contain a cycle."""


class PathwayConsistencyError(RouteValidationError):
    """Raised when a patient route disagrees with its pathway template."""


class RouteTimingError(RouteValidationError):
    """Raised when a temporal lower bound cannot be computed."""


_ID_PATTERNS = {
    "patient_id": re.compile(r"PAT-\d{3}"),
    "pathway_id": re.compile(r"PATHWAY-[A-Z]"),
    "event_id": re.compile(r"EVENT-[A-Z]\d"),
    "event_type": re.compile(r"EVENT-[A-Z]\d"),
    "clinician_id": re.compile(r"CLINICIAN-\d{2}"),
    "service_id": re.compile(r"SERVICE-[A-Z]"),
    "section_id": re.compile(r"SECTION-[A-Z]\d"),
    "agenda_id": re.compile(r"AGENDA-DEMO-\d{2}"),
}
_ALLOWED_MODALITIES = {"IN_PERSON", "REMOTE"}
_ALLOWED_RESOURCE_MODES = {"FIXED", "COMPATIBLE_SET"}


def _require_columns(frame: pd.DataFrame, required: Iterable[str]) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise RouteValidationError(f"routes is missing required columns: {missing}")
    null_columns = [column for column in required if frame[column].isna().any()]
    if null_columns:
        raise RouteValidationError(
            f"routes contains null required fields: {null_columns}"
        )


def _integer_series(frame: pd.DataFrame, column: str) -> pd.Series:
    values = pd.to_numeric(frame[column], errors="coerce")
    if values.isna().any() or not np.isfinite(values).all():
        raise RouteValidationError(f"routes.{column} must contain finite integers")
    if (values % 1 != 0).any():
        raise RouteValidationError(f"routes.{column} must contain integers")
    return values.astype("int64")


def parse_dependency_list(value: object) -> tuple[int, ...]:
    """Parse the canonical JSON dependency list into an immutable tuple."""

    if not isinstance(value, str):
        raise DependencyValidationError(
            f"Dependencies must be encoded as a JSON list string: {value!r}"
        )
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise DependencyValidationError(
            f"Malformed dependency list: {value!r}"
        ) from exc
    if not isinstance(parsed, list):
        raise DependencyValidationError(
            f"Dependencies must be a JSON list: {value!r}"
        )
    if any(isinstance(item, bool) or not isinstance(item, int) for item in parsed):
        raise DependencyValidationError(
            f"Dependencies must contain only integers: {value!r}"
        )
    if len(parsed) != len(set(parsed)):
        raise DependencyValidationError(
            f"Dependency list contains duplicates: {value!r}"
        )
    return tuple(parsed)


def validate_route_input(routes: pd.DataFrame) -> None:
    """Validate primitive route values before graph construction."""

    _require_columns(routes, ROUTE_COLUMNS)
    if routes.empty:
        raise RouteValidationError("routes must contain at least one event")

    event_numbers = _integer_series(routes, "event_number")
    minimum = _integer_series(routes, "min_spacing_days")
    preferred = _integer_series(routes, "preferred_max_spacing_days")
    if (event_numbers <= 0).any():
        raise RouteValidationError("routes.event_number must be positive")
    if (minimum < 0).any():
        raise RouteValidationError("Minimum spacing must be non-negative")
    if (preferred < minimum).any():
        raise RouteValidationError(
            "Preferred maximum spacing must be at least the minimum"
        )

    for column, pattern in _ID_PATTERNS.items():
        invalid = ~routes[column].astype(str).str.fullmatch(pattern)
        if invalid.any():
            raise RouteValidationError(
                f"routes.{column} contains an invalid synthetic identifier"
            )
    if not routes["modality"].isin(_ALLOWED_MODALITIES).all():
        raise RouteValidationError("routes.modality contains an unsupported value")
    if not routes["resource_mode"].isin(_ALLOWED_RESOURCE_MODES).all():
        raise RouteValidationError("routes.resource_mode contains an unsupported value")
    valid_overbooking = routes["overbooking_allowed"].map(
        lambda value: isinstance(value, (bool, np.bool_))
    )
    if not valid_overbooking.all():
        raise RouteValidationError(
            "routes.overbooking_allowed must contain booleans"
        )


def validate_patient_identity(rows: pd.DataFrame, patient_id: str) -> None:
    """Validate uniqueness, pathway identity, and contiguous numbering."""

    pathway_ids = tuple(sorted(set(rows["pathway_id"])))
    if len(pathway_ids) != 1:
        raise RouteValidationError(
            f"Patient {patient_id} has inconsistent pathway IDs: {pathway_ids}"
        )
    if rows["event_number"].duplicated().any():
        number = int(rows.loc[rows["event_number"].duplicated(False), "event_number"].iloc[0])
        raise RouteValidationError(
            f"Patient {patient_id} has duplicate event number {number}"
        )
    if rows["event_id"].duplicated().any():
        event_id = str(rows.loc[rows["event_id"].duplicated(False), "event_id"].iloc[0])
        raise RouteValidationError(
            f"Patient {patient_id} has duplicate event ID {event_id!r}"
        )
    numbers = tuple(sorted(int(number) for number in rows["event_number"]))
    expected = tuple(range(1, len(numbers) + 1))
    if numbers != expected:
        raise RouteValidationError(
            f"Patient {patient_id} event numbering must be contiguous from 1"
        )


def validate_dependency_references(
    patient_id: str,
    event_number: int,
    dependencies: tuple[int, ...],
    valid_event_numbers: set[int],
) -> None:
    """Reject self-dependencies and references outside the patient route."""

    if event_number in dependencies:
        raise DependencyValidationError(
            f"Patient {patient_id} event {event_number} depends on itself"
        )
    missing = sorted(set(dependencies) - valid_event_numbers)
    if missing:
        raise DependencyValidationError(
            f"Patient {patient_id} event {event_number} references missing events {missing}"
        )


def validate_pathway_instance(
    route: PatientRoute,
    template: PathwayTemplate,
) -> None:
    """Validate patient-independent structure while allowing resource variation."""

    expected = {
        event.event_number: (
            event.event_id,
            event.event_type,
            event.dependencies,
            event.min_spacing_days,
            event.preferred_max_spacing_days,
            event.resource_mode,
        )
        for event in template.events
    }
    actual = {
        event.event_number: (
            event.event_id,
            event.event_type,
            event.dependencies,
            event.min_spacing_days,
            event.preferred_max_spacing_days,
            event.resource_mode,
        )
        for event in route.events
    }
    if actual != expected:
        raise PathwayConsistencyError(
            f"Patient {route.patient_id} does not match template {template.pathway_id}"
        )
