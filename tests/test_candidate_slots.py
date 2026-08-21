from datetime import date

from appointment_scheduling.scheduling import (
    CapacityType,
    EventStatus,
    assign_event,
    get_candidate_slots,
)


def _assign_first(state, patient_id: str, event_number: int):
    candidate = get_candidate_slots(state, patient_id, event_number)[0]
    return assign_event(state, patient_id, event_number, candidate)


def test_candidates_before_earliest_date_are_excluded(canonical_state) -> None:
    state = _assign_first(canonical_state, "PAT-001", 1)
    candidates = get_candidate_slots(state, "PAT-001", 2)

    assert candidates
    assert min(candidate.date for candidate in candidates) >= date(2035, 1, 3)


def test_late_candidates_remain_available_and_are_annotated(canonical_state) -> None:
    candidates = get_candidate_slots(canonical_state, "PAT-001", 1)

    assert any(candidate.within_preferred_window for candidate in candidates)
    assert any(not candidate.within_preferred_window for candidate in candidates)
    assert any(
        candidate.date > date(2035, 1, 3) and not candidate.within_preferred_window
        for candidate in candidates
    )


def test_compatible_set_returns_alternative_resources(canonical_state) -> None:
    candidates = get_candidate_slots(canonical_state, "PAT-001", 1)

    assert {candidate.clinician_id for candidate in candidates} >= {
        "CLINICIAN-01",
        "CLINICIAN-02",
    }
    assert any(not candidate.uses_preferred_resource for candidate in candidates)


def test_fixed_resource_excludes_other_clinicians(canonical_state) -> None:
    candidates = get_candidate_slots(canonical_state, "PAT-003", 1)

    assert candidates
    assert {candidate.clinician_id for candidate in candidates} == {"CLINICIAN-06"}
    assert {candidate.agenda_id for candidate in candidates} == {"AGENDA-DEMO-06"}


def test_zero_capacity_opportunity_is_excluded(demo_scheduling_components) -> None:
    _, routes, availability, starts = demo_scheduling_components
    target = availability["event_type"].eq("EVENT-A1")
    opportunity_id = str(availability.loc[target, "block_id"].iloc[0])
    row_index = availability.index[target][0]
    configured = int(
        availability.loc[row_index, "base_capacity"]
        + availability.loc[row_index, "overbooking_capacity"]
    )
    availability.loc[row_index, "blocked_capacity"] = configured
    availability.loc[row_index, "standard_available_capacity"] = 0
    availability.loc[row_index, "total_available_capacity"] = 0
    availability.loc[row_index, "remaining_capacity"] = 0

    from appointment_scheduling.scheduling import build_scheduling_state

    state = build_scheduling_state(routes, availability, starts)
    candidates = get_candidate_slots(state, "PAT-001", 1)

    assert opportunity_id not in {candidate.opportunity_id for candidate in candidates}


def test_standard_candidates_are_labeled(canonical_state) -> None:
    candidate = get_candidate_slots(canonical_state, "PAT-001", 1)[0]

    assert candidate.capacity_type_required is CapacityType.STANDARD
    assert candidate.standard_remaining_capacity > 0


def test_candidate_ordering_is_deterministic(canonical_state) -> None:
    first = get_candidate_slots(canonical_state, "PAT-001", 1)
    second = get_candidate_slots(canonical_state, "PAT-001", 1)
    ordering = tuple(
        (
            item.date,
            item.agenda_id,
            item.clinician_id,
            item.schedule_key,
            item.opportunity_id,
        )
        for item in first
    )

    assert first == second
    assert ordering == tuple(sorted(ordering))


def test_no_candidate_does_not_implicitly_mark_pending(canonical_state) -> None:
    state = _assign_first(canonical_state, "PAT-004", 1)
    state = _assign_first(state, "PAT-004", 2)
    state = _assign_first(state, "PAT-004", 3)

    assert state.status_for("PAT-004", 5) is EventStatus.ELIGIBLE
    assert get_candidate_slots(state, "PAT-004", 5) == ()
    assert ("PAT-004", 5) not in state.pending_events


def test_candidate_model_is_bound_to_patient_event_and_opportunity(canonical_state) -> None:
    candidate = get_candidate_slots(canonical_state, "PAT-001", 1)[0]

    assert candidate.patient_id == "PAT-001"
    assert candidate.event_number == 1
    assert candidate.event_id == "EVENT-A1"
    assert candidate.opportunity_id.startswith("SUPPLY-BLOCK-")
