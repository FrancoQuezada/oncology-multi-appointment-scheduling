from dataclasses import replace

import pytest

from appointment_scheduling.optimization import (
    ConstraintSense,
    VariableKind,
    build_deterministic_problem,
    formulate_deterministic_milp,
    validate_formulation,
    OptimizationValidationError,
)


def _formulation(state):
    return formulate_deterministic_milp(build_deterministic_problem(state))


def test_formulation_has_historical_variable_families(canonical_state) -> None:
    formulation = _formulation(canonical_state)
    families = {variable.family for variable in formulation.variables}

    assert {"x", "y", "eta", "fi"}.issubset(families)


def test_x_and_y_are_binary_and_timing_is_continuous(canonical_state) -> None:
    formulation = _formulation(canonical_state)

    assert all(
        item.kind is VariableKind.BINARY
        for item in formulation.variables
        if item.family in {"x", "y"}
    )
    assert all(
        item.kind is VariableKind.CONTINUOUS
        for item in formulation.variables
        if item.family in {"eta", "fi", "reference"}
    )


def test_every_event_has_exactly_one_internal_or_alternative_outcome(
    canonical_state,
) -> None:
    formulation = _formulation(canonical_state)
    outcomes = [item for item in formulation.constraints if item.family == "outcome"]

    assert len(outcomes) == 20
    assert all(item.sense is ConstraintSense.EQUAL for item in outcomes)
    assert all(item.right_hand_side == 1 for item in outcomes)
    assert all(sum(term.variable_key.startswith("y[") for term in item.terms) == 1 for item in outcomes)


def test_objective_is_sum_fi_plus_M_sum_y(canonical_state) -> None:
    formulation = _formulation(canonical_state)

    assert all(
        variable.objective_coefficient == 1
        for variable in formulation.variables
        if variable.family == "fi"
    )
    assert all(
        variable.objective_coefficient == 200
        for variable in formulation.variables
        if variable.family == "y"
    )
    assert all(
        variable.objective_coefficient == 0
        for variable in formulation.variables
        if variable.family not in {"fi", "y"}
    )


def test_root_arrival_constraints_are_explicit(canonical_state) -> None:
    formulation = _formulation(canonical_state)

    roots = [item for item in formulation.constraints if item.family == "root_arrival"]
    assert len(roots) == canonical_state.routes.diagnostics.root_events


def test_dependency_spacing_and_alternative_propagation_cover_all_arcs(
    canonical_state,
) -> None:
    formulation = _formulation(canonical_state)
    arcs = len(formulation.problem.dependency_arcs)

    assert sum(item.family == "dependency_spacing" for item in formulation.constraints) == arcs
    assert sum(item.family == "dependency_alternative" for item in formulation.constraints) == arcs


def test_join_uses_exact_latest_predecessor_selector(canonical_state) -> None:
    formulation = _formulation(canonical_state)
    join_selectors = [
        variable
        for variable in formulation.variables
        if variable.family == "latest_selector" and "PAT-001" in variable.key and ",5" in variable.key
    ]

    assert len(join_selectors) == 2
    assert any(
        item.family == "latest_predecessor"
        and item.name.startswith("latest_selector")
        and "PAT-001" in item.name
        and ",5" in item.name
        for item in formulation.constraints
    )


def test_preferred_max_is_soft_through_fi(canonical_state) -> None:
    formulation = _formulation(canonical_state)
    constraints = [item for item in formulation.constraints if item.family == "preferred_max"]

    assert len(constraints) == 20
    assert all(any(term.variable_key.startswith("fi[") for term in item.terms) for item in constraints)


def test_capacity_constraints_use_exact_opportunities(canonical_state) -> None:
    formulation = _formulation(canonical_state)
    capacity = [
        item
        for item in formulation.constraints
        if item.family in {"total_capacity", "standard_capacity"}
    ]

    assert capacity
    assert all(item.sense is ConstraintSense.LESS_EQUAL for item in capacity)
    assert all(all(term.variable_key.startswith("x[") for term in item.terms) for item in capacity)
    by_name = {item.name: item for item in capacity}
    for opportunity in canonical_state.opportunities:
        total_name = f"total_capacity[{opportunity.opportunity_id!r}]"
        if total_name in by_name:
            assert by_name[total_name].right_hand_side == opportunity.total_available_capacity
        standard_name = f"standard_capacity[{opportunity.opportunity_id!r}]"
        if standard_name in by_name:
            assert by_name[standard_name].right_hand_side == opportunity.standard_available_capacity


def test_formulation_statistics_reconcile(canonical_state) -> None:
    formulation = _formulation(canonical_state)
    stats = formulation.statistics

    assert stats.compatible_assignment_variables == 80
    assert stats.alternative_variables == 20
    assert stats.total_variables == len(formulation.variables)
    assert stats.total_constraints == len(formulation.constraints)
    assert stats.capacity_constraints == 93


def test_repeated_formulation_is_identical(canonical_state) -> None:
    assert _formulation(canonical_state) == _formulation(canonical_state)


def test_generated_formulation_validates(canonical_state) -> None:
    validate_formulation(_formulation(canonical_state))


def test_invalid_formulation_is_rejected_before_solver(canonical_state) -> None:
    formulation = _formulation(canonical_state)
    malformed = replace(formulation, variables=formulation.variables[1:])

    with pytest.raises(OptimizationValidationError, match="unknown variable"):
        validate_formulation(malformed)
