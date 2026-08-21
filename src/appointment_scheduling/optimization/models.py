"""Typed, solver-neutral models for the deterministic scheduling MILP."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from appointment_scheduling.research.models import PolicyMetrics
from appointment_scheduling.scheduling import (
    AvailabilityOpportunity,
    SchedulingState,
)
from appointment_scheduling.scheduling.models import EventKey


class VariableKind(str, Enum):
    """Supported mathematical variable domains."""

    BINARY = "BINARY"
    CONTINUOUS = "CONTINUOUS"


class ConstraintSense(str, Enum):
    """Supported linear-constraint relations."""

    EQUAL = "=="
    LESS_EQUAL = "<="
    GREATER_EQUAL = ">="


class OptimizationStatus(str, Enum):
    """Solver outcomes without conflating time limits and optimality."""

    OPTIMAL = "OPTIMAL"
    TIME_LIMIT_WITH_INCUMBENT = "TIME_LIMIT_WITH_INCUMBENT"
    TIME_LIMIT_WITHOUT_INCUMBENT = "TIME_LIMIT_WITHOUT_INCUMBENT"
    FEASIBLE_INCUMBENT = "FEASIBLE_INCUMBENT"
    INFEASIBLE = "INFEASIBLE"
    UNBOUNDED = "UNBOUNDED"
    INFEASIBLE_OR_UNBOUNDED = "INFEASIBLE_OR_UNBOUNDED"
    NO_SOLUTION = "NO_SOLUTION"


@dataclass(frozen=True, slots=True)
class OptimizationEvent:
    """Minimal immutable patient-event data required by the MILP."""

    key: EventKey
    patient_id: str
    event_number: int
    event_id: str
    dependencies: tuple[int, ...]
    min_spacing_days: int
    preferred_max_spacing_days: int
    route_start_date: date
    overbooking_allowed: bool


@dataclass(frozen=True, slots=True)
class AssignmentOption:
    """One sparse compatible internal assignment variable x[e,o]."""

    event_key: EventKey
    opportunity_id: str
    day_index: int


@dataclass(frozen=True, slots=True)
class DependencyArc:
    """One predecessor-to-successor timing arc."""

    predecessor: EventKey
    successor: EventKey
    min_spacing_days: int


@dataclass(frozen=True, slots=True)
class DeterministicSchedulingProblem:
    """Validated solver-independent data for one finite-horizon model."""

    initial_state: SchedulingState
    events: tuple[OptimizationEvent, ...]
    opportunities: tuple[AvailabilityOpportunity, ...]
    assignment_options: tuple[AssignmentOption, ...]
    dependency_arcs: tuple[DependencyArc, ...]
    planning_days: tuple[date, ...]
    post_horizon_label: str
    penalty_M: float
    big_m: float
    events_by_key: Mapping[EventKey, OptimizationEvent]
    options_by_event: Mapping[EventKey, tuple[AssignmentOption, ...]]
    opportunities_by_id: Mapping[str, AvailabilityOpportunity]

    @classmethod
    def create(
        cls,
        *,
        initial_state: SchedulingState,
        events: tuple[OptimizationEvent, ...],
        opportunities: tuple[AvailabilityOpportunity, ...],
        assignment_options: tuple[AssignmentOption, ...],
        dependency_arcs: tuple[DependencyArc, ...],
        planning_days: tuple[date, ...],
        post_horizon_label: str,
        penalty_M: float,
        big_m: float,
    ) -> "DeterministicSchedulingProblem":
        event_index = {event.key: event for event in events}
        opportunity_index = {
            opportunity.opportunity_id: opportunity
            for opportunity in opportunities
        }
        option_index = {
            event.key: tuple(
                option for option in assignment_options if option.event_key == event.key
            )
            for event in events
        }
        return cls(
            initial_state=initial_state,
            events=tuple(events),
            opportunities=tuple(opportunities),
            assignment_options=tuple(assignment_options),
            dependency_arcs=tuple(dependency_arcs),
            planning_days=tuple(planning_days),
            post_horizon_label=post_horizon_label,
            penalty_M=float(penalty_M),
            big_m=float(big_m),
            events_by_key=MappingProxyType(event_index),
            options_by_event=MappingProxyType(option_index),
            opportunities_by_id=MappingProxyType(opportunity_index),
        )


@dataclass(frozen=True, slots=True)
class VariableSpec:
    """A solver-neutral scalar decision variable."""

    key: str
    name: str
    family: str
    kind: VariableKind
    lower_bound: float
    upper_bound: float | None
    objective_coefficient: float


@dataclass(frozen=True, slots=True)
class LinearTerm:
    """One coefficient-variable pair in a linear constraint."""

    variable_key: str
    coefficient: float


@dataclass(frozen=True, slots=True)
class LinearConstraintSpec:
    """A named linear constraint independent of any solver API."""

    name: str
    family: str
    terms: tuple[LinearTerm, ...]
    sense: ConstraintSense
    right_hand_side: float


@dataclass(frozen=True, slots=True)
class ModelStatistics:
    """Transparent dimensions of a generated deterministic MILP."""

    patients: int
    events: int
    opportunities: int
    dependency_arcs: int
    planning_days: int
    compatible_assignment_variables: int
    alternative_variables: int
    continuous_timing_variables: int
    auxiliary_binary_variables: int
    dependency_constraints: int
    capacity_constraints: int
    total_variables: int
    total_constraints: int


@dataclass(frozen=True, slots=True)
class DeterministicMILPFormulation:
    """Complete linear formulation ready for a solver adapter."""

    problem: DeterministicSchedulingProblem
    variables: tuple[VariableSpec, ...]
    constraints: tuple[LinearConstraintSpec, ...]
    statistics: ModelStatistics
    objective_sense: str = "minimize"


@dataclass(frozen=True, slots=True)
class GurobiConfig:
    """Lightweight public solver defaults; historical settings are opt-in."""

    time_limit_seconds: float = 60.0
    seed: int = 123
    threads: int = 1
    mip_gap: float = 0.0
    output_flag: int = 0
    cuts: int | None = None


@dataclass(frozen=True, slots=True)
class GurobiEnvironmentInfo:
    """Package and license availability without exposing license details."""

    installed: bool
    version: str | None
    license_available: bool
    message: str


@dataclass(frozen=True, slots=True)
class DeterministicMILPResult:
    """Status, incumbent, objective accounting, and shared public metrics."""

    status: OptimizationStatus
    solver_name: str
    solver_version: str | None
    runtime_seconds: float
    objective_value: float | None
    best_bound: float | None
    mip_gap: float | None
    timing_penalty: float | None
    alternative_penalty: float | None
    penalized_events: tuple[EventKey, ...]
    assignment_opportunity_by_event: Mapping[EventKey, str]
    eta_by_event: Mapping[EventKey, float]
    fi_by_event: Mapping[EventKey, float]
    final_state: SchedulingState | None
    shared_metrics: PolicyMetrics | None
    model_statistics: ModelStatistics

    @property
    def tardiness_component(self) -> float | None:
        """Authoritative ``sum(fi)`` objective component."""

        return self.timing_penalty

    @property
    def penalized_assignment_component(self) -> float | None:
        """Authoritative ``penalty_M * sum(y)`` objective component."""

        return self.alternative_penalty

    @classmethod
    def create(
        cls,
        *,
        status: OptimizationStatus,
        solver_name: str,
        solver_version: str | None,
        runtime_seconds: float,
        objective_value: float | None,
        best_bound: float | None,
        mip_gap: float | None,
        timing_penalty: float | None,
        alternative_penalty: float | None,
        penalized_events: tuple[EventKey, ...],
        assignment_opportunity_by_event: Mapping[EventKey, str],
        eta_by_event: Mapping[EventKey, float],
        fi_by_event: Mapping[EventKey, float],
        final_state: SchedulingState | None,
        shared_metrics: PolicyMetrics | None,
        model_statistics: ModelStatistics,
    ) -> "DeterministicMILPResult":
        return cls(
            status=status,
            solver_name=solver_name,
            solver_version=solver_version,
            runtime_seconds=float(runtime_seconds),
            objective_value=objective_value,
            best_bound=best_bound,
            mip_gap=mip_gap,
            timing_penalty=timing_penalty,
            alternative_penalty=alternative_penalty,
            penalized_events=tuple(penalized_events),
            assignment_opportunity_by_event=MappingProxyType(
                dict(assignment_opportunity_by_event)
            ),
            eta_by_event=MappingProxyType(dict(eta_by_event)),
            fi_by_event=MappingProxyType(dict(fi_by_event)),
            final_state=final_state,
            shared_metrics=shared_metrics,
            model_statistics=model_statistics,
        )


@dataclass(frozen=True, slots=True)
class IncumbentEvaluation:
    """Solver-independent interpretation of one complete outcome selection."""

    final_state: SchedulingState
    eta_by_event: Mapping[EventKey, float]
    fi_by_event: Mapping[EventKey, float]
    timing_penalty: float
    alternative_penalty: float
    objective_value: float
    shared_metrics: PolicyMetrics
