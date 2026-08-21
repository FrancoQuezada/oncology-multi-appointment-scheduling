"""Small deterministic runner for isolated public policy comparisons."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import fields
from datetime import date
from itertools import zip_longest
from statistics import fmean

import pandas as pd

from appointment_scheduling.config import DEMO_START_DATE
from appointment_scheduling.preprocessing import preprocess_supply
from appointment_scheduling.routes import preprocess_routes
from appointment_scheduling.schedulers import run_sequential_scheduler
from appointment_scheduling.scheduling import SchedulingState, build_scheduling_state, validate_state
from appointment_scheduling.synthetic.generator import generate_demo_dataset

from appointment_scheduling.research.experiments.metrics import (
    research_result_from_sequential,
)
from appointment_scheduling.research.models import (
    AggregatePolicyMetrics,
    ExperimentCaseResult,
    ExperimentComparison,
    PolicyMetrics,
    PolicyDifferentiationDiagnostics,
    PolicyName,
    ResearchSchedulingResult,
)
from appointment_scheduling.research.policies.asap import run_asap_policy
from appointment_scheduling.research.policies.resource_aware import (
    run_resource_aware_policy,
)

InitialStateFactory = Callable[[], SchedulingState]
ResearchPolicy = Callable[[SchedulingState], ResearchSchedulingResult]


class ExperimentIsolationError(ValueError):
    """Raised when policies do not receive distinct equivalent initial states."""


def run_applied_sequential_baseline(
    initial_state: SchedulingState,
) -> ResearchSchedulingResult:
    """Adapt the existing operational workflow to the research result contract."""

    result = run_sequential_scheduler(initial_state)
    return research_result_from_sequential(PolicyName.APPLIED_SEQUENTIAL, result)


DEFAULT_POLICIES: tuple[ResearchPolicy, ...] = (
    run_applied_sequential_baseline,
    run_asap_policy,
    run_resource_aware_policy,
)


def run_experiment_case(
    instance_id: str,
    initial_state_factory: InitialStateFactory,
    policies: Iterable[ResearchPolicy] = DEFAULT_POLICIES,
) -> ExperimentCaseResult:
    """Run every policy from a distinct, logically equivalent initial state."""

    policy_tuple = tuple(policies)
    if not policy_tuple:
        raise ExperimentIsolationError("At least one research policy is required")
    states = tuple(initial_state_factory() for _ in policy_tuple)
    if len({id(state) for state in states}) != len(states):
        raise ExperimentIsolationError("Each policy requires a fresh state object")
    for state in states:
        validate_state(state)
    reference = states[0]
    if any(state != reference for state in states[1:]):
        raise ExperimentIsolationError(
            "Policy initial states must be logically equivalent"
        )

    results = tuple(
        policy(initial_state)
        for policy, initial_state in zip(policy_tuple, states)
    )
    policy_names = tuple(result.policy_name for result in results)
    if len(set(policy_names)) != len(policy_names):
        raise ExperimentIsolationError("Policy identifiers must be unique")
    if any(state != reference for state in states):
        raise ExperimentIsolationError("A policy mutated its initial state")
    return ExperimentCaseResult(instance_id=instance_id, policy_results=results)


def comparison_table(case: ExperimentCaseResult) -> pd.DataFrame:
    """Return common metrics as rows and stable policy identifiers as columns."""

    metric_names = tuple(field.name for field in fields(PolicyMetrics))
    return pd.DataFrame(
        {
            result.policy_name.value: [
                getattr(result.metrics, name) for name in metric_names
            ]
            for result in case.policy_results
        },
        index=metric_names,
    )


def _synthetic_state_factory(seed: int) -> InitialStateFactory:
    datasets = generate_demo_dataset(seed=seed)
    routes = preprocess_routes(datasets["routes"])
    availability = preprocess_supply(
        datasets["supply"],
        datasets["blocks"],
        datasets["resource_mapping"],
    ).availability
    starts = {
        patient_id: date.fromisoformat(DEMO_START_DATE.isoformat())
        for patient_id in routes.routes_by_patient
    }

    def factory() -> SchedulingState:
        return build_scheduling_state(routes, availability, starts)

    return factory


def _aggregate_cases(
    cases: tuple[ExperimentCaseResult, ...],
) -> tuple[AggregatePolicyMetrics, ...]:
    policy_names = tuple(result.policy_name for result in cases[0].policy_results)
    aggregates = []
    for policy_name in policy_names:
        metrics = tuple(case.result_for(policy_name).metrics for case in cases)
        aggregates.append(
            AggregatePolicyMetrics(
                policy_name=policy_name,
                cases=len(metrics),
                mean_assigned_events=fmean(item.assigned_events for item in metrics),
                mean_pending_events=fmean(item.pending_events for item in metrics),
                mean_assignment_rate=fmean(item.assignment_rate for item in metrics),
                mean_late_assignments=fmean(item.late_assignments for item in metrics),
                mean_total_tardiness_days=fmean(
                    item.total_tardiness_days for item in metrics
                ),
                mean_overbooking_assignments=fmean(
                    item.overbooking_assignments for item in metrics
                ),
                mean_route_completion_rate=fmean(
                    item.route_completion_rate for item in metrics
                ),
            )
        )
    return tuple(aggregates)


def run_multi_seed_experiment(
    seeds: Iterable[int] = (42, 43, 44, 45, 46),
    policies: Iterable[ResearchPolicy] = DEFAULT_POLICIES,
) -> ExperimentComparison:
    """Run a small reproducible synthetic suite and compute descriptive means."""

    seed_tuple = tuple(seeds)
    if not seed_tuple:
        raise ExperimentIsolationError("At least one synthetic seed is required")
    if len(set(seed_tuple)) != len(seed_tuple):
        raise ExperimentIsolationError("Synthetic seeds must be unique")
    policy_tuple = tuple(policies)
    cases = tuple(
        run_experiment_case(
            instance_id=f"synthetic-seed-{seed}",
            initial_state_factory=_synthetic_state_factory(seed),
            policies=policy_tuple,
        )
        for seed in seed_tuple
    )
    return ExperimentComparison(cases=cases, aggregates=_aggregate_cases(cases))


def aggregate_table(comparison: ExperimentComparison) -> pd.DataFrame:
    """Return recruiter-friendly aggregate means without policy-specific logic."""

    names = tuple(
        field.name
        for field in fields(AggregatePolicyMetrics)
        if field.name not in {"policy_name", "cases"}
    )
    return pd.DataFrame(
        {
            aggregate.policy_name.value: [
                getattr(aggregate, name) for name in names
            ]
            for aggregate in comparison.aggregates
        },
        index=names,
    )


def policy_differentiation(
    comparison: ExperimentComparison,
    reference_policy: PolicyName = PolicyName.ASAP,
    comparison_policy: PolicyName = PolicyName.RESOURCE_AWARE,
) -> PolicyDifferentiationDiagnostics:
    """Count assignment-set and trace-step differences across all cases."""

    differing_instances = 0
    differing_steps = 0
    for case in comparison.cases:
        reference = case.result_for(reference_policy)
        compared = case.result_for(comparison_policy)
        if reference.final_state.assignments != compared.final_state.assignments:
            differing_instances += 1

        def signature(entry):
            if entry is None:
                return None
            return (
                entry.patient_id,
                entry.event_number,
                entry.outcome,
                entry.chosen_opportunity_id,
                entry.chosen_date,
                entry.pending_reason,
            )

        differing_steps += sum(
            signature(reference_entry) != signature(compared_entry)
            for reference_entry, compared_entry in zip_longest(
                reference.trace,
                compared.trace,
            )
        )
    return PolicyDifferentiationDiagnostics(
        reference_policy=reference_policy,
        comparison_policy=comparison_policy,
        instances_with_different_final_assignments=differing_instances,
        decision_steps_differing=differing_steps,
    )
