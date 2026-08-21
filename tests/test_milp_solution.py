from dataclasses import replace

import pytest

from appointment_scheduling.optimization import (
    DeterministicMILPResult,
    ModelStatistics,
    OptimizationStatus,
    OptimizationValidationError,
    build_deterministic_problem,
    build_state_from_milp_incumbent,
    evaluate_milp_incumbent,
    optimization_result_to_research_result,
)
from appointment_scheduling.research import PolicyName
from appointment_scheduling.scheduling import CapacityType, validate_state


def _known_outcomes(state):
    opportunities = {item.event_type: item.opportunity_id for item in state.opportunities}
    return {
        ("PAT-901", 1): opportunities["EVENT-Z1"],
        ("PAT-901", 2): opportunities["EVENT-Z2"],
    }


def test_known_chain_incumbent_has_expected_eta_fi_and_objective(tiny_milp_state) -> None:
    problem = build_deterministic_problem(tiny_milp_state)
    evaluation = evaluate_milp_incumbent(problem, _known_outcomes(tiny_milp_state), ())

    assert evaluation.eta_by_event == {("PAT-901", 1): 0, ("PAT-901", 2): 3}
    assert evaluation.fi_by_event == {("PAT-901", 1): 0, ("PAT-901", 2): 1}
    assert evaluation.timing_penalty == 1
    assert evaluation.alternative_penalty == 0
    assert evaluation.objective_value == 1


def test_post_horizon_outcome_uses_M_and_zero_timing(tiny_milp_state) -> None:
    problem = build_deterministic_problem(tiny_milp_state)
    evaluation = evaluate_milp_incumbent(
        problem, {}, (("PAT-901", 1), ("PAT-901", 2))
    )

    assert evaluation.objective_value == 400
    assert set(evaluation.fi_by_event.values()) == {0}
    assert evaluation.shared_metrics.pending_events == 2


def test_successor_cannot_be_assigned_when_predecessor_is_post_horizon(
    tiny_milp_state,
) -> None:
    problem = build_deterministic_problem(tiny_milp_state)
    outcomes = _known_outcomes(tiny_milp_state)

    with pytest.raises(OptimizationValidationError, match="predecessor"):
        evaluate_milp_incumbent(
            problem,
            {("PAT-901", 2): outcomes[("PAT-901", 2)]},
            (("PAT-901", 1),),
        )


def test_every_event_requires_exactly_one_incumbent_outcome(tiny_milp_state) -> None:
    problem = build_deterministic_problem(tiny_milp_state)

    with pytest.raises(OptimizationValidationError, match="Every event"):
        build_state_from_milp_incumbent(problem, {}, (("PAT-901", 1),))


def test_assignment_and_penalty_cannot_overlap(tiny_milp_state) -> None:
    problem = build_deterministic_problem(tiny_milp_state)
    outcomes = _known_outcomes(tiny_milp_state)

    with pytest.raises(OptimizationValidationError, match="assigned and penalized"):
        build_state_from_milp_incumbent(
            problem, outcomes, (("PAT-901", 2),)
        )


def test_solution_translation_uses_shared_capacity_state(tiny_milp_state) -> None:
    problem = build_deterministic_problem(tiny_milp_state)
    state = build_state_from_milp_incumbent(
        problem, _known_outcomes(tiny_milp_state), ()
    )

    validate_state(state)
    assert state.summary.used_capacity == 2
    assert all(
        assignment.capacity_type is CapacityType.STANDARD
        for assignment in state.assignments.values()
    )


def test_solution_translation_does_not_mutate_initial_state(tiny_milp_state) -> None:
    problem = build_deterministic_problem(tiny_milp_state)
    translated = build_state_from_milp_incumbent(
        problem, _known_outcomes(tiny_milp_state), ()
    )

    assert translated is not tiny_milp_state
    assert not tiny_milp_state.assignments
    assert tiny_milp_state.summary.used_capacity == 0


def test_result_adapter_uses_deterministic_milp_policy(tiny_milp_state) -> None:
    problem = build_deterministic_problem(tiny_milp_state)
    evaluation = evaluate_milp_incumbent(problem, _known_outcomes(tiny_milp_state), ())
    stats = ModelStatistics(1, 2, 2, 1, 4, 2, 2, 5, 0, 2, 4, 9, 15)
    result = DeterministicMILPResult.create(
        status=OptimizationStatus.OPTIMAL,
        solver_name="fixture",
        solver_version=None,
        runtime_seconds=0,
        objective_value=evaluation.objective_value,
        best_bound=evaluation.objective_value,
        mip_gap=0,
        timing_penalty=evaluation.timing_penalty,
        alternative_penalty=evaluation.alternative_penalty,
        penalized_events=(),
        assignment_opportunity_by_event=_known_outcomes(tiny_milp_state),
        eta_by_event=evaluation.eta_by_event,
        fi_by_event=evaluation.fi_by_event,
        final_state=evaluation.final_state,
        shared_metrics=evaluation.shared_metrics,
        model_statistics=stats,
    )

    adapted = optimization_result_to_research_result(result)
    assert adapted.policy_name is PolicyName.DETERMINISTIC_MILP
    assert adapted.metrics == evaluation.shared_metrics
    assert len(adapted.trace) == 2
