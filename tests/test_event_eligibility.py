from datetime import date
from datetime import timedelta

from appointment_scheduling.scheduling import (
    EventStatus,
    assign_event,
    get_candidate_slots,
    get_timing_window,
    is_event_dependency_eligible,
)


def _assign_first(state, patient_id: str, event_number: int):
    candidates = get_candidate_slots(state, patient_id, event_number)
    assert candidates
    return assign_event(state, patient_id, event_number, candidates[0])


def test_root_dependency_eligibility_is_pure(canonical_state) -> None:
    route = canonical_state.route_for("PAT-001")

    assert is_event_dependency_eligible(route, 1, canonical_state.assignments)


def test_dependent_event_requires_its_predecessor(canonical_state) -> None:
    route = canonical_state.route_for("PAT-001")

    assert not is_event_dependency_eligible(route, 2, canonical_state.assignments)
    assigned = _assign_first(canonical_state, "PAT-001", 1)
    assert is_event_dependency_eligible(route, 2, assigned.assignments)


def test_multiple_predecessors_are_all_required(canonical_state) -> None:
    state = _assign_first(canonical_state, "PAT-001", 1)
    state = _assign_first(state, "PAT-001", 2)

    assert state.status_for("PAT-001", 5) is EventStatus.BLOCKED_BY_PREDECESSOR

    state = _assign_first(state, "PAT-001", 3)
    assert state.status_for("PAT-001", 5) is EventStatus.ELIGIBLE


def test_root_timing_window_uses_explicit_route_start(canonical_state) -> None:
    window = get_timing_window(canonical_state, "PAT-001", 1)

    assert window.earliest_date == date(2035, 1, 1)
    assert window.preferred_latest_date == date(2035, 1, 3)


def test_dependent_timing_window_uses_realized_predecessor(canonical_state) -> None:
    state = _assign_first(canonical_state, "PAT-001", 1)

    window = get_timing_window(state, "PAT-001", 2)

    assert window.earliest_date == date(2035, 1, 3)
    assert window.preferred_latest_date == date(2035, 1, 6)


def test_join_timing_uses_latest_realized_predecessor(canonical_state) -> None:
    state = _assign_first(canonical_state, "PAT-001", 1)
    state = _assign_first(state, "PAT-001", 2)
    state = _assign_first(state, "PAT-001", 3)
    predecessor_dates = [
        state.assignments[("PAT-001", number)].date for number in (2, 3)
    ]

    window = get_timing_window(state, "PAT-001", 5)

    reference = max(predecessor_dates)
    assert window.earliest_date == reference + timedelta(days=2)
    assert window.preferred_latest_date == reference + timedelta(days=6)


def test_blocked_event_has_no_candidate_slots(canonical_state) -> None:
    assert get_candidate_slots(canonical_state, "PAT-001", 2) == ()


def test_assignment_does_not_unlock_unrelated_join(canonical_state) -> None:
    state = _assign_first(canonical_state, "PAT-001", 1)
    state = _assign_first(state, "PAT-001", 2)

    assert state.status_for("PAT-001", 4) is EventStatus.ELIGIBLE
    assert state.status_for("PAT-001", 5) is EventStatus.BLOCKED_BY_PREDECESSOR
