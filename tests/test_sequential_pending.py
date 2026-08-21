from appointment_scheduling.schedulers import (
    DecisionAction,
    SchedulingDecision,
    earliest_feasible_rule,
    run_sequential_scheduler,
)
from appointment_scheduling.scheduling import EventStatus, PendingReason


def test_no_candidate_event_becomes_pending(canonical_sequential_result) -> None:
    entry = next(
        item
        for item in canonical_sequential_result.trace
        if (item.patient_id, item.event_number) == ("PAT-004", 5)
    )

    assert entry.chosen_action is DecisionAction.PENDING
    assert entry.candidate_count == 0
    assert entry.pending_reason is PendingReason.NO_FEASIBLE_CAPACITY
    assert entry.status_after is EventStatus.PENDING


def test_horizon_overflow_has_specific_pending_reason(
    canonical_sequential_result,
) -> None:
    entry = next(
        item
        for item in canonical_sequential_result.trace
        if (item.patient_id, item.event_number) == ("PAT-003", 6)
    )

    assert entry.candidate_count == 0
    assert entry.pending_reason is PendingReason.HORIZON_EXCEEDED


def test_pending_predecessor_is_propagated_to_downstream_events(
    canonical_state,
) -> None:
    def pending_branch_rule(event, candidates, state):
        if (event.patient_id, event.event_number) == ("PAT-001", 2):
            return SchedulingDecision.pending(
                event.patient_id,
                event.event_number,
                PendingReason.MANUAL_DECISION,
            )
        return earliest_feasible_rule(event, candidates, state)

    result = run_sequential_scheduler(canonical_state, pending_branch_rule)

    assert result.final_state.pending_events[("PAT-001", 2)].reason is PendingReason.MANUAL_DECISION
    assert result.final_state.pending_events[("PAT-001", 4)].reason is PendingReason.PREDECESSOR_PENDING
    assert result.final_state.pending_events[("PAT-001", 5)].reason is PendingReason.PREDECESSOR_PENDING


def test_other_branch_remains_schedulable_when_one_branch_is_pending(
    canonical_state,
) -> None:
    def pending_branch_rule(event, candidates, state):
        if (event.patient_id, event.event_number) == ("PAT-001", 2):
            return SchedulingDecision.pending(
                event.patient_id,
                event.event_number,
                PendingReason.MANUAL_DECISION,
            )
        return earliest_feasible_rule(event, candidates, state)

    result = run_sequential_scheduler(canonical_state, pending_branch_rule)

    assert result.final_state.status_for("PAT-001", 3) is EventStatus.ASSIGNED
    assert result.final_state.status_for("PAT-001", 5) is EventStatus.PENDING
    assert ("PAT-001", 5) not in result.final_state.assignments


def test_propagated_pending_trace_distinguishes_its_reason(canonical_state) -> None:
    def pending_root_rule(event, candidates, state):
        if (event.patient_id, event.event_number) == ("PAT-001", 1):
            return SchedulingDecision.pending(
                event.patient_id,
                event.event_number,
                PendingReason.MANUAL_DECISION,
            )
        return earliest_feasible_rule(event, candidates, state)

    result = run_sequential_scheduler(canonical_state, pending_root_rule)
    propagated = [
        entry
        for entry in result.trace
        if entry.patient_id == "PAT-001" and entry.event_number != 1
    ]

    assert propagated
    assert all(
        entry.pending_reason is PendingReason.PREDECESSOR_PENDING
        for entry in propagated
    )
    assert all(entry.candidate_count == 0 for entry in propagated)


def test_rule_can_explicitly_decline_existing_candidates(canonical_state) -> None:
    def decline_rule(event, candidates, state):
        return SchedulingDecision.pending(
            event.patient_id,
            event.event_number,
            PendingReason.MANUAL_DECISION,
        )

    result = run_sequential_scheduler(canonical_state, decline_rule)
    first = result.trace[0]

    assert first.candidate_count > 0
    assert first.pending_reason is PendingReason.MANUAL_DECISION
    assert result.summary.events_assigned == 0
    assert result.summary.routes_unresolved == 4


def test_complete_run_leaves_no_dependency_blocked_events(
    canonical_sequential_result,
) -> None:
    assert canonical_sequential_result.summary.events_dependency_blocked == 0
    assert all(
        entry.status_after in (EventStatus.ASSIGNED, EventStatus.PENDING)
        for entry in canonical_sequential_result.trace
    )


def test_partial_route_metrics_include_unresolved_terminals(
    canonical_sequential_result,
) -> None:
    summary = canonical_sequential_result.summary

    assert summary.events_assigned == 18
    assert summary.events_pending == 2
    assert summary.routes_partially_completed == 2
