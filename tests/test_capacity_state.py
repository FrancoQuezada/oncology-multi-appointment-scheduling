from datetime import date

import pandas as pd
import pytest

from appointment_scheduling.routes import (
    PathwayEventTemplate,
    PathwayTemplate,
    ResourceMode,
    preprocess_routes,
)
from appointment_scheduling.scheduling import (
    AssignmentConflictError,
    CapacityState,
    CapacityStateError,
    CapacityType,
    EventStatus,
    SchedulingState,
    StaleCandidateError,
    assign_event,
    build_scheduling_state,
    get_candidate_slots,
    validate_state,
)


def _small_state(
    demo_scheduling_components,
    *,
    patient_count: int = 3,
    standard_capacity: int = 2,
    total_capacity: int = 3,
    overbooking_allowed: bool = True,
    opportunity_count: int = 1,
    min_spacing_days: int = 0,
):
    _, _, demo_availability, _ = demo_scheduling_components
    route_rows = []
    for patient_number in range(11, 11 + patient_count):
        route_rows.append(
            {
                "patient_id": f"PAT-{patient_number:03d}",
                "pathway_id": "PATHWAY-Z",
                "event_number": 1,
                "event_id": "EVENT-Z1",
                "agenda_id": "AGENDA-DEMO-01",
                "event_type": "EVENT-Z1",
                "min_spacing_days": min_spacing_days,
                "preferred_max_spacing_days": max(min_spacing_days, 2),
                "dependencies": "[]",
                "clinician_id": "CLINICIAN-01",
                "service_id": "SERVICE-A",
                "section_id": "SECTION-A1",
                "modality": "IN_PERSON",
                "resource_mode": "COMPATIBLE_SET",
                "overbooking_allowed": overbooking_allowed,
            }
        )
    template = PathwayTemplate(
        pathway_id="PATHWAY-Z",
        events=(
            PathwayEventTemplate(
                1,
                "EVENT-Z1",
                "EVENT-Z1",
                (),
                min_spacing_days,
                max(min_spacing_days, 2),
                ResourceMode.COMPATIBLE_SET,
            ),
        ),
    )
    routes = preprocess_routes(pd.DataFrame(route_rows), (template,))

    source = demo_availability.iloc[[0]].copy()
    opportunities = []
    for index in range(opportunity_count):
        row = source.copy()
        row.loc[:, "block_id"] = f"SUPPLY-BLOCK-{901 + index:03d}"
        row.loc[:, "schedule_key"] = f"SCHEDULE-DEMO-{901 + index:03d}"
        row.loc[:, "date"] = pd.Timestamp(2035, 1, 1)
        row.loc[:, "event_type"] = "EVENT-Z1"
        row.loc[:, "base_capacity"] = standard_capacity
        row.loc[:, "overbooking_capacity"] = total_capacity - standard_capacity
        row.loc[:, "blocked_capacity"] = 0
        row.loc[:, "standard_available_capacity"] = standard_capacity
        row.loc[:, "total_available_capacity"] = total_capacity
        row.loc[:, "used_capacity"] = 0
        row.loc[:, "remaining_capacity"] = total_capacity
        opportunities.append(row)
    availability = pd.concat(opportunities, ignore_index=True)
    starts = {
        patient_id: date(2035, 1, 1) for patient_id in routes.routes_by_patient
    }
    return build_scheduling_state(routes, availability, starts)


def test_assignment_consumes_exactly_one_capacity_unit(demo_scheduling_components) -> None:
    state = _small_state(demo_scheduling_components)
    candidate = get_candidate_slots(state, "PAT-011", 1)[0]

    updated = assign_event(state, "PAT-011", 1, candidate)

    before = state.capacity_by_opportunity[candidate.opportunity_id]
    after = updated.capacity_by_opportunity[candidate.opportunity_id]
    assert after.used_total_capacity == before.used_total_capacity + 1
    assert after.remaining_total_capacity == before.remaining_total_capacity - 1


def test_assignment_changes_no_unrelated_opportunity(demo_scheduling_components) -> None:
    state = _small_state(demo_scheduling_components, opportunity_count=2)
    candidate = get_candidate_slots(state, "PAT-011", 1)[0]
    unrelated = next(
        key for key in state.capacity_by_opportunity if key != candidate.opportunity_id
    )

    updated = assign_event(state, "PAT-011", 1, candidate)

    assert (
        updated.capacity_by_opportunity[unrelated]
        == state.capacity_by_opportunity[unrelated]
    )


