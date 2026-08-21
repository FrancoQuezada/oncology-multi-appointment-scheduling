"""Policy-independent metrics for completed scheduling results."""

from __future__ import annotations

from appointment_scheduling.schedulers import (
    DecisionAction,
    SequentialSchedulingResult,
)
from appointment_scheduling.scheduling import (
    CapacityType,
    SchedulingState,
    get_timing_window,
)

from appointment_scheduling.research.models import (
    PolicyMetrics,
    PolicyName,
    ResearchOutcome,
    ResearchSchedulingResult,
    ResearchTraceEntry,
)


def compute_policy_metrics(
    final_state: SchedulingState,
    trace: tuple[ResearchTraceEntry, ...],
) -> PolicyMetrics:
    """Compute common metrics without knowledge of the producing policy."""

    del trace
    state_summary = final_state.summary
    assignments = tuple(final_state.assignments.values())
    total_routes = len(final_state.routes.patient_routes)
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

    tardiness = []
    for assignment in assignments:
        window = get_timing_window(
            final_state,
            assignment.patient_id,
            assignment.event_number,
        )
        tardiness.append(
            max((assignment.date - window.preferred_latest_date).days, 0)
        )
    assigned_events = len(assignments)
    late_assignments = sum(value > 0 for value in tardiness)
    overbooking_assignments = sum(
        assignment.capacity_type is CapacityType.OVERBOOKING
        for assignment in assignments
    )
    return PolicyMetrics(
        total_events=state_summary.total_events,
        assigned_events=assigned_events,
        pending_events=state_summary.pending_events,
        assignment_rate=(
            assigned_events / state_summary.total_events
            if state_summary.total_events
            else 0.0
        ),
        fully_completed_routes=fully_completed,
        partially_completed_routes=partially_completed,
        unresolved_routes=unresolved,
        route_completion_rate=(
            fully_completed / total_routes if total_routes else 0.0
        ),
        late_assignments=late_assignments,
        late_assignment_rate=(
            late_assignments / assigned_events if assigned_events else 0.0
        ),
        total_tardiness_days=sum(tardiness),
        mean_tardiness_days=(
            sum(tardiness) / assigned_events if assigned_events else 0.0
        ),
        max_tardiness_days=max(tardiness, default=0),
        standard_assignments=sum(
            assignment.capacity_type is CapacityType.STANDARD
            for assignment in assignments
        ),
        overbooking_assignments=overbooking_assignments,
        overbooking_rate=(
            overbooking_assignments / assigned_events if assigned_events else 0.0
        ),
        capacity_used=state_summary.used_capacity,
        capacity_remaining=state_summary.remaining_capacity,
    )


def research_result_from_sequential(
    policy_name: PolicyName,
    result: SequentialSchedulingResult,
) -> ResearchSchedulingResult:
    """Convert a shared workflow result into the common research contract."""

    trace = tuple(
        ResearchTraceEntry(
            step=entry.step,
            policy=policy_name,
            patient_id=entry.patient_id,
            event_number=entry.event_number,
            candidate_count=entry.candidate_count,
            chosen_opportunity_id=entry.chosen_opportunity_id,
            chosen_date=entry.chosen_date,
            capacity_type=entry.capacity_type,
            within_preferred_window=entry.within_preferred_window,
            outcome=(
                ResearchOutcome.ASSIGNED
                if entry.chosen_action is DecisionAction.ASSIGN
                else ResearchOutcome.PENDING
            ),
            pending_reason=entry.pending_reason,
        )
        for entry in result.trace
    )
    return ResearchSchedulingResult(
        policy_name=policy_name,
        final_state=result.final_state,
        trace=trace,
        metrics=compute_policy_metrics(result.final_state, trace),
    )
