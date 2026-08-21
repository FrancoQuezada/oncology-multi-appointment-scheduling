"""Solver-independent linear formulation of the deterministic MILP."""

from __future__ import annotations

from collections import defaultdict

from appointment_scheduling.optimization.models import (
    ConstraintSense,
    DeterministicMILPFormulation,
    DeterministicSchedulingProblem,
    LinearConstraintSpec,
    LinearTerm,
    ModelStatistics,
    VariableKind,
    VariableSpec,
)
from appointment_scheduling.optimization.validation import (
    validate_deterministic_problem,
    validate_formulation,
)


def _event_token(key: tuple[str, int]) -> str:
    return f"{key[0]!r},{key[1]}"


def x_key(key: tuple[str, int], opportunity_id: str) -> str:
    return f"x[{_event_token(key)},{opportunity_id!r}]"


def y_key(key: tuple[str, int]) -> str:
    return f"y[{_event_token(key)}]"


def eta_key(key: tuple[str, int]) -> str:
    return f"eta[{_event_token(key)}]"


def fi_key(key: tuple[str, int]) -> str:
    return f"fi[{_event_token(key)}]"


def reference_key(key: tuple[str, int]) -> str:
    return f"reference[{_event_token(key)}]"


def selector_key(key: tuple[str, int], predecessor_number: int) -> str:
    return f"latest[{_event_token(key)},{predecessor_number}]"


def _assignment_time_terms(problem, event_key, coefficient=1.0):
    return tuple(
        LinearTerm(x_key(event_key, option.opportunity_id), coefficient * option.day_index)
        for option in problem.options_by_event[event_key]
        if option.day_index != 0
    )