def test_broad_resource_key_cannot_consume_multiple_rows(demo_scheduling_components) -> None:
    state = _small_state(demo_scheduling_components, opportunity_count=2)
    candidates = get_candidate_slots(state, "PAT-011", 1)
    assert candidates[0].date == candidates[1].date
    assert candidates[0].clinician_id == candidates[1].clinician_id

    updated = assign_event(state, "PAT-011", 1, candidates[0])
    changed = [
        key
        for key in state.capacity_by_opportunity
        if state.capacity_by_opportunity[key]
        != updated.capacity_by_opportunity[key]
    ]

    assert changed == [candidates[0].opportunity_id]


def test_standard_capacity_is_exhausted_before_overbooking(
    demo_scheduling_components,
) -> None:
    state = _small_state(demo_scheduling_components)
    capacity_types = []
    for patient_id in ("PAT-011", "PAT-012", "PAT-013"):
        candidate = get_candidate_slots(state, patient_id, 1)[0]
        capacity_types.append(candidate.capacity_type_required)
        state = assign_event(state, patient_id, 1, candidate)

    assert capacity_types == [
        CapacityType.STANDARD,
        CapacityType.STANDARD,
        CapacityType.OVERBOOKING,
    ]
    assert state.summary.overbooking_used == 1


def test_overbooking_disallowed_event_cannot_use_extra_capacity(
    demo_scheduling_components,
) -> None:
    state = _small_state(
        demo_scheduling_components,
        overbooking_allowed=False,
    )
    for patient_id in ("PAT-011", "PAT-012"):
        candidate = get_candidate_slots(state, patient_id, 1)[0]
        state = assign_event(state, patient_id, 1, candidate)

    assert get_candidate_slots(state, "PAT-013", 1) == ()
    assert state.status_for("PAT-013", 1) is EventStatus.ELIGIBLE


def test_stale_candidate_fails_after_capacity_changes(demo_scheduling_components) -> None:
    state = _small_state(demo_scheduling_components)
    first = get_candidate_slots(state, "PAT-011", 1)[0]
    stale = get_candidate_slots(state, "PAT-012", 1)[0]
    updated = assign_event(state, "PAT-011", 1, first)

    with pytest.raises(StaleCandidateError, match="stale"):
        assign_event(updated, "PAT-012", 1, stale)


def test_double_assignment_fails(demo_scheduling_components) -> None:
    state = _small_state(demo_scheduling_components)
    candidate = get_candidate_slots(state, "PAT-011", 1)[0]
    updated = assign_event(state, "PAT-011", 1, candidate)

    with pytest.raises(AssignmentConflictError, match="already assigned"):
        assign_event(updated, "PAT-011", 1, candidate)


def test_old_state_is_unchanged_after_copy_on_write_assignment(
    demo_scheduling_components,
) -> None:
    state = _small_state(demo_scheduling_components)
    candidate = get_candidate_slots(state, "PAT-011", 1)[0]

    updated = assign_event(state, "PAT-011", 1, candidate)

    assert state.assignments == {}
    assert state.capacity_by_opportunity[candidate.opportunity_id].used_total_capacity == 0
    assert updated.assignments[("PAT-011", 1)].capacity_type is CapacityType.STANDARD


def test_capacity_assignment_invariant_detects_tampering(
    demo_scheduling_components,
) -> None:
    state = _small_state(demo_scheduling_components)
    opportunity_id = next(iter(state.capacity_by_opportunity))
    original = state.capacity_by_opportunity[opportunity_id]
    capacities = dict(state.capacity_by_opportunity)
    capacities[opportunity_id] = CapacityState(
        opportunity_id,
        original.standard_capacity,
        original.total_capacity,
        used_standard_capacity=1,
    )
    invalid = SchedulingState.create(
        state.routes,
        state.opportunities,
        state.route_start_dates,
        state.assignments,
        capacities,
        state.pending_events,
    )

    with pytest.raises(CapacityStateError, match="differs from assignments"):
        validate_state(invalid)


def test_horizon_overflow_returns_no_candidates(demo_scheduling_components) -> None:
    state = _small_state(
        demo_scheduling_components,
        patient_count=1,
        min_spacing_days=31,
    )

    assert state.status_for("PAT-011", 1) is EventStatus.ELIGIBLE
    assert get_candidate_slots(state, "PAT-011", 1) == ()
    assert state.assignments == {}
