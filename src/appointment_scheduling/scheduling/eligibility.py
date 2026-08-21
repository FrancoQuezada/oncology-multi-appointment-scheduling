"""Pure dependency, timing, resource, and candidate-feasibility functions."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta

from appointment_scheduling.routes import PatientRoute, ResourceMode, RouteEvent
from appointment_scheduling.scheduling.models import (
    AvailabilityOpportunity,
    CandidateSlot,
    CapacityType,
    EventAssignment,
    EventKey,
    EventStatus,
    SchedulingState,
    SchedulingStateSummary,
    TimingWindow,
)
from appointment_scheduling.scheduling.validation import require_event


def is_event_dependency_eligible(
    route: PatientRoute,
    event_number: int,
    assignments: Mapping[EventKey, EventAssignment],
) -> bool:
    """Return whether every predecessor has a valid patient-specific assignment."""

    event = route.event(event_number)
    for predecessor in event.dependencies:
        assignment = assignments.get((route.patient_id, predecessor))
        if not isinstance(assignment, EventAssignment):
            return False
        if (
            assignment.patient_id != route.patient_id
            or assignment.event_number != predecessor
        ):
            return False
    return True


def get_event_status(
    state: SchedulingState,
    patient_id: str,
    event_number: int,
) -> EventStatus:
    """Derive one event's current mutually exclusive state."""

    key = (patient_id, event_number)
    require_event(state, key)
    if key in state.assignments:
        return EventStatus.ASSIGNED
    if key in state.pending_events:
        return EventStatus.PENDING
    route = state.route_for(patient_id)
    if is_event_dependency_eligible(route, event_number, state.assignments):
        return EventStatus.ELIGIBLE
    return EventStatus.BLOCKED_BY_PREDECESSOR


def get_timing_window(
    state: SchedulingState,
    patient_id: str,
    event_number: int,
) -> TimingWindow:
    """Return the predecessor-derived hard lower and soft preferred dates."""

    key = (patient_id, event_number)
    require_event(state, key)
    route = state.route_for(patient_id)
    event = route.event(event_number)
    if not is_event_dependency_eligible(route, event_number, state.assignments):
        raise ValueError("Timing window requires all predecessor assignments")
    if event.dependencies:
        reference = max(
            state.assignments[(patient_id, predecessor)].date
            for predecessor in event.dependencies
        )
    else:
        reference = state.route_start_dates[patient_id]
    return TimingWindow(
        earliest_date=reference + timedelta(days=event.min_spacing_days),
        preferred_latest_date=(
            reference + timedelta(days=event.preferred_max_spacing_days)
        ),
    )


def is_resource_compatible(
    event: RouteEvent,
    opportunity: AvailabilityOpportunity,
) -> bool:
    """Apply the explicit fixed-resource or compatible-set contract."""

    common_match = (
        opportunity.service_id == event.service_id
        and opportunity.section_id == event.section_id
        and opportunity.event_type == event.event_type
        and opportunity.modality == event.modality
    )
    if not common_match:
        return False
    if event.resource_mode is ResourceMode.FIXED:
        return (
            opportunity.clinician_id == event.clinician_id
            and opportunity.agenda_id == event.agenda_id
        )
    return True


def get_candidate_slots(
    state: SchedulingState,
    patient_id: str,
    event_number: int,
) -> tuple[CandidateSlot, ...]:
    """Return all currently feasible slots in deterministic non-policy order."""

    status = get_event_status(state, patient_id, event_number)
    if status is not EventStatus.ELIGIBLE:
        return ()
    event = state.event(patient_id, event_number)
    window = get_timing_window(state, patient_id, event_number)
    candidates = []
    for opportunity in state.opportunities:
        if opportunity.date < window.earliest_date:
            continue
        if not is_resource_compatible(event, opportunity):
            continue
        capacity = state.capacity_by_opportunity[opportunity.opportunity_id]
        if capacity.remaining_standard_capacity > 0:
            capacity_type = CapacityType.STANDARD
        elif capacity.remaining_total_capacity > 0 and event.overbooking_allowed:
            capacity_type = CapacityType.OVERBOOKING
        else:
            continue
        candidates.append(
            CandidateSlot(
                patient_id=patient_id,
                event_number=event_number,
                event_id=event.event_id,
                opportunity_id=opportunity.opportunity_id,
                date=opportunity.date,
                schedule_key=opportunity.schedule_key,
                agenda_id=opportunity.agenda_id,
                clinician_id=opportunity.clinician_id,
                service_id=opportunity.service_id,
                section_id=opportunity.section_id,
                center_id=opportunity.center_id,
                modality=opportunity.modality,
                event_type=opportunity.event_type,
                standard_remaining_capacity=capacity.remaining_standard_capacity,
                total_remaining_capacity=capacity.remaining_total_capacity,
                capacity_type_required=capacity_type,
                within_preferred_window=(
                    opportunity.date <= window.preferred_latest_date
                ),
                uses_preferred_resource=(
                    opportunity.clinician_id == event.clinician_id
                    and opportunity.agenda_id == event.agenda_id
                ),
            )
        )
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.date,
                item.agenda_id,
                item.clinician_id,
                item.schedule_key,
                item.opportunity_id,
            ),
        )
    )


def summarize_state(state: SchedulingState) -> SchedulingStateSummary:
    """Aggregate event status and capacity diagnostics for one snapshot."""

    statuses = [
        get_event_status(state, route.patient_id, event.event_number)
        for route in state.routes.patient_routes
        for event in route.events
    ]
    capacities = tuple(state.capacity_by_opportunity.values())
    return SchedulingStateSummary(
        patients=len(state.routes.patient_routes),
        total_events=len(statuses),
        assigned_events=statuses.count(EventStatus.ASSIGNED),
        eligible_events=statuses.count(EventStatus.ELIGIBLE),
        dependency_blocked_events=statuses.count(
            EventStatus.BLOCKED_BY_PREDECESSOR
        ),
        pending_events=statuses.count(EventStatus.PENDING),
        total_capacity=sum(item.total_capacity for item in capacities),
        used_capacity=sum(item.used_total_capacity for item in capacities),
        remaining_capacity=sum(item.remaining_total_capacity for item in capacities),
        overbooking_used=sum(item.used_overbooking_capacity for item in capacities),
    )