def formulate_deterministic_milp(
    problem: DeterministicSchedulingProblem,
) -> DeterministicMILPFormulation:
    """Create variables and linear constraints without importing Gurobi."""

    validate_deterministic_problem(problem)
    variables = []
    constraints = []

    for option in problem.assignment_options:
        key = x_key(option.event_key, option.opportunity_id)
        variables.append(
            VariableSpec(key, key, "x", VariableKind.BINARY, 0.0, 1.0, 0.0)
        )
    for event in problem.events:
        token = _event_token(event.key)
        variables.extend(
            (
                VariableSpec(
                    y_key(event.key),
                    y_key(event.key),
                    "y",
                    VariableKind.BINARY,
                    0.0,
                    1.0,
                    problem.penalty_M,
                ),
                VariableSpec(
                    eta_key(event.key),
                    eta_key(event.key),
                    "eta",
                    VariableKind.CONTINUOUS,
                    0.0,
                    problem.big_m,
                    0.0,
                ),
                VariableSpec(
                    fi_key(event.key),
                    fi_key(event.key),
                    "fi",
                    VariableKind.CONTINUOUS,
                    0.0,
                    problem.big_m,
                    1.0,
                ),
            )
        )
        outcome_terms = tuple(
            LinearTerm(x_key(event.key, option.opportunity_id), 1.0)
            for option in problem.options_by_event[event.key]
        ) + (LinearTerm(y_key(event.key), 1.0),)
        constraints.append(
            LinearConstraintSpec(
                f"outcome[{token}]",
                "outcome",
                outcome_terms,
                ConstraintSense.EQUAL,
                1.0,
            )
        )

        if not event.dependencies:
            start_index = (event.route_start_date - problem.planning_days[0]).days
            terms = (LinearTerm(eta_key(event.key), 1.0),) + tuple(
                LinearTerm(
                    x_key(event.key, option.opportunity_id),
                    -(option.day_index - start_index),
                )
                for option in problem.options_by_event[event.key]
                if option.day_index != start_index
            )
            constraints.append(
                LinearConstraintSpec(
                    f"root_eta[{token}]",
                    "root_timing",
                    terms,
                    ConstraintSense.EQUAL,
                    0.0,
                )
            )
            constraints.append(
                LinearConstraintSpec(
                    f"root_arrival[{token}]",
                    "root_arrival",
                    (
                        LinearTerm(eta_key(event.key), 1.0),
                        LinearTerm(y_key(event.key), event.min_spacing_days),
                    ),
                    ConstraintSense.GREATER_EQUAL,
                    float(event.min_spacing_days),
                )
            )
        else:
            variables.append(
                VariableSpec(
                    reference_key(event.key),
                    reference_key(event.key),
                    "reference",
                    VariableKind.CONTINUOUS,
                    0.0,
                    problem.big_m,
                    0.0,
                )
            )
            predecessor_keys = tuple(
                (event.patient_id, predecessor)
                for predecessor in event.dependencies
            )
            if len(predecessor_keys) == 1:
                predecessor = predecessor_keys[0]
                constraints.append(
                    LinearConstraintSpec(
                        f"reference_equal[{token}]",
                        "latest_predecessor",
                        (LinearTerm(reference_key(event.key), 1.0),)
                        + _assignment_time_terms(problem, predecessor, -1.0),
                        ConstraintSense.EQUAL,
                        0.0,
                    )
                )
            else:
                selectors = []
                for predecessor in predecessor_keys:
                    selector = selector_key(event.key, predecessor[1])
                    selectors.append(selector)
                    variables.append(
                        VariableSpec(
                            selector,
                            selector,
                            "latest_selector",
                            VariableKind.BINARY,
                            0.0,
                            1.0,
                            0.0,
                        )
                    )
                    constraints.append(
                        LinearConstraintSpec(
                            f"reference_lower[{token},{predecessor[1]}]",
                            "latest_predecessor",
                            (LinearTerm(reference_key(event.key), 1.0),)
                            + _assignment_time_terms(problem, predecessor, -1.0),
                            ConstraintSense.GREATER_EQUAL,
                            0.0,
                        )
                    )
                    constraints.append(
                        LinearConstraintSpec(
                            f"reference_upper[{token},{predecessor[1]}]",
                            "latest_predecessor",
                            (LinearTerm(reference_key(event.key), 1.0),)
                            + _assignment_time_terms(problem, predecessor, -1.0)
                            + (LinearTerm(selector, problem.big_m),),
                            ConstraintSense.LESS_EQUAL,
                            problem.big_m,
                        )
                    )
                constraints.append(
                    LinearConstraintSpec(
                        f"latest_selector[{token}]",
                        "latest_predecessor",
                        tuple(LinearTerm(key, 1.0) for key in selectors),
                        ConstraintSense.EQUAL,
                        1.0,
                    )
                )

            eta_expression = (
                (LinearTerm(eta_key(event.key), 1.0),)
                + _assignment_time_terms(problem, event.key, -1.0)
                + (LinearTerm(reference_key(event.key), 1.0),)
            )
            constraints.extend(
                (
                    LinearConstraintSpec(
                        f"eta_lower[{token}]",
                        "dependent_timing",
                        eta_expression
                        + (LinearTerm(y_key(event.key), problem.big_m),),
                        ConstraintSense.GREATER_EQUAL,
                        0.0,
                    ),
                    LinearConstraintSpec(
                        f"eta_upper[{token}]",
                        "dependent_timing",
                        eta_expression
                        + (LinearTerm(y_key(event.key), -problem.big_m),),
                        ConstraintSense.LESS_EQUAL,
                        0.0,
                    ),
                )
            )

        constraints.extend(
            (
                LinearConstraintSpec(
                    f"eta_zero_if_alternative[{token}]",
                    "timing_activation",
                    (
                        LinearTerm(eta_key(event.key), 1.0),
                        LinearTerm(y_key(event.key), problem.big_m),
                    ),
                    ConstraintSense.LESS_EQUAL,
                    problem.big_m,
                ),
                LinearConstraintSpec(
                    f"preferred_max[{token}]",
                    "preferred_max",
                    (
                        LinearTerm(fi_key(event.key), 1.0),
                        LinearTerm(eta_key(event.key), -1.0),
                    ),
                    ConstraintSense.GREATER_EQUAL,
                    -float(event.preferred_max_spacing_days),
                ),
                LinearConstraintSpec(
                    f"fi_zero_if_alternative[{token}]",
                    "timing_activation",
                    (
                        LinearTerm(fi_key(event.key), 1.0),
                        LinearTerm(y_key(event.key), problem.big_m),
                    ),
                    ConstraintSense.LESS_EQUAL,
                    problem.big_m,
                ),
            )
        )

    for arc in problem.dependency_arcs:
        predecessor_token = _event_token(arc.predecessor)
        successor_token = _event_token(arc.successor)
        constraints.extend(
            (
                LinearConstraintSpec(
                    f"dependency_spacing[{predecessor_token}->{successor_token}]",
                    "dependency_spacing",
                    _assignment_time_terms(problem, arc.successor, 1.0)
                    + _assignment_time_terms(problem, arc.predecessor, -1.0)
                    + (LinearTerm(y_key(arc.successor), problem.big_m),),
                    ConstraintSense.GREATER_EQUAL,
                    float(arc.min_spacing_days),
                ),
                LinearConstraintSpec(
                    f"alternative_propagation[{predecessor_token}->{successor_token}]",
                    "dependency_alternative",
                    (
                        LinearTerm(y_key(arc.successor), 1.0),
                        LinearTerm(y_key(arc.predecessor), -1.0),
                    ),
                    ConstraintSense.GREATER_EQUAL,
                    0.0,
                ),
            )
        )

    options_at_opportunity = defaultdict(list)
    for option in problem.assignment_options:
        options_at_opportunity[option.opportunity_id].append(option)
    capacity_constraints = 0
    for opportunity in problem.opportunities:
        options = options_at_opportunity[opportunity.opportunity_id]
        if not options:
            continue
        constraints.append(
            LinearConstraintSpec(
                f"total_capacity[{opportunity.opportunity_id!r}]",
                "total_capacity",
                tuple(
                    LinearTerm(x_key(option.event_key, option.opportunity_id), 1.0)
                    for option in options
                ),
                ConstraintSense.LESS_EQUAL,
                float(opportunity.total_available_capacity),
            )
        )
        capacity_constraints += 1
        standard_only = tuple(
            option
            for option in options
            if not problem.events_by_key[option.event_key].overbooking_allowed
        )
        if standard_only:
            constraints.append(
                LinearConstraintSpec(
                    f"standard_capacity[{opportunity.opportunity_id!r}]",
                    "standard_capacity",
                    tuple(
                        LinearTerm(
                            x_key(option.event_key, option.opportunity_id), 1.0
                        )
                        for option in standard_only
                    ),
                    ConstraintSense.LESS_EQUAL,
                    float(opportunity.standard_available_capacity),
                )
            )
            capacity_constraints += 1

    continuous_timing = sum(
        item.kind is VariableKind.CONTINUOUS for item in variables
    )
    auxiliary_binary = sum(
        item.family == "latest_selector" for item in variables
    )
    dependency_constraints = sum(
        item.family in {"dependency_spacing", "dependency_alternative"}
        for item in constraints
    )
    statistics = ModelStatistics(
        patients=len({event.patient_id for event in problem.events}),
        events=len(problem.events),
        opportunities=len(problem.opportunities),
        dependency_arcs=len(problem.dependency_arcs),
        planning_days=len(problem.planning_days),
        compatible_assignment_variables=len(problem.assignment_options),
        alternative_variables=len(problem.events),
        continuous_timing_variables=continuous_timing,
        auxiliary_binary_variables=auxiliary_binary,
        dependency_constraints=dependency_constraints,
        capacity_constraints=capacity_constraints,
        total_variables=len(variables),
        total_constraints=len(constraints),
    )
    formulation = DeterministicMILPFormulation(
        problem=problem,
        variables=tuple(variables),
        constraints=tuple(constraints),
        statistics=statistics,
    )
    validate_formulation(formulation)
    return formulation
