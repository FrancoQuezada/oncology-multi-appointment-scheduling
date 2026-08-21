from datetime import date

import pandas as pd

from appointment_scheduling.research import (
    CandidateRegion,
    PolicyName,
    ResearchOutcome,
    compute_policy_metrics,
    run_asap_policy,
    run_resource_aware_policy,
)
from appointment_scheduling.routes import (
    PathwayEventTemplate,
    PathwayTemplate,
    ResourceMode,
    preprocess_routes,
)
from appointment_scheduling.scheduling import (
    CapacityType,
    EventStatus,
    build_scheduling_state,
    get_candidate_slots,
    validate_state,
)


def _policy_state(
    demo_scheduling_components,
    opportunities,
    *,
    patients: int = 1,
    preferred_max_spacing_days: int = 5,
    overbooking_allowed: bool = True,
):
    _, _, demo_availability, _ = demo_scheduling_components
    route_rows = [
        {
            "patient_id": f"PAT-{patient_number:03d}",
            "pathway_id": "PATHWAY-Z",
            "event_number": 1,
            "event_id": "EVENT-Z1",
            "agenda_id": "AGENDA-DEMO-01",
            "event_type": "EVENT-Z1",
            "min_spacing_days": 0,
            "preferred_max_spacing_days": preferred_max_spacing_days,
            "dependencies": "[]",
            "clinician_id": "CLINICIAN-01",
            "service_id": "SERVICE-A",
            "section_id": "SECTION-A1",
            "modality": "IN_PERSON",
            "resource_mode": "COMPATIBLE_SET",
            "overbooking_allowed": overbooking_allowed,
        }
        for patient_number in range(11, 11 + patients)
    ]
    template = PathwayTemplate(
        "PATHWAY-Z",
        (
            PathwayEventTemplate(
                1,
                "EVENT-Z1",
                "EVENT-Z1",
                (),
                0,
                preferred_max_spacing_days,
                ResourceMode.COMPATIBLE_SET,
            ),
        ),
    )
    routes = preprocess_routes(pd.DataFrame(route_rows), (template,))

    source = demo_availability.iloc[[0]].copy()
    rows = []
    for index, (day, standard, total) in enumerate(opportunities, start=1):
        row = source.copy()
        row.loc[:, "block_id"] = f"SUPPLY-BLOCK-{900 + index:03d}"
        row.loc[:, "schedule_key"] = f"SCHEDULE-DEMO-{900 + index:03d}"
        row.loc[:, "date"] = pd.Timestamp(2035, 1, day)
        row.loc[:, "event_type"] = "EVENT-Z1"
        row.loc[:, "base_capacity"] = standard
        row.loc[:, "overbooking_capacity"] = total - standard
        row.loc[:, "blocked_capacity"] = 0
        row.loc[:, "standard_available_capacity"] = standard
        row.loc[:, "total_available_capacity"] = total
        row.loc[:, "used_capacity"] = 0
        row.loc[:, "remaining_capacity"] = total
        rows.append(row)
    availability = pd.concat(rows, ignore_index=True)
    starts = {
        patient_id: date(2035, 1, 1) for patient_id in routes.routes_by_patient
    }
    return build_scheduling_state(routes, availability, starts)


def test_resource_aware_runs_end_to_end(canonical_state) -> None:
    result = run_resource_aware_policy(canonical_state)

    assert result.policy_name is PolicyName.RESOURCE_AWARE
    assert result.metrics.total_events == 20
    assert len(result.trace) == 20
    validate_state(result.final_state)


def test_policy_differentiation_fixture_selects_capacity_preserving_date(
    demo_scheduling_components,
) -> None:
    state = _policy_state(
        demo_scheduling_components,
        opportunities=((1, 1, 1), (2, 4, 4)),
    )

    asap = run_asap_policy(state)
    resource_aware = run_resource_aware_policy(state)

    assert next(iter(asap.final_state.assignments.values())).date == date(2035, 1, 1)
    assert next(iter(resource_aware.final_state.assignments.values())).date == date(2035, 1, 2)


def test_resource_aware_uses_current_shared_candidates(
    demo_scheduling_components,
) -> None:
    state = _policy_state(
        demo_scheduling_components,
        opportunities=((1, 1, 1), (2, 4, 4)),
    )
    candidate_ids = {
        candidate.opportunity_id
        for candidate in get_candidate_slots(state, "PAT-011", 1)
    }

    result = run_resource_aware_policy(state)
    selected = next(iter(result.final_state.assignments.values()))

    assert selected.opportunity_id in candidate_ids
    assert state.assignments == {}
    assert state.summary.used_capacity == 0
    assert result.final_state.summary.used_capacity == 1


def test_resource_scores_are_recomputed_after_each_assignment(
    demo_scheduling_components,
) -> None:
    state = _policy_state(
        demo_scheduling_components,
        opportunities=((1, 3, 3), (2, 4, 4)),
        patients=2,
    )

    result = run_resource_aware_policy(state)
    selected_dates = tuple(item.selected_date for item in result.policy_diagnostics)

    assert selected_dates == (date(2035, 1, 2), date(2035, 1, 1))
    assert tuple(item.selected_resource_score for item in result.policy_diagnostics) == (4, 3)


