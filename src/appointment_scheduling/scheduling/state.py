"""Construction and explicit copy-on-write scheduling-state transitions."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import pandas as pd

from appointment_scheduling.routes import RoutePreprocessingResult
from appointment_scheduling.scheduling.eligibility import get_candidate_slots
from appointment_scheduling.scheduling.models import (
    AvailabilityOpportunity,
    CandidateSlot,
    CapacityState,
    EventAssignment,
    EventStatus,
    PendingEvent,
    PendingReason,
    SchedulingState,
)
from appointment_scheduling.scheduling.validation import (
    AssignmentConflictError,
    CapacityStateError,
    EventNotEligibleError,
    PendingStateError,
    StaleCandidateError,
    normalize_public_date,
    require_event,
    validate_build_inputs,
    validate_state,
)


def build_scheduling_state(
    routes: RoutePreprocessingResult,
    availability: pd.DataFrame,
    route_start_dates: Mapping[str, date],
) -> SchedulingState:
    """Build a clean initial state from immutable routes and preprocessed supply."""

    validate_build_inputs(routes, availability, route_start_dates)
    opportunities = tuple(
        AvailabilityOpportunity(
            opportunity_id=str(row["block_id"]),
            date=normalize_public_date(row["date"], "availability.date"),
            schedule_key=str(row["schedule_key"]),
            agenda_id=str(row["agenda_id"]),
            clinician_id=str(row["clinician_id"]),
            resource_mapping_key=str(row["resource_mapping_key"]),
            service_id=str(row["service_id"]),
            section_id=str(row["section_id"]),
            center_id=str(row["center_id"]),
            modality=str(row["modality"]),
            event_type=str(row["event_type"]),
            standard_available_capacity=int(row["standard_available_capacity"]),
            total_available_capacity=int(row["total_available_capacity"]),
        )
        for _, row in availability.sort_values(
            ["date", "agenda_id", "clinician_id", "schedule_key", "block_id"],
            kind="mergesort",
        ).iterrows()
    )
    capacities = {
        item.opportunity_id: CapacityState(
            opportunity_id=item.opportunity_id,
            standard_capacity=item.standard_available_capacity,
            total_capacity=item.total_available_capacity,
        )
        for item in opportunities
    }
    normalized_starts = {
        patient_id: normalize_public_date(value, f"route_start_dates[{patient_id!r}]")
        for patient_id, value in route_start_dates.items()
    }
    state = SchedulingState.create(
        routes=routes,
        opportunities=opportunities,
        route_start_dates=normalized_starts,
        assignments={},
        capacity_by_opportunity=capacities,
        pending_events={},
    )
    validate_state(state)
    return state


def assign_event(
    state: SchedulingState,
    patient_id: str,
    event_number: int,
    candidate_slot: CandidateSlot,
) -> SchedulingState:
    """Assign one event to one current candidate and consume one capacity unit."""

    key = (patient_id, event_number)
    require_event(state, key)
    status = state.status_for(patient_id, event_number)
    if status is EventStatus.ASSIGNED:
        raise AssignmentConflictError("Event is already assigned")
    if status is EventStatus.PENDING:
        raise AssignmentConflictError("A pending event cannot be assigned")
    if status is not EventStatus.ELIGIBLE:
        raise EventNotEligibleError("Event dependencies are not satisfied")

    current_candidates = get_candidate_slots(state, patient_id, event_number)
    if candidate_slot not in current_candidates:
        raise StaleCandidateError(
            "Candidate is stale or does not belong to this event and state"
        )
    capacity = state.capacity_by_opportunity[candidate_slot.opportunity_id]
    try:
        updated_capacity = capacity.consume(candidate_slot.capacity_type_required)
    except ValueError as exc:
        raise CapacityStateError(str(exc)) from exc

    assignment = EventAssignment(
        patient_id=patient_id,
        event_number=event_number,
        event_id=candidate_slot.event_id,
        date=candidate_slot.date,
        opportunity_id=candidate_slot.opportunity_id,
        schedule_key=candidate_slot.schedule_key,
        agenda_id=candidate_slot.agenda_id,
        clinician_id=candidate_slot.clinician_id,
        service_id=candidate_slot.service_id,
        section_id=candidate_slot.section_id,
        modality=candidate_slot.modality,
        capacity_type=candidate_slot.capacity_type_required,
    )
    assignments = dict(state.assignments)
    assignments[key] = assignment
    capacities = dict(state.capacity_by_opportunity)
    capacities[candidate_slot.opportunity_id] = updated_capacity
    new_state = SchedulingState.create(
        routes=state.routes,
        opportunities=state.opportunities,
        route_start_dates=state.route_start_dates,
        assignments=assignments,
        capacity_by_opportunity=capacities,
        pending_events=state.pending_events,
    )
    validate_state(new_state)
    return new_state


def mark_pending(
    state: SchedulingState,
    patient_id: str,
    event_number: int,
    reason: PendingReason,
) -> SchedulingState:
    """Explicitly mark an unassigned event unresolved without propagation."""

    key = (patient_id, event_number)
    require_event(state, key)
    if key in state.assignments:
        raise AssignmentConflictError("An assigned event cannot become pending")
    if key in state.pending_events:
        raise PendingStateError("Event is already pending")
    if not isinstance(reason, PendingReason):
        raise PendingStateError("reason must be a PendingReason")
    pending = dict(state.pending_events)
    pending[key] = PendingEvent(patient_id, event_number, reason)
    new_state = SchedulingState.create(
        routes=state.routes,
        opportunities=state.opportunities,
        route_start_dates=state.route_start_dates,
        assignments=state.assignments,
        capacity_by_opportunity=state.capacity_by_opportunity,
        pending_events=pending,
    )
    validate_state(new_state)
    return new_state
