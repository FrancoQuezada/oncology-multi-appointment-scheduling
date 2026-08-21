import pytest

from appointment_scheduling.schedulers import (
    DecisionAction,
    InvalidDecisionError,
    SchedulingDecision,
    earliest_feasible_rule,
    run_sequential_scheduler,
)
from appointment_scheduling.scheduling import (
    CapacityType,
    EventStatus,
    PendingReason,
    get_candidate_slots,
)


def test_trace_steps_are_contiguous_and_stable(canonical_sequential_result) -> None:
    trace = canonical_sequential_result.trace

    assert tuple(entry.step for entry in trace) == tuple(range(1, len(trace) + 1))
    assert len(trace) == 20


def test_assignment_trace_contains_auditable_fields(
    canonical_sequential_result,
) -> None:
    entry = next(
        item
        for item in canonical_sequential_result.trace
        if item.chosen_action is DecisionAction.ASSIGN
    )

    assert entry.status_before is EventStatus.ELIGIBLE
    assert entry.status_after is EventStatus.ASSIGNED
    assert entry.candidate_count > 0
    assert entry.chosen_opportunity_id is not None
    assert entry.chosen_date is not None
    assert entry.capacity_type is not None
    assert entry.pending_reason is None


def test_standard_assignment_is_traced(canonical_sequential_result) -> None:
    assert any(
        entry.capacity_type is CapacityType.STANDARD
        for entry in canonical_sequential_result.trace
    )


def test_overbooking_assignment_is_traced(canonical_sequential_result) -> None:
    overbooked = [
        entry
        for entry in canonical_sequential_result.trace
        if entry.capacity_type is CapacityType.OVERBOOKING
    ]

    assert len(overbooked) == canonical_sequential_result.summary.overbooking_assignments
    assert overbooked[0].chosen_opportunity_id is not None


def test_late_feasible_assignment_is_retained_in_trace(
    canonical_sequential_result,
) -> None:
    late = [
        entry
        for entry in canonical_sequential_result.trace
        if entry.chosen_action is DecisionAction.ASSIGN
        and entry.within_preferred_window is False
    ]

    assert late
    assert len(late) == canonical_sequential_result.summary.late_assignments


def test_rule_receives_current_event_candidates_and_state(canonical_state) -> None:
    observed = []

    def observing_rule(event, candidates, state):
        observed.append(
            (
                event.patient_id,
                event.event_number,
                candidates[0].patient_id,
                state.status_for(event.patient_id, event.event_number),
            )
        )
        return earliest_feasible_rule(event, candidates, state)

    run_sequential_scheduler(canonical_state, observing_rule)

    assert observed
    assert all(patient == candidate_patient for patient, _, candidate_patient, _ in observed)
    assert all(status is EventStatus.ELIGIBLE for _, _, _, status in observed)


def test_invalid_rule_output_fails_without_mutating_input(canonical_state) -> None:
    before_capacities = dict(canonical_state.capacity_by_opportunity)

    with pytest.raises(InvalidDecisionError, match="SchedulingDecision"):
        run_sequential_scheduler(canonical_state, lambda event, candidates, state: None)

    assert canonical_state.assignments == {}
    assert dict(canonical_state.capacity_by_opportunity) == before_capacities


def test_foreign_candidate_is_rejected(canonical_state) -> None:
    foreign = get_candidate_slots(canonical_state, "PAT-002", 1)[0]

    def foreign_rule(event, candidates, state):
        return SchedulingDecision.assign(foreign)

    with pytest.raises(InvalidDecisionError, match="another patient|foreign"):
        run_sequential_scheduler(canonical_state, foreign_rule)

    assert canonical_state.assignments == {}


def test_stale_candidate_is_rejected(canonical_state) -> None:
    stale = get_candidate_slots(canonical_state, "PAT-004", 1)[0]

    def stale_rule(event, candidates, state):
        if (event.patient_id, event.event_number) == ("PAT-004", 1):
            return SchedulingDecision.assign(stale)
        return earliest_feasible_rule(event, candidates, state)

    with pytest.raises(InvalidDecisionError, match="stale"):
        run_sequential_scheduler(canonical_state, stale_rule)

    assert canonical_state.assignments == {}


def test_impossible_decision_combination_is_rejected(canonical_state) -> None:
    def malformed_rule(event, candidates, state):
        return SchedulingDecision(
            patient_id=event.patient_id,
            event_number=event.event_number,
            action=DecisionAction.ASSIGN,
            candidate=candidates[0],
            pending_reason=PendingReason.MANUAL_DECISION,
        )

    with pytest.raises(InvalidDecisionError, match="no pending reason"):
        run_sequential_scheduler(canonical_state, malformed_rule)
