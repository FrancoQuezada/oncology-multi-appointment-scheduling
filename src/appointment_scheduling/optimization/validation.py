"""Fail-fast validation for deterministic optimization inputs and models."""

from __future__ import annotations

from math import isfinite
from datetime import timedelta

from appointment_scheduling.scheduling import is_resource_compatible, validate_state

from appointment_scheduling.optimization.models import (
    DeterministicMILPFormulation,
    DeterministicSchedulingProblem,
)


class OptimizationValidationError(ValueError):
    """Raised before solver creation when optimization data are inconsistent."""


def validate_deterministic_problem(problem: DeterministicSchedulingProblem) -> None:
    """Validate referential, capacity, timing, and compatibility invariants."""

    validate_state(problem.initial_state)
    if problem.initial_state.assignments or problem.initial_state.pending_events:
        raise OptimizationValidationError("The MILP requires a clean initial state")
    if any(
        capacity.used_total_capacity
        for capacity in problem.initial_state.capacity_by_opportunity.values()
    ):
        raise OptimizationValidationError("Initial capacity usage must be zero")
    if not isfinite(problem.penalty_M) or problem.penalty_M <= 0:
        raise OptimizationValidationError("penalty_M must be finite and positive")
    if not isfinite(problem.big_m) or problem.big_m <= 0:
        raise OptimizationValidationError("big_m must be finite and positive")
    if not problem.planning_days:
        raise OptimizationValidationError("At least one planning day is required")
    if tuple(sorted(set(problem.planning_days))) != problem.planning_days:
        raise OptimizationValidationError("Planning days must be unique and sorted")
    if len(problem.events_by_key) != len(problem.events):
        raise OptimizationValidationError("Optimization event keys must be unique")
    if len(problem.opportunities_by_id) != len(problem.opportunities):
        raise OptimizationValidationError("Opportunity identifiers must be unique")
    if problem.post_horizon_label != "POST_HORIZON":
        raise OptimizationValidationError("The penalized fallback must be POST_HORIZON")

    static_earliest = {}
    for route in problem.initial_state.routes.patient_routes:
        for event_number in route.graph.topological_order:
            source = route.event(event_number)
            key = (route.patient_id, event_number)
            event = problem.events_by_key.get(key)
            if event is None:
                raise OptimizationValidationError("A route event is missing from the problem")
            if event.dependencies != source.dependencies:
                raise OptimizationValidationError("Optimization dependencies differ from the route")
            if event.min_spacing_days != source.min_spacing_days:
                raise OptimizationValidationError("Optimization spacing differs from the route")
            reference = (
                max(static_earliest[(route.patient_id, predecessor)] for predecessor in source.dependencies)
                if source.dependencies
                else problem.initial_state.route_start_dates[route.patient_id]
            )
            static_earliest[key] = reference + timedelta(days=source.min_spacing_days)
    if set(static_earliest) != set(problem.events_by_key):
        raise OptimizationValidationError("Problem contains events absent from public routes")

    option_pairs = set()
    for option in problem.assignment_options:
        pair = (option.event_key, option.opportunity_id)
        if pair in option_pairs:
            raise OptimizationValidationError("Assignment options must be unique")
        option_pairs.add(pair)
        event = problem.events_by_key.get(option.event_key)
        opportunity = problem.opportunities_by_id.get(option.opportunity_id)
        if event is None or opportunity is None:
            raise OptimizationValidationError("Assignment option has an unknown reference")
        source_event = problem.initial_state.event(*event.key)
        if not is_resource_compatible(source_event, opportunity):
            raise OptimizationValidationError("Assignment option is resource-incompatible")
        if opportunity.date not in problem.planning_days:
            raise OptimizationValidationError("Assignment option is outside the horizon")
        expected_index = (opportunity.date - problem.planning_days[0]).days
        if option.day_index != expected_index:
            raise OptimizationValidationError("Assignment option day index is inconsistent")
        if opportunity.total_available_capacity <= 0:
            raise OptimizationValidationError("Assignment option has no total capacity")
        if (
            not event.overbooking_allowed
            and opportunity.standard_available_capacity <= 0
        ):
            raise OptimizationValidationError(
                "Non-overbooking event has no standard capacity"
            )
        if opportunity.date < static_earliest[option.event_key]:
            raise OptimizationValidationError(
                "Assignment option precedes the static route timing lower bound"
            )

    indexed_pairs = {
        (option.event_key, option.opportunity_id)
        for options in problem.options_by_event.values()
        for option in options
    }
    if indexed_pairs != option_pairs:
        raise OptimizationValidationError("Assignment-option index is inconsistent")

    arc_pairs = set()
    for arc in problem.dependency_arcs:
        pair = (arc.predecessor, arc.successor)
        if pair in arc_pairs:
            raise OptimizationValidationError("Dependency arcs must be unique")
        arc_pairs.add(pair)
        if arc.predecessor not in problem.events_by_key:
            raise OptimizationValidationError("Dependency predecessor is unknown")
        successor = problem.events_by_key.get(arc.successor)
        if successor is None:
            raise OptimizationValidationError("Dependency successor is unknown")
        if arc.predecessor[0] != arc.successor[0]:
            raise OptimizationValidationError("Dependencies cannot cross patients")
        if arc.predecessor[1] not in successor.dependencies:
            raise OptimizationValidationError("Dependency arc is not declared by successor")
        if arc.min_spacing_days != successor.min_spacing_days:
            raise OptimizationValidationError("Dependency spacing is inconsistent")


def validate_formulation(formulation: DeterministicMILPFormulation) -> None:
    """Validate generated linear references and key semantic counts."""

    validate_deterministic_problem(formulation.problem)
    variable_keys = [variable.key for variable in formulation.variables]
    if len(set(variable_keys)) != len(variable_keys):
        raise OptimizationValidationError("Formulation variable keys must be unique")
    known = set(variable_keys)
    constraint_names = set()
    for constraint in formulation.constraints:
        if constraint.name in constraint_names:
            raise OptimizationValidationError("Constraint names must be unique")
        constraint_names.add(constraint.name)
        if not constraint.terms:
            raise OptimizationValidationError("Constraints cannot be empty")
        if any(term.variable_key not in known for term in constraint.terms):
            raise OptimizationValidationError("Constraint references an unknown variable")

    event_count = len(formulation.problem.events)
    y_variables = [item for item in formulation.variables if item.family == "y"]
    eta_variables = [item for item in formulation.variables if item.family == "eta"]
    fi_variables = [item for item in formulation.variables if item.family == "fi"]
    if not (len(y_variables) == len(eta_variables) == len(fi_variables) == event_count):
        raise OptimizationValidationError("Every event requires y, eta, and fi variables")
    if any(item.objective_coefficient != formulation.problem.penalty_M for item in y_variables):
        raise OptimizationValidationError("Each y variable must use penalty_M")
    if any(item.objective_coefficient != 1.0 for item in fi_variables):
        raise OptimizationValidationError("Each fi variable must have unit cost")

    outcomes = [item for item in formulation.constraints if item.family == "outcome"]
    if len(outcomes) != event_count:
        raise OptimizationValidationError("Every event requires one outcome constraint")
