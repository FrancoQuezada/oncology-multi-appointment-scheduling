from appointment_scheduling.optimization import (
    build_deterministic_problem,
    evaluate_milp_incumbent,
    formulate_deterministic_milp,
)
from appointment_scheduling.research import run_asap_policy


def test_canonical_seed42_formulation_dimensions(canonical_state) -> None:
    stats = formulate_deterministic_milp(
        build_deterministic_problem(canonical_state)
    ).statistics

    assert stats.patients == 4
    assert stats.events == 20
    assert stats.opportunities == 80
    assert stats.dependency_arcs == 19
    assert stats.planning_days == 28
    assert stats.compatible_assignment_variables == 80
    assert stats.alternative_variables == 20
    assert stats.continuous_timing_variables == 56
    assert stats.auxiliary_binary_variables == 6
    assert stats.dependency_constraints == 38
    assert stats.capacity_constraints == 93
    assert stats.total_variables == 162
    assert stats.total_constraints == 279


def test_existing_asap_solution_can_be_scored_under_milp_objective(
    canonical_state,
) -> None:
    asap = run_asap_policy(canonical_state)
    selected = {
        key: assignment.opportunity_id
        for key, assignment in asap.final_state.assignments.items()
    }
    penalized = tuple(asap.final_state.pending_events)
    evaluation = evaluate_milp_incumbent(
        build_deterministic_problem(canonical_state), selected, penalized
    )

    assert evaluation.timing_penalty == 29
    assert evaluation.alternative_penalty == 400
    assert evaluation.objective_value == 429
    assert evaluation.shared_metrics == asap.metrics


def test_milp_is_not_added_to_default_five_seed_policy_suite() -> None:
    from appointment_scheduling.research import DEFAULT_POLICIES

    assert all(policy.__name__ != "run_deterministic_milp_policy" for policy in DEFAULT_POLICIES)
