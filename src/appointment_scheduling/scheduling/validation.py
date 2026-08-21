"""Invariant validation and public errors for scheduling state."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import date, datetime, timedelta

import pandas as pd

from appointment_scheduling.preprocessing.validation import (
    SupplyValidationError,
    validate_availability_output,
)
from appointment_scheduling.routes import RoutePreprocessingResult
from appointment_scheduling.scheduling.models import (
    CapacityType,
    EventKey,
    SchedulingState,
)


class SchedulingValidationError(ValueError):
    """Base error for invalid scheduling inputs or state."""


class UnknownSchedulingEventError(SchedulingValidationError):
    """Raised when a patient-event key is absent from the route model."""


class EventNotEligibleError(SchedulingValidationError):
    """Raised when assignment is attempted before dependencies are satisfied."""


class AssignmentConflictError(SchedulingValidationError):
    """Raised for double assignment or assignment/pending conflicts."""


class StaleCandidateError(SchedulingValidationError):
    """Raised when a candidate no longer matches the current state snapshot."""


class CapacityStateError(SchedulingValidationError):
    """Raised when capacity accounting is invalid or exhausted."""


class PendingStateError(SchedulingValidationError):
    """Raised for an invalid explicit pending transition."""


def normalize_public_date(value: object, field_name: str) -> date:
    """Normalize a parseable value to one day-level public date."""

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise SchedulingValidationError(f"{field_name} contains an invalid date")
    return parsed.date()


def validate_build_inputs(
    routes: RoutePreprocessingResult,
    availability: pd.DataFrame,
    route_start_dates: Mapping[str, date],
) -> None:
    """Validate the static inputs required to create an initial state."""

    if not isinstance(routes, RoutePreprocessingResult):
        raise SchedulingValidationError("routes must be a RoutePreprocessingResult")
    if not isinstance(availability, pd.DataFrame):
        raise SchedulingValidationError("availability must be a pandas DataFrame")
    try:
        validate_availability_output(availability, expected_rows=len(availability))
    except SupplyValidationError as exc:
        raise SchedulingValidationError(str(exc)) from exc
    if availability.empty:
        raise SchedulingValidationError("availability must contain at least one row")
    if availability["block_id"].duplicated().any():
        raise SchedulingValidationError(
            "availability.block_id must uniquely identify supply opportunities"
        )

    patients = set(routes.routes_by_patient)
    supplied = set(route_start_dates)
    missing = sorted(patients - supplied)
    extra = sorted(supplied - patients)
    if missing or extra:
        raise SchedulingValidationError(
            f"route_start_dates keys differ from route patients; missing={missing}, extra={extra}"
        )
    for patient_id, value in route_start_dates.items():
        normalize_public_date(value, f"route_start_dates[{patient_id!r}]")


def require_event(state: SchedulingState, key: EventKey) -> None:
    """Require a patient-event key to exist in the immutable route model."""

    patient_id, event_number = key
    try:
        state.event(patient_id, event_number)
    except KeyError as exc:
        raise UnknownSchedulingEventError(
            f"Unknown scheduling event {patient_id!r}/{event_number}"
        ) from exc


def validate_state(state: SchedulingState) -> None:
    """Validate assignment, dependency, capacity, and status invariants."""

    opportunity_by_id = state.opportunities_by_id
    if set(opportunity_by_id) != set(state.capacity_by_opportunity):
        raise CapacityStateError("Capacity keys must match supply opportunity IDs")
    if set(state.assignments) & set(state.pending_events):
        raise AssignmentConflictError("An event cannot be assigned and pending")

    standard_assignments: Counter[str] = Counter()
    overbooking_assignments: Counter[str] = Counter()
    for key, assignment in state.assignments.items():
        require_event(state, key)
        patient_id, event_number = key
        event = state.event(patient_id, event_number)
        if (assignment.patient_id, assignment.event_number) != key:
            raise SchedulingValidationError("Assignment key and payload disagree")
        if assignment.event_id != event.event_id:
            raise SchedulingValidationError("Assignment event ID disagrees with route")
        if assignment.opportunity_id not in opportunity_by_id:
            raise SchedulingValidationError(
                "Assignment references an unknown supply opportunity"
            )
        opportunity = opportunity_by_id[assignment.opportunity_id]
        expected_fields = (
            opportunity.date,
            opportunity.schedule_key,
            opportunity.agenda_id,
            opportunity.clinician_id,
            opportunity.service_id,
            opportunity.section_id,
            opportunity.modality,
        )
        actual_fields = (
            assignment.date,
            assignment.schedule_key,
            assignment.agenda_id,
            assignment.clinician_id,
            assignment.service_id,
            assignment.section_id,
            assignment.modality,
        )
        if actual_fields != expected_fields:
            raise SchedulingValidationError(
                "Assignment payload disagrees with its supply opportunity"
            )
        from appointment_scheduling.scheduling.eligibility import (
            is_resource_compatible,
        )

        if not is_resource_compatible(event, opportunity):
            raise SchedulingValidationError(
                "Assignment supply opportunity is not resource-compatible"
            )
        if assignment.capacity_type is CapacityType.OVERBOOKING:
            if not event.overbooking_allowed:
                raise CapacityStateError(
                    "An overbooking-disallowed event consumed overbooking"
                )
            overbooking_assignments[assignment.opportunity_id] += 1
        else:
            standard_assignments[assignment.opportunity_id] += 1

        predecessor_dates = []
        for predecessor in event.dependencies:
            predecessor_key = (patient_id, predecessor)
            if predecessor_key not in state.assignments:
                raise SchedulingValidationError(
                    "Assigned event has an unassigned predecessor"
                )
            predecessor_dates.append(state.assignments[predecessor_key].date)
        reference = (
            max(predecessor_dates)
            if predecessor_dates
            else state.route_start_dates[patient_id]
        )
        if assignment.date < reference + timedelta(days=event.min_spacing_days):
            raise SchedulingValidationError(
                "Assigned date violates the event minimum spacing"
            )

    for key, pending in state.pending_events.items():
        require_event(state, key)
        if (pending.patient_id, pending.event_number) != key:
            raise PendingStateError("Pending key and payload disagree")

    for opportunity_id, capacity in state.capacity_by_opportunity.items():
        opportunity = opportunity_by_id[opportunity_id]
        if capacity.opportunity_id != opportunity_id:
            raise CapacityStateError("Capacity key and payload disagree")
        values = (
            capacity.standard_capacity,
            capacity.total_capacity,
            capacity.used_standard_capacity,
            capacity.used_overbooking_capacity,
            capacity.remaining_standard_capacity,
            capacity.remaining_total_capacity,
        )
        if any(value < 0 for value in values):
            raise CapacityStateError("Capacity values cannot be negative")
        if capacity.standard_capacity != opportunity.standard_available_capacity:
            raise CapacityStateError("Standard capacity differs from static supply")
        if capacity.total_capacity != opportunity.total_available_capacity:
            raise CapacityStateError("Total capacity differs from static supply")
        if capacity.standard_capacity > capacity.total_capacity:
            raise CapacityStateError("Standard capacity exceeds total capacity")
        if capacity.used_total_capacity + capacity.remaining_total_capacity != capacity.total_capacity:
            raise CapacityStateError("Used plus remaining must equal total capacity")
        if capacity.used_standard_capacity > capacity.standard_capacity:
            raise CapacityStateError("Standard usage exceeds standard capacity")
        if capacity.used_overbooking_capacity > (
            capacity.total_capacity - capacity.standard_capacity
        ):
            raise CapacityStateError("Overbooking usage exceeds overbooking capacity")
        if capacity.used_overbooking_capacity and capacity.remaining_standard_capacity:
            raise CapacityStateError(
                "Overbooking usage cannot precede standard-capacity exhaustion"
            )
        if capacity.used_standard_capacity != standard_assignments[opportunity_id]:
            raise CapacityStateError("Standard usage differs from assignments")
        if capacity.used_overbooking_capacity != overbooking_assignments[opportunity_id]:
            raise CapacityStateError("Overbooking usage differs from assignments")
