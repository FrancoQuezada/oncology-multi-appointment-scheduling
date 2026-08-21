from dataclasses import replace
from datetime import timedelta

import pytest

from appointment_scheduling.optimization import (
    OptimizationValidationError,
    build_deterministic_problem,
    validate_deterministic_problem,
)
from appointment_scheduling.research import run_asap_policy


def test_canonical_problem_uses_every_patient_and_event(canonical_state) -> None:
    problem = build_deterministic_problem(canonical_state)

    assert len({event.patient_id for event in problem.events}) == 4
    assert len(problem.events) == 20
    assert len(problem.dependency_arcs) == 19


def test_planning_days_and_post_horizon_are_explicit(canonical_state) -> None:
    problem = build_deterministic_problem(canonical_state)

    assert problem.planning_days[0] == canonical_state.horizon_start
    assert problem.planning_days[-1] == canonical_state.horizon_end
    assert problem.post_horizon_label == "POST_HORIZON"


def test_assignment_variables_are_sparse_and_compatible(canonical_state) -> None:
    problem = build_deterministic_problem(canonical_state)

    dense_size = len(problem.events) * len(problem.opportunities)
    assert 0 < len(problem.assignment_options) < dense_size
    assert all(
        option.event_key in problem.events_by_key
        and option.opportunity_id in problem.opportunities_by_id
        for option in problem.assignment_options
    )


def test_no_assignment_option_precedes_static_route_earliest_date(
    canonical_state,
) -> None:
    problem = build_deterministic_problem(canonical_state)
    option_dates = {
        (option.event_key, option.opportunity_id): problem.opportunities_by_id[
            option.opportunity_id
        ].date
        for option in problem.assignment_options
    }

    for route in canonical_state.routes.patient_routes:
        earliest = {}
        for event_number in route.graph.topological_order:
            event = route.event(event_number)
            reference = (
                max(earliest[pred] for pred in event.dependencies)
                if event.dependencies
                else canonical_state.route_start_dates[route.patient_id]
            )
            earliest[event_number] = reference + timedelta(days=event.min_spacing_days)
            assert all(
                date >= earliest[event_number]
                for (key, _), date in option_dates.items()
                if key == (route.patient_id, event_number)
            )


def test_dependencies_include_every_join_arc(canonical_state) -> None:
    problem = build_deterministic_problem(canonical_state)

    incoming = {
        arc.predecessor[1]
        for arc in problem.dependency_arcs
        if arc.successor == ("PAT-001", 5)
    }
    assert incoming == {2, 3}


def test_branch_successors_remain_distinct_arcs(canonical_state) -> None:
    problem = build_deterministic_problem(canonical_state)
    successors = {
        arc.successor[1]
        for arc in problem.dependency_arcs
        if arc.predecessor == ("PAT-001", 1)
    }

    assert successors == {2, 3}


def test_route_start_and_timing_parameters_are_preserved(canonical_state) -> None:
    problem = build_deterministic_problem(canonical_state)

    for event in problem.events:
        source = canonical_state.event(*event.key)
        assert event.route_start_date == canonical_state.route_start_dates[event.patient_id]
        assert event.min_spacing_days == source.min_spacing_days
        assert event.preferred_max_spacing_days == source.preferred_max_spacing_days


def test_default_penalty_preserves_historical_scale(canonical_state) -> None:
    assert build_deterministic_problem(canonical_state).penalty_M == 200.0


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_invalid_penalty_fails_before_solver_creation(canonical_state, value) -> None:
    with pytest.raises(OptimizationValidationError, match="penalty_M"):
        build_deterministic_problem(canonical_state, penalty_M=value)


def test_non_clean_initial_state_fails_before_solver_creation(canonical_state) -> None:
    completed = run_asap_policy(canonical_state).final_state

    with pytest.raises(OptimizationValidationError, match="clean initial state"):
        build_deterministic_problem(completed)


def test_problem_is_deterministic(canonical_state) -> None:
    assert build_deterministic_problem(canonical_state) == build_deterministic_problem(
        canonical_state
    )


def test_problem_build_does_not_mutate_input(canonical_state) -> None:
    before = canonical_state
    build_deterministic_problem(canonical_state)

    assert canonical_state == before
    assert not canonical_state.assignments
    assert not canonical_state.pending_events


def test_problem_validation_rejects_inconsistent_big_m(canonical_state) -> None:
    problem = build_deterministic_problem(canonical_state)

    with pytest.raises(OptimizationValidationError, match="big_m"):
        validate_deterministic_problem(replace(problem, big_m=0.0))
