"""Typed result and experiment models for public scheduling research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from appointment_scheduling.scheduling import (
    CapacityType,
    PendingReason,
    SchedulingState,
)


class PolicyName(str, Enum):
    """Stable public identifiers for comparable scheduling methods."""

    APPLIED_SEQUENTIAL = "APPLIED_SEQUENTIAL"
    ASAP = "ASAP"
    RESOURCE_AWARE = "RESOURCE_AWARE"
    DETERMINISTIC_MILP = "DETERMINISTIC_MILP"


class ResearchOutcome(str, Enum):
    """Policy outcome recorded for one processed event."""

    ASSIGNED = "ASSIGNED"
    PENDING = "PENDING"


class CandidateRegion(str, Enum):
    """Timing region used by a resource-aware decision."""

    PREFERRED_WINDOW = "PREFERRED_WINDOW"
    LATE_FALLBACK = "LATE_FALLBACK"


@dataclass(frozen=True, slots=True)
class ResourceAwareDecisionDiagnostics:
    """Compact explanation of one resource-aware candidate selection."""

    patient_id: str
    event_number: int
    candidate_count: int
    preferred_window_candidate_count: int
    candidate_region: CandidateRegion
    selected_resource_score: int
    best_resource_score: int
    selected_date: date
    selected_opportunity_id: str


@dataclass(frozen=True, slots=True)
class ResearchTraceEntry:
    """Policy-labelled, public-safe record of one research decision."""

    step: int
    policy: PolicyName
    patient_id: str
    event_number: int
    candidate_count: int
    chosen_opportunity_id: str | None
    chosen_date: date | None
    capacity_type: CapacityType | None
    within_preferred_window: bool | None
    outcome: ResearchOutcome
    pending_reason: PendingReason | None


@dataclass(frozen=True, slots=True)
class PolicyMetrics:
    """Common assignment, route, timing, and capacity measurements."""

    total_events: int
    assigned_events: int
    pending_events: int
    assignment_rate: float
    fully_completed_routes: int
    partially_completed_routes: int
    unresolved_routes: int
    route_completion_rate: float
    late_assignments: int
    late_assignment_rate: float
    total_tardiness_days: int
    mean_tardiness_days: float
    max_tardiness_days: int
    standard_assignments: int
    overbooking_assignments: int
    overbooking_rate: float
    capacity_used: int
    capacity_remaining: int


@dataclass(frozen=True, slots=True)
class ResearchSchedulingResult:
    """One policy's final state, deterministic trace, and common metrics."""

    policy_name: PolicyName
    final_state: SchedulingState
    trace: tuple[ResearchTraceEntry, ...]
    metrics: PolicyMetrics
    policy_diagnostics: tuple[ResourceAwareDecisionDiagnostics, ...] = ()


@dataclass(frozen=True, slots=True)
class ExperimentCaseResult:
    """Comparable policy results for one synthetic instance."""

    instance_id: str
    policy_results: tuple[ResearchSchedulingResult, ...]

    @property
    def results_by_policy(self) -> Mapping[PolicyName, ResearchSchedulingResult]:
        return MappingProxyType(
            {result.policy_name: result for result in self.policy_results}
        )

    def result_for(self, policy_name: PolicyName) -> ResearchSchedulingResult:
        try:
            return self.results_by_policy[policy_name]
        except KeyError as exc:
            raise KeyError(f"Policy {policy_name.value!r} is absent") from exc


@dataclass(frozen=True, slots=True)
class AggregatePolicyMetrics:
    """Descriptive means across a deterministic synthetic seed suite."""

    policy_name: PolicyName
    cases: int
    mean_assigned_events: float
    mean_pending_events: float
    mean_assignment_rate: float
    mean_late_assignments: float
    mean_total_tardiness_days: float
    mean_overbooking_assignments: float
    mean_route_completion_rate: float


@dataclass(frozen=True, slots=True)
class ExperimentComparison:
    """Per-instance results and per-policy descriptive aggregates."""

    cases: tuple[ExperimentCaseResult, ...]
    aggregates: tuple[AggregatePolicyMetrics, ...]

    @property
    def aggregates_by_policy(self) -> Mapping[PolicyName, AggregatePolicyMetrics]:
        return MappingProxyType(
            {aggregate.policy_name: aggregate for aggregate in self.aggregates}
        )


@dataclass(frozen=True, slots=True)
class PolicyDifferentiationDiagnostics:
    """Transparent behavioral difference counts across experiment cases."""

    reference_policy: PolicyName
    comparison_policy: PolicyName
    instances_with_different_final_assignments: int
    decision_steps_differing: int
