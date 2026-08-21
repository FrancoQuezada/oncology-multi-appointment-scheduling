"""Pure construction and result adapters for deterministic optimization."""

from __future__ import annotations

from datetime import timedelta
from math import isfinite
from types import MappingProxyType

from appointment_scheduling.research import (
    PolicyName,
    ResearchOutcome,
    ResearchSchedulingResult,
    ResearchTraceEntry,
    compute_policy_metrics,
)
from appointment_scheduling.scheduling import (
    CapacityState,
    CapacityType,
    EventAssignment,
    PendingEvent,
    PendingReason,
    SchedulingState,
    is_resource_compatible,
    validate_state,
)

from appointment_scheduling.optimization.models import (
    AssignmentOption,
    DependencyArc,
    DeterministicMILPResult,
    DeterministicSchedulingProblem,
    IncumbentEvaluation,
    OptimizationEvent,
)
from appointment_scheduling.optimization.validation import (
    OptimizationValidationError,
    validate_deterministic_problem,
)


def build_deterministic_problem(
    initial_state: SchedulingState,
    *,
    penalty_M: float = 200.0,
) -> DeterministicSchedulingProblem:
    """Build sparse finite-horizon MILP data without importing a solver.

    ``penalty_M=200`` preserves the historical experiment scale. It is exposed
    because it is a modeling parameter, not a universally calibrated value.
    """

    validate_state(initial_state)
    if not isfinite(penalty_M) or penalty_M <= 0:
        raise OptimizationValidationError("penalty_M must be finite and positive")

    horizon_start = initial_state.horizon_start
    horizon_end = initial_state.horizon_end
    planning_days = tuple(
        horizon_start + timedelta(days=offset)
        for offset in range((horizon_end - horizon_start).days + 1)
    )
    events = tuple(
        OptimizationEvent(
            key=(route.patient_id, event.event_number),
            patient_id=route.patient_id,
            event_number=event.event_number,
            event_id=event.event_id,
            dependencies=event.dependencies,
            min_spacing_days=event.min_spacing_days,
            preferred_max_spacing_days=event.preferred_max_spacing_days,
            route_start_date=initial_state.route_start_dates[route.patient_id],
            overbooking_allowed=event.overbooking_allowed,
        )
        for route in initial_state.routes.patient_routes
        for event in route.events
    )
    static_earliest_dates = {}
    for route in initial_state.routes.patient_routes:
        for event_number in route.graph.topological_order:
            event = route.event(event_number)
            if event.dependencies:
                reference = max(
                    static_earliest_dates[(route.patient_id, predecessor)]
                    for predecessor in event.dependencies
                )
            else:
                reference = initial_state.route_start_dates[route.patient_id]
            static_earliest_dates[(route.patient_id, event_number)] = (
                reference + timedelta(days=event.min_spacing_days)
            )
    options = []
    for event in events:
        source_event = initial_state.event(*event.key)
        for opportunity in initial_state.opportunities:
            if opportunity.date < static_earliest_dates[event.key]:
                continue
            if opportunity.total_available_capacity <= 0:
                continue
            if not is_resource_compatible(source_event, opportunity):
                continue
            if (
                not event.overbooking_allowed
                and opportunity.standard_available_capacity <= 0
            ):
                continue
            options.append(
                AssignmentOption(
                    event_key=event.key,
                    opportunity_id=opportunity.opportunity_id,
                    day_index=(opportunity.date - horizon_start).days,
                )
            )
    options.sort(
        key=lambda option: (
            option.event_key[0],
            option.event_key[1],
            option.day_index,
            option.opportunity_id,
        )
    )
    arcs = tuple(
        DependencyArc(
            predecessor=(event.patient_id, predecessor),
            successor=event.key,
            min_spacing_days=event.min_spacing_days,
        )
        for event in events
        for predecessor in event.dependencies
    )
    start_offsets = [
        abs((event.route_start_date - horizon_start).days) for event in events
    ]
    spacing = [
        max(event.min_spacing_days, event.preferred_max_spacing_days)
        for event in events
    ]
    # Covers any difference between two horizon days plus route-start offsets.
    big_m = float(
        2
        * (
            len(planning_days)
            + max(start_offsets, default=0)
            + max(spacing, default=0)
            + 1
        )
    )
    problem = DeterministicSchedulingProblem.create(
        initial_state=initial_state,
        events=events,
        opportunities=initial_state.opportunities,
        assignment_options=tuple(options),
        dependency_arcs=arcs,
        planning_days=planning_days,
        post_horizon_label="POST_HORIZON",
        penalty_M=penalty_M,
        big_m=big_m,
    )
    validate_deterministic_problem(problem)
    return problem