def test_equal_resource_scores_choose_earliest_date(
    demo_scheduling_components,
) -> None:
    state = _policy_state(
        demo_scheduling_components,
        opportunities=((1, 4, 4), (2, 4, 4)),
    )

    result = run_resource_aware_policy(state)

    assert next(iter(result.final_state.assignments.values())).date == date(2035, 1, 1)


def test_equal_score_and_date_use_stable_opportunity_order(
    demo_scheduling_components,
) -> None:
    state = _policy_state(
        demo_scheduling_components,
        opportunities=((1, 4, 4), (1, 4, 4)),
    )

    result = run_resource_aware_policy(state)
    assignment = next(iter(result.final_state.assignments.values()))

    assert assignment.schedule_key == "SCHEDULE-DEMO-901"
    assert assignment.opportunity_id == "SUPPLY-BLOCK-901"


def test_standard_capacity_region_precedes_overbooking(
    demo_scheduling_components,
) -> None:
    state = _policy_state(
        demo_scheduling_components,
        opportunities=((1, 0, 4), (1, 1, 1)),
    )

    result = run_resource_aware_policy(state)
    assignment = next(iter(result.final_state.assignments.values()))

    assert assignment.capacity_type is CapacityType.STANDARD
    assert assignment.opportunity_id == "SUPPLY-BLOCK-902"


def test_overbooking_permission_is_still_shared_feasibility(
    demo_scheduling_components,
) -> None:
    state = _policy_state(
        demo_scheduling_components,
        opportunities=((1, 0, 4),),
        overbooking_allowed=False,
    )

    result = run_resource_aware_policy(state)

    assert result.metrics.assigned_events == 0
    assert result.metrics.pending_events == 1
    assert result.final_state.status_for("PAT-011", 1) is EventStatus.PENDING


def test_preferred_region_excludes_later_high_capacity_candidate(
    demo_scheduling_components,
) -> None:
    state = _policy_state(
        demo_scheduling_components,
        opportunities=((2, 1, 1), (8, 10, 10)),
        preferred_max_spacing_days=2,
    )

    result = run_resource_aware_policy(state)
    diagnostic = result.policy_diagnostics[0]

    assert diagnostic.selected_date == date(2035, 1, 2)
    assert diagnostic.candidate_region is CandidateRegion.PREFERRED_WINDOW
    assert diagnostic.preferred_window_candidate_count == 1


def test_late_fallback_uses_all_feasible_late_candidates(
    demo_scheduling_components,
) -> None:
    state = _policy_state(
        demo_scheduling_components,
        opportunities=((2, 1, 1), (3, 4, 4)),
        preferred_max_spacing_days=0,
    )

    result = run_resource_aware_policy(state)
    diagnostic = result.policy_diagnostics[0]

    assert diagnostic.candidate_region is CandidateRegion.LATE_FALLBACK
    assert diagnostic.preferred_window_candidate_count == 0
    assert diagnostic.selected_date == date(2035, 1, 3)
    assert result.metrics.late_assignments == 1


def test_resource_aware_handles_branches_and_joins(canonical_state) -> None:
    result = run_resource_aware_policy(canonical_state)
    steps = {(item.patient_id, item.event_number): item.step for item in result.trace}

    assert result.final_state.status_for("PAT-001", 2) is EventStatus.ASSIGNED
    assert result.final_state.status_for("PAT-001", 3) is EventStatus.ASSIGNED
    assert steps[("PAT-001", 5)] > steps[("PAT-001", 2)]
    assert steps[("PAT-001", 5)] > steps[("PAT-001", 3)]


def test_resource_aware_uses_common_pending_semantics(canonical_state) -> None:
    result = run_resource_aware_policy(canonical_state)
    pending = [entry for entry in result.trace if entry.outcome is ResearchOutcome.PENDING]

    assert pending
    assert all(entry.pending_reason is not None for entry in pending)
    assert result.final_state.summary.dependency_blocked_events == 0


def test_trace_and_diagnostics_identify_policy_reasoning(canonical_state) -> None:
    result = run_resource_aware_policy(canonical_state)

    assert all(entry.policy is PolicyName.RESOURCE_AWARE for entry in result.trace)
    assert result.policy_diagnostics
    assert all(
        item.selected_resource_score == item.best_resource_score
        for item in result.policy_diagnostics
    )


def test_resource_aware_uses_common_metric_definitions(canonical_state) -> None:
    result = run_resource_aware_policy(canonical_state)

    assert compute_policy_metrics(result.final_state, result.trace) == result.metrics


def test_resource_aware_is_forward_only_without_backtracking(canonical_state) -> None:
    result = run_resource_aware_policy(canonical_state)
    processed = [(entry.patient_id, entry.event_number) for entry in result.trace]

    assert len(processed) == len(set(processed))
    assert result.metrics.capacity_used == result.metrics.assigned_events
