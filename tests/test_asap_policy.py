from appointment_scheduling.research import (
    PolicyName,
    ResearchOutcome,
    run_asap_policy,
)
from appointment_scheduling.scheduling import (
    CapacityType,
    EventStatus,
    build_scheduling_state,
    get_candidate_slots,
    validate_state,
)


def test_asap_runs_end_to_end(canonical_state) -> None:
    result = run_asap_policy(canonical_state)

    assert result.policy_name is PolicyName.ASAP
    assert result.metrics.total_events == 20
    assert result.metrics.assigned_events == 18
    assert len(result.trace) == 20


def test_asap_selects_earliest_feasible_candidate(canonical_state) -> None:
    expected = get_candidate_slots(canonical_state, "PAT-001", 1)[0]

    result = run_asap_policy(canonical_state)
    first = result.trace[0]

    assert first.chosen_opportunity_id == expected.opportunity_id
    assert first.chosen_date == expected.date


def test_asap_tie_breaking_is_deterministic(canonical_state) -> None:
    first = run_asap_policy(canonical_state)
    second = run_asap_policy(canonical_state)

    assert first.trace == second.trace
    assert first.final_state.assignments == second.final_state.assignments


def test_asap_uses_shared_copy_on_write_capacity(canonical_state) -> None:
    result = run_asap_policy(canonical_state)

    assert canonical_state.assignments == {}
    assert canonical_state.summary.used_capacity == 0
    assert result.final_state.summary.used_capacity == result.metrics.assigned_events


def test_asap_handles_both_branches(canonical_state) -> None:
    result = run_asap_policy(canonical_state)

    assert result.final_state.status_for("PAT-001", 2) is EventStatus.ASSIGNED
    assert result.final_state.status_for("PAT-001", 3) is EventStatus.ASSIGNED


def test_asap_join_waits_for_both_predecessors(canonical_state) -> None:
    result = run_asap_policy(canonical_state)
    steps = {
        (entry.patient_id, entry.event_number): entry.step for entry in result.trace
    }

    assert steps[("PAT-001", 5)] > steps[("PAT-001", 2)]
    assert steps[("PAT-001", 5)] > steps[("PAT-001", 3)]


def test_asap_propagates_an_unresolved_branch_to_its_join(
    demo_scheduling_components,
) -> None:
    _, routes, availability, starts = demo_scheduling_components
    target = availability["event_type"].eq("EVENT-A2")
    availability.loc[target, "blocked_capacity"] = (
        availability.loc[target, "base_capacity"]
        + availability.loc[target, "overbooking_capacity"]
    )
    availability.loc[target, "standard_available_capacity"] = 0
    availability.loc[target, "total_available_capacity"] = 0
    availability.loc[target, "remaining_capacity"] = 0
    state = build_scheduling_state(routes, availability, starts)

    result = run_asap_policy(state)

    assert result.final_state.status_for("PAT-001", 2) is EventStatus.PENDING
    assert result.final_state.status_for("PAT-001", 3) is EventStatus.ASSIGNED
    assert result.final_state.status_for("PAT-001", 5) is EventStatus.PENDING
    assert ("PAT-001", 5) not in result.final_state.assignments


def test_asap_records_controlled_pending_outcomes(canonical_state) -> None:
    result = run_asap_policy(canonical_state)
    pending = [entry for entry in result.trace if entry.outcome is ResearchOutcome.PENDING]

    assert len(pending) == 2
    assert all(entry.pending_reason is not None for entry in pending)


def test_asap_assigns_late_feasible_candidates(canonical_state) -> None:
    result = run_asap_policy(canonical_state)
    late = [
        entry
        for entry in result.trace
        if entry.outcome is ResearchOutcome.ASSIGNED
        and entry.within_preferred_window is False
    ]

    assert late
    assert len(late) == result.metrics.late_assignments


def test_asap_overbooking_uses_shared_permission(canonical_state) -> None:
    result = run_asap_policy(canonical_state)
    overbooked = [
        assignment
        for assignment in result.final_state.assignments.values()
        if assignment.capacity_type is CapacityType.OVERBOOKING
    ]

    assert len(overbooked) == result.metrics.overbooking_assignments == 1
    assert all(
        result.final_state.event(item.patient_id, item.event_number).overbooking_allowed
        for item in overbooked
    )


def test_asap_final_state_validates(canonical_state) -> None:
    validate_state(run_asap_policy(canonical_state).final_state)