def build_state_from_milp_incumbent(
    problem: DeterministicSchedulingProblem,
    assignment_opportunity_by_event: dict[tuple[str, int], str],
    penalized_events: tuple[tuple[str, int], ...],
) -> SchedulingState:
    """Translate an incumbent into the shared immutable scheduling state."""

    penalized = set(penalized_events)
    if penalized.intersection(assignment_opportunity_by_event):
        raise OptimizationValidationError("An event cannot be assigned and penalized")
    all_keys = set(problem.events_by_key)
    if set(assignment_opportunity_by_event).union(penalized) != all_keys:
        raise OptimizationValidationError("Every event needs exactly one incumbent outcome")

    assignments = {}
    selected_by_opportunity: dict[str, list[tuple[str, int]]] = {}
    for key, opportunity_id in assignment_opportunity_by_event.items():
        if opportunity_id not in problem.opportunities_by_id:
            raise OptimizationValidationError("Incumbent uses an unknown opportunity")
        selected_by_opportunity.setdefault(opportunity_id, []).append(key)

    capacities = {}
    capacity_type_by_event = {}
    for opportunity in problem.opportunities:
        selected = sorted(
            selected_by_opportunity.get(opportunity.opportunity_id, ()),
            key=lambda key: (
                problem.events_by_key[key].overbooking_allowed,
                key[0],
                key[1],
            ),
        )
        if len(selected) > opportunity.total_available_capacity:
            raise OptimizationValidationError("Incumbent exceeds total capacity")
        non_overbook = sum(
            not problem.events_by_key[key].overbooking_allowed for key in selected
        )
        if non_overbook > opportunity.standard_available_capacity:
            raise OptimizationValidationError("Incumbent exceeds standard capacity")
        standard_count = min(len(selected), opportunity.standard_available_capacity)
        for position, key in enumerate(selected):
            capacity_type_by_event[key] = (
                CapacityType.STANDARD
                if position < standard_count
                else CapacityType.OVERBOOKING
            )
        capacities[opportunity.opportunity_id] = CapacityState(
            opportunity_id=opportunity.opportunity_id,
            standard_capacity=opportunity.standard_available_capacity,
            total_capacity=opportunity.total_available_capacity,
            used_standard_capacity=standard_count,
            used_overbooking_capacity=len(selected) - standard_count,
        )

    for key, opportunity_id in sorted(assignment_opportunity_by_event.items()):
        event = problem.initial_state.event(*key)
        opportunity = problem.opportunities_by_id[opportunity_id]
        assignments[key] = EventAssignment(
            patient_id=key[0],
            event_number=key[1],
            event_id=event.event_id,
            date=opportunity.date,
            opportunity_id=opportunity.opportunity_id,
            schedule_key=opportunity.schedule_key,
            agenda_id=opportunity.agenda_id,
            clinician_id=opportunity.clinician_id,
            service_id=opportunity.service_id,
            section_id=opportunity.section_id,
            modality=opportunity.modality,
            capacity_type=capacity_type_by_event[key],
        )

    pending = {}
    for key in sorted(penalized):
        event = problem.events_by_key[key]
        predecessor_pending = any(
            (event.patient_id, predecessor) in penalized
            for predecessor in event.dependencies
        )
        pending[key] = PendingEvent(
            patient_id=key[0],
            event_number=key[1],
            reason=(
                PendingReason.PREDECESSOR_PENDING
                if predecessor_pending
                else PendingReason.HORIZON_EXCEEDED
            ),
        )
    state = SchedulingState.create(
        routes=problem.initial_state.routes,
        opportunities=problem.initial_state.opportunities,
        route_start_dates=problem.initial_state.route_start_dates,
        assignments=assignments,
        capacity_by_opportunity=capacities,
        pending_events=pending,
    )
    try:
        validate_state(state)
    except ValueError as exc:
        raise OptimizationValidationError(f"Invalid incumbent: {exc}") from exc
    return state


