"""Applied sequential workflow built on the shared scheduling-state engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Protocol

from appointment_scheduling.routes import RouteEvent
from appointment_scheduling.scheduling import (
    CandidateSlot,
    CapacityType,
    EventStatus,
    PendingReason,
    SchedulingState,
    assign_event,
    get_candidate_slots,
    get_timing_window,
    mark_pending,
    validate_state,
)


class SequentialSchedulerError(ValueError):
    """Base error for invalid sequential-workflow behavior."""


class InvalidDecisionError(SequentialSchedulerError):
    """Raised when a decision rule violates the public decision contract."""


class DecisionAction(str, Enum):
    """Actions a decision rule may request for one eligible event."""

    ASSIGN = "ASSIGN"
    PENDING = "PENDING"


@dataclass(frozen=True, slots=True)
class SchedulingDecision:
    """Auditable assignment or pending request returned by a decision rule."""

    patient_id: str
    event_number: int
    action: DecisionAction
    candidate: CandidateSlot | None = None
    pending_reason: PendingReason | None = None

    @classmethod
    def assign(cls, candidate: CandidateSlot) -> SchedulingDecision:
        return cls(
            patient_id=candidate.patient_id,
            event_number=candidate.event_number,
            action=DecisionAction.ASSIGN,
            candidate=candidate,
        )

    @classmethod
    def pending(
        cls,
        patient_id: str,
        event_number: int,
        reason: PendingReason,
    ) -> SchedulingDecision:
        return cls(
            patient_id=patient_id,
            event_number=event_number,
            action=DecisionAction.PENDING,
            pending_reason=reason,
        )


class DecisionRule(Protocol):
    """Callable candidate-selection boundary for the sequential workflow."""

    def __call__(
        self,
        event: RouteEvent,
        candidates: tuple[CandidateSlot, ...],
        state: SchedulingState,
    ) -> SchedulingDecision:
        """Choose one current candidate or explicitly request pending state."""


@dataclass(frozen=True, slots=True)
class SchedulingTraceEntry:
    """One public-safe, deterministic event-processing record."""

    step: int
    patient_id: str
    event_number: int
    event_id: str
    status_before: EventStatus
    candidate_count: int
    chosen_action: DecisionAction
    chosen_opportunity_id: str | None
    chosen_date: date | None
    capacity_type: CapacityType | None
    within_preferred_window: bool | None
    pending_reason: PendingReason | None
    status_after: EventStatus


@dataclass(frozen=True, slots=True)
class SequentialSchedulingSummary:
    """Aggregate outcome of one complete sequential workflow run."""

    patients_processed: int
    events_total: int
    events_assigned: int
    events_pending: int
    events_dependency_blocked: int
    standard_assignments: int
    overbooking_assignments: int
    late_assignments: int
    capacity_used: int
    capacity_remaining: int
    routes_fully_completed: int
    routes_partially_completed: int
    routes_unresolved: int


@dataclass(frozen=True, slots=True)
class SequentialSchedulingResult:
    """Final scheduling snapshot, ordered audit trace, and outcome summary."""

    final_state: SchedulingState
    trace: tuple[SchedulingTraceEntry, ...]
    summary: SequentialSchedulingSummary


def earliest_feasible_rule(
    event: RouteEvent,
    candidates: tuple[CandidateSlot, ...],
    state: SchedulingState,
) -> SchedulingDecision:
    """Select the first already-sorted candidate as a simple demo rule."""

    del event, state
    if not candidates:
        raise InvalidDecisionError(
            "earliest_feasible_rule requires at least one candidate"
        )
    return SchedulingDecision.assign(candidates[0])


def _validate_decision(
    decision: object,
    patient_id: str,
    event_number: int,
    candidates: tuple[CandidateSlot, ...],
) -> SchedulingDecision:
    if not isinstance(decision, SchedulingDecision):
        raise InvalidDecisionError("Decision rule must return SchedulingDecision")
    if (decision.patient_id, decision.event_number) != (patient_id, event_number):
        raise InvalidDecisionError("Decision belongs to another patient or event")
    if not isinstance(decision.action, DecisionAction):
        raise InvalidDecisionError("Decision action is invalid")
    if decision.action is DecisionAction.ASSIGN:
        if decision.candidate is None or decision.pending_reason is not None:
            raise InvalidDecisionError(
                "ASSIGN requires one candidate and no pending reason"
            )
        if decision.candidate not in candidates:
            raise InvalidDecisionError("Decision candidate is foreign or stale")
    elif decision.candidate is not None or not isinstance(
        decision.pending_reason, PendingReason
    ):
        raise InvalidDecisionError(
            "PENDING requires one controlled reason and no candidate"
        )
    return decision


def _pending_reason_for_no_candidates(
    state: SchedulingState,
    patient_id: str,
    event_number: int,
) -> PendingReason:
    window = get_timing_window(state, patient_id, event_number)
    if window.earliest_date > state.horizon_end:
        return PendingReason.HORIZON_EXCEEDED
    return PendingReason.NO_FEASIBLE_CAPACITY


def _record_assignment(
    step: int,
    event: RouteEvent,
    status_before: EventStatus,
    candidates: tuple[CandidateSlot, ...],
    candidate: CandidateSlot,
    state_after: SchedulingState,
) -> SchedulingTraceEntry:
    return SchedulingTraceEntry(
        step=step,
        patient_id=event.patient_id,
        event_number=event.event_number,
        event_id=event.event_id,
        status_before=status_before,
        candidate_count=len(candidates),
        chosen_action=DecisionAction.ASSIGN,
        chosen_opportunity_id=candidate.opportunity_id,
        chosen_date=candidate.date,
        capacity_type=candidate.capacity_type_required,
        within_preferred_window=candidate.within_preferred_window,
        pending_reason=None,
        status_after=state_after.status_for(event.patient_id, event.event_number),
    )


def _record_pending(
    step: int,
    event: RouteEvent,
    status_before: EventStatus,
    candidate_count: int,
    reason: PendingReason,
    state_after: SchedulingState,
) -> SchedulingTraceEntry:
    return SchedulingTraceEntry(
        step=step,
        patient_id=event.patient_id,
        event_number=event.event_number,
        event_id=event.event_id,
        status_before=status_before,
        candidate_count=candidate_count,
        chosen_action=DecisionAction.PENDING,
        chosen_opportunity_id=None,
        chosen_date=None,
        capacity_type=None,
        within_preferred_window=None,
        pending_reason=reason,
        status_after=state_after.status_for(event.patient_id, event.event_number),
    )


def _summarize(
    final_state: SchedulingState,
) -> SequentialSchedulingSummary:
    state_summary = final_state.summary
    assignments = tuple(final_state.assignments.values())
    fully_completed = 0
    partially_completed = 0
    unresolved = 0
    for route in final_state.routes.patient_routes:
        assigned_count = sum(
            (route.patient_id, event.event_number) in final_state.assignments
            for event in route.events
        )
        if assigned_count == len(route.events):
            fully_completed += 1
        elif assigned_count:
            partially_completed += 1
        else:
            unresolved += 1

    late_assignments = 0
    for assignment in assignments:
        window = get_timing_window(
            final_state,
            assignment.patient_id,
            assignment.event_number,
        )
        late_assignments += assignment.date > window.preferred_latest_date

    return SequentialSchedulingSummary(
        patients_processed=len(final_state.routes.patient_routes),
        events_total=state_summary.total_events,
        events_assigned=state_summary.assigned_events,
        events_pending=state_summary.pending_events,
        events_dependency_blocked=state_summary.dependency_blocked_events,
        standard_assignments=sum(
            item.capacity_type is CapacityType.STANDARD for item in assignments
        ),
        overbooking_assignments=sum(
            item.capacity_type is CapacityType.OVERBOOKING for item in assignments
        ),
        late_assignments=late_assignments,
        capacity_used=state_summary.used_capacity,
        capacity_remaining=state_summary.remaining_capacity,
        routes_fully_completed=fully_completed,
        routes_partially_completed=partially_completed,
        routes_unresolved=unresolved,
    )


def run_sequential_scheduler(
    state: SchedulingState,
    decision_rule: DecisionRule = earliest_feasible_rule,
) -> SequentialSchedulingResult:
    """Run one forward-only applied workflow using shared feasibility mechanics.

    Patients are ordered by route start date and patient ID. Events are visited
    once in deterministic route topological order. Accepted decisions are never
    reconsidered, and capacity is changed only through ``assign_event``.
    """

    validate_state(state)
    current = state
    trace_entries: list[SchedulingTraceEntry] = []
    ordered_routes = sorted(
        state.routes.patient_routes,
        key=lambda route: (state.route_start_dates[route.patient_id], route.patient_id),
    )
    for route in ordered_routes:
        for event_number in route.graph.topological_order:
            event = route.event(event_number)
            status_before = current.status_for(route.patient_id, event_number)
            if status_before in (EventStatus.ASSIGNED, EventStatus.PENDING):
                continue
            if status_before is EventStatus.BLOCKED_BY_PREDECESSOR:
                predecessor_statuses = (
                    current.status_for(route.patient_id, predecessor)
                    for predecessor in event.dependencies
                )
                if EventStatus.PENDING not in predecessor_statuses:
                    continue
                updated = mark_pending(
                    current,
                    route.patient_id,
                    event_number,
                    PendingReason.PREDECESSOR_PENDING,
                )
                trace_entries.append(
                    _record_pending(
                        len(trace_entries) + 1,
                        event,
                        status_before,
                        0,
                        PendingReason.PREDECESSOR_PENDING,
                        updated,
                    )
                )
                current = updated
                continue

            candidates = get_candidate_slots(current, route.patient_id, event_number)
            if not candidates:
                reason = _pending_reason_for_no_candidates(
                    current,
                    route.patient_id,
                    event_number,
                )
                updated = mark_pending(
                    current,
                    route.patient_id,
                    event_number,
                    reason,
                )
                trace_entries.append(
                    _record_pending(
                        len(trace_entries) + 1,
                        event,
                        status_before,
                        0,
                        reason,
                        updated,
                    )
                )
                current = updated
                continue

            decision = _validate_decision(
                decision_rule(event, candidates, current),
                route.patient_id,
                event_number,
                candidates,
            )
            if decision.action is DecisionAction.ASSIGN:
                candidate = decision.candidate
                if candidate is None:  # narrowed by _validate_decision
                    raise InvalidDecisionError("ASSIGN candidate is missing")
                updated = assign_event(
                    current,
                    route.patient_id,
                    event_number,
                    candidate,
                )
                trace_entries.append(
                    _record_assignment(
                        len(trace_entries) + 1,
                        event,
                        status_before,
                        candidates,
                        candidate,
                        updated,
                    )
                )
            else:
                reason = decision.pending_reason
                if reason is None:  # narrowed by _validate_decision
                    raise InvalidDecisionError("PENDING reason is missing")
                updated = mark_pending(
                    current,
                    route.patient_id,
                    event_number,
                    reason,
                )
                trace_entries.append(
                    _record_pending(
                        len(trace_entries) + 1,
                        event,
                        status_before,
                        len(candidates),
                        reason,
                        updated,
                    )
                )
            current = updated

    validate_state(current)
    trace = tuple(trace_entries)
    return SequentialSchedulingResult(
        final_state=current,
        trace=trace,
        summary=_summarize(current),
    )
