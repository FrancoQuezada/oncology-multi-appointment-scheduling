from datetime import date

import pandas as pd
import pytest

from appointment_scheduling.scheduling import (
    AssignmentConflictError,
    EventStatus,
    PendingReason,
    PendingStateError,
    SchedulingValidationError,
    assign_event,
    build_scheduling_state,
    get_candidate_slots,
    get_timing_window,
    mark_pending,
    validate_state,
)


def test_clean_initial_state_builds_successfully(canonical_state) -> None:
    summary = canonical_state.summary

    assert summary.patients == 4
    assert summary.total_events == 20
    assert summary.assigned_events == 0
    assert summary.eligible_events == 4
    assert summary.dependency_blocked_events == 16
    assert summary.pending_events == 0
    assert summary.used_capacity == 0
    assert summary.remaining_capacity == summary.total_capacity


def test_root_events_are_initially_eligible(canonical_state) -> None:
    for patient_id in canonical_state.routes.routes_by_patient:
        assert canonical_state.status_for(patient_id, 1) is EventStatus.ELIGIBLE


def test_dependent_events_are_initially_blocked(canonical_state) -> None:
    assert (
        canonical_state.status_for("PAT-001", 2)
        is EventStatus.BLOCKED_BY_PREDECESSOR
    )
    assert (
        canonical_state.status_for("PAT-001", 5)
        is EventStatus.BLOCKED_BY_PREDECESSOR
    )


def test_assignment_unlocks_a_successor(canonical_state) -> None:
    candidate = get_candidate_slots(canonical_state, "PAT-001", 1)[0]
    before = canonical_state.capacity_by_opportunity[
        candidate.opportunity_id
    ].remaining_total_capacity

    updated = assign_event(canonical_state, "PAT-001", 1, candidate)
    after = updated.capacity_by_opportunity[
        candidate.opportunity_id
    ].remaining_total_capacity
    window = get_timing_window(updated, "PAT-001", 2)

    assert updated.status_for("PAT-001", 1) is EventStatus.ASSIGNED
    assert updated.status_for("PAT-001", 2) is EventStatus.ELIGIBLE
    assert updated.status_for("PAT-001", 3) is EventStatus.ELIGIBLE
    assert after == before - 1
    assert window.earliest_date == date(2035, 1, 3)


def test_pending_is_an_explicit_transition_without_propagation(canonical_state) -> None:
    updated = mark_pending(
        canonical_state,
        "PAT-001",
        1,
        PendingReason.NO_FEASIBLE_CAPACITY,
    )

    assert updated.status_for("PAT-001", 1) is EventStatus.PENDING
    assert (
        updated.status_for("PAT-001", 2)
        is EventStatus.BLOCKED_BY_PREDECESSOR
    )
    assert ("PAT-001", 2) not in updated.pending_events


def test_pending_and_assigned_cannot_coexist(canonical_state) -> None:
    candidate = get_candidate_slots(canonical_state, "PAT-001", 1)[0]
    assigned = assign_event(canonical_state, "PAT-001", 1, candidate)

    with pytest.raises(AssignmentConflictError, match="cannot become pending"):
        mark_pending(assigned, "PAT-001", 1, PendingReason.MANUAL_DECISION)


def test_repeated_pending_transition_fails(canonical_state) -> None:
    pending = mark_pending(
        canonical_state,
        "PAT-001",
        1,
        PendingReason.MANUAL_DECISION,
    )

    with pytest.raises(PendingStateError, match="already pending"):
        mark_pending(pending, "PAT-001", 1, PendingReason.MANUAL_DECISION)


def test_state_construction_is_deterministic(demo_scheduling_components) -> None:
    _, routes, availability, starts = demo_scheduling_components

    first = build_scheduling_state(routes, availability, starts)
    second = build_scheduling_state(routes, availability.sample(frac=1), starts)

    assert first == second


def test_build_does_not_mutate_static_inputs(demo_scheduling_components) -> None:
    route_rows, routes, availability, starts = demo_scheduling_components
    route_rows_before = route_rows.copy(deep=True)
    availability_before = availability.copy(deep=True)
    starts_before = dict(starts)

    state = build_scheduling_state(routes, availability, starts)

    pd.testing.assert_frame_equal(route_rows, route_rows_before)
    pd.testing.assert_frame_equal(availability, availability_before)
    assert starts == starts_before
    assert state.routes is routes


def test_route_start_dates_are_explicit_and_complete(demo_scheduling_components) -> None:
    _, routes, availability, starts = demo_scheduling_components
    starts.pop("PAT-004")

    with pytest.raises(SchedulingValidationError, match="missing=.*PAT-004"):
        build_scheduling_state(routes, availability, starts)


def test_state_invariants_hold_after_assignment(canonical_state) -> None:
    candidate = get_candidate_slots(canonical_state, "PAT-001", 1)[0]
    updated = assign_event(canonical_state, "PAT-001", 1, candidate)

    validate_state(updated)
    assert updated.summary.assigned_events == 1
    assert updated.summary.used_capacity == 1
    assert updated.summary.remaining_capacity == updated.summary.total_capacity - 1
