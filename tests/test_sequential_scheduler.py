from datetime import date

from appointment_scheduling.schedulers import (
    SchedulingDecision,
    earliest_feasible_rule,
    run_sequential_scheduler,
)
from appointment_scheduling.scheduling import (
    CapacityType,
    EventStatus,
    PendingReason,
    build_scheduling_state,
    get_candidate_slots,
    validate_state,
)


def test_sequential_scheduler_completes_linear_route(
    canonical_sequential_result,
) -> None:
    final_state = canonical_sequential_result.final_state
    route = final_state.route_for("PAT-002")

    assert all(
        final_state.status_for(route.patient_id, number) is EventStatus.ASSIGNED
        for number in route.graph.topological_order
    )


def test_patient_order_uses_start_date_then_patient_id(
    demo_scheduling_components,
) -> None:
    _, routes, availability, starts = demo_scheduling_components
    starts["PAT-004"] = date(2034, 12, 31)
    state = build_scheduling_state(routes, availability, starts)

    result = run_sequential_scheduler(state)
    first_seen = tuple(dict.fromkeys(entry.patient_id for entry in result.trace))

    assert first_seen == ("PAT-004", "PAT-001", "PAT-002", "PAT-003")


def test_event_order_follows_route_topology(canonical_sequential_result) -> None:
    numbers = tuple(
        entry.event_number
        for entry in canonical_sequential_result.trace
        if entry.patient_id == "PAT-001"
    )

    assert numbers == (1, 2, 3, 4, 5)


def test_earliest_demo_rule_selects_first_shared_candidate(canonical_state) -> None:
    candidates = get_candidate_slots(canonical_state, "PAT-001", 1)
    event = canonical_state.event("PAT-001", 1)

    decision = earliest_feasible_rule(event, candidates, canonical_state)

    assert decision.candidate == candidates[0]


def test_scheduler_assignment_uses_shared_capacity_transition(canonical_state) -> None:
    calls = 0

    def assign_only_first(event, candidates, state):
        nonlocal calls
        calls += 1
        if calls == 1:
            return SchedulingDecision.assign(candidates[0])
        return SchedulingDecision.pending(
            event.patient_id,
            event.event_number,
            PendingReason.MANUAL_DECISION,
        )

    result = run_sequential_scheduler(canonical_state, assign_only_first)
    changed = [
        key
        for key in canonical_state.capacity_by_opportunity
        if canonical_state.capacity_by_opportunity[key]
        != result.final_state.capacity_by_opportunity[key]
    ]

    assert len(changed) == 1
    before = canonical_state.capacity_by_opportunity[changed[0]]
    after = result.final_state.capacity_by_opportunity[changed[0]]
    assert after.used_total_capacity == before.used_total_capacity + 1


def test_successor_assignment_respects_realized_predecessor(
    canonical_sequential_result,
) -> None:
    assignments = canonical_sequential_result.final_state.assignments
    predecessor = assignments[("PAT-001", 1)]
    successor = assignments[("PAT-001", 2)]

    assert (successor.date - predecessor.date).days >= 2


def test_branching_route_processes_both_branches(canonical_sequential_result) -> None:
    final_state = canonical_sequential_result.final_state

    assert final_state.status_for("PAT-001", 2) is EventStatus.ASSIGNED
    assert final_state.status_for("PAT-001", 3) is EventStatus.ASSIGNED


def test_join_is_processed_after_both_branches(canonical_sequential_result) -> None:
    entries = {
        (entry.patient_id, entry.event_number): entry.step
        for entry in canonical_sequential_result.trace
    }

    assert entries[("PAT-001", 5)] > entries[("PAT-001", 2)]
    assert entries[("PAT-001", 5)] > entries[("PAT-001", 3)]


def test_accepted_decisions_are_not_reconsidered(canonical_sequential_result) -> None:
    processed_keys = [
        (entry.patient_id, entry.event_number)
        for entry in canonical_sequential_result.trace
    ]

    assert len(processed_keys) == len(set(processed_keys))
    assert len(canonical_sequential_result.final_state.assignments) == 18


def test_complete_run_is_deterministic(canonical_state) -> None:
    first = run_sequential_scheduler(canonical_state)
    second = run_sequential_scheduler(canonical_state)

    assert first == second
    assert first.final_state.capacity_by_opportunity == second.final_state.capacity_by_opportunity


def test_final_state_validates(canonical_sequential_result) -> None:
    validate_state(canonical_sequential_result.final_state)


def test_route_completion_metrics_are_explicit(canonical_sequential_result) -> None:
    summary = canonical_sequential_result.summary

    assert summary.routes_fully_completed == 2
    assert summary.routes_partially_completed == 2
    assert summary.routes_unresolved == 0
    assert (
        summary.routes_fully_completed
        + summary.routes_partially_completed
        + summary.routes_unresolved
        == summary.patients_processed
    )


def test_overbooking_assignments_only_apply_to_permitted_events(
    canonical_sequential_result,
) -> None:
    state = canonical_sequential_result.final_state
    overbooked = [
        assignment
        for assignment in state.assignments.values()
        if assignment.capacity_type is CapacityType.OVERBOOKING
    ]

    assert overbooked
    assert all(
        state.event(item.patient_id, item.event_number).overbooking_allowed
        for item in overbooked
    )