def evaluate_milp_incumbent(
    problem: DeterministicSchedulingProblem,
    assignment_opportunity_by_event: dict[tuple[str, int], str],
    penalized_events: tuple[tuple[str, int], ...],
) -> IncumbentEvaluation:
    """Validate and score a complete incumbent with no solver dependency."""

    state = build_state_from_milp_incumbent(
        problem, assignment_opportunity_by_event, penalized_events
    )
    eta = {}
    fi = {}
    penalized = set(penalized_events)
    for event in problem.events:
        if event.key in penalized:
            eta[event.key] = 0.0
            fi[event.key] = 0.0
            continue
        assignment = state.assignments[event.key]
        if event.dependencies:
            reference = max(
                state.assignments[(event.patient_id, predecessor)].date
                for predecessor in event.dependencies
            )
        else:
            reference = event.route_start_date
        spacing = float((assignment.date - reference).days)
        eta[event.key] = spacing
        fi[event.key] = max(
            spacing - event.preferred_max_spacing_days,
            0.0,
        )
    timing_penalty = sum(fi.values())
    alternative_penalty = problem.penalty_M * len(penalized)
    return IncumbentEvaluation(
        final_state=state,
        eta_by_event=MappingProxyType(eta),
        fi_by_event=MappingProxyType(fi),
        timing_penalty=timing_penalty,
        alternative_penalty=alternative_penalty,
        objective_value=timing_penalty + alternative_penalty,
        shared_metrics=compute_policy_metrics(state, ()),
    )


def optimization_result_to_research_result(
    result: DeterministicMILPResult,
) -> ResearchSchedulingResult:
    """Adapt a solved MILP incumbent to the existing comparison contract."""

    if result.final_state is None or result.shared_metrics is None:
        raise OptimizationValidationError("A research result requires an incumbent")
    # A deterministic complete trace over every route, not a solver log.
    trace = tuple(
        ResearchTraceEntry(
            step=step,
            policy=PolicyName.DETERMINISTIC_MILP,
            patient_id=route.patient_id,
            event_number=event_number,
            candidate_count=0,
            chosen_opportunity_id=result.assignment_opportunity_by_event.get(
                (route.patient_id, event_number)
            ),
            chosen_date=(
                result.final_state.assignments[(route.patient_id, event_number)].date
                if (route.patient_id, event_number) in result.final_state.assignments
                else None
            ),
            capacity_type=(
                result.final_state.assignments[
                    (route.patient_id, event_number)
                ].capacity_type
                if (route.patient_id, event_number) in result.final_state.assignments
                else None
            ),
            within_preferred_window=None,
            outcome=(
                ResearchOutcome.ASSIGNED
                if (route.patient_id, event_number) in result.final_state.assignments
                else ResearchOutcome.PENDING
            ),
            pending_reason=(
                result.final_state.pending_events[
                    (route.patient_id, event_number)
                ].reason
                if (route.patient_id, event_number) in result.final_state.pending_events
                else None
            ),
        )
        for step, (route, event_number) in enumerate(
            (
                (route, event_number)
                for route in result.final_state.routes.patient_routes
                for event_number in route.graph.topological_order
            ),
            start=1,
        )
    )
    return ResearchSchedulingResult(
        policy_name=PolicyName.DETERMINISTIC_MILP,
        final_state=result.final_state,
        trace=trace,
        metrics=compute_policy_metrics(result.final_state, trace),
    )
