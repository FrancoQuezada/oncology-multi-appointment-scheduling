from dataclasses import fields

import pandas as pd

from appointment_scheduling.research import (
    PolicyMetrics,
    PolicyName,
    aggregate_table,
    comparison_table,
    policy_differentiation,
    run_applied_sequential_baseline,
    run_asap_policy,
    run_experiment_case,
    run_multi_seed_experiment,
    run_resource_aware_policy,
)
from appointment_scheduling.scheduling import build_scheduling_state


def test_default_experiment_runs_three_isolated_policies(
    canonical_research_case,
) -> None:
    assert tuple(canonical_research_case.results_by_policy) == (
        PolicyName.APPLIED_SEQUENTIAL,
        PolicyName.ASAP,
        PolicyName.RESOURCE_AWARE,
    )
    assert len(
        {
            id(result.final_state)
            for result in canonical_research_case.policy_results
        }
    ) == 3


def test_seed_42_three_policy_metrics_are_deterministic(
    canonical_research_case,
) -> None:
    resource = canonical_research_case.result_for(PolicyName.RESOURCE_AWARE).metrics

    assert resource.assigned_events == 17
    assert resource.pending_events == 3
    assert resource.assignment_rate == 0.85
    assert resource.fully_completed_routes == 1
    assert resource.route_completion_rate == 0.25
    assert resource.late_assignments == 6
    assert resource.total_tardiness_days == 44
    assert resource.mean_tardiness_days == 44 / 17
    assert resource.max_tardiness_days == 18
    assert resource.overbooking_assignments == 1
    assert resource.capacity_remaining == 252


def test_existing_applied_and_asap_results_are_unchanged(
    canonical_state,
    canonical_research_case,
) -> None:
    baseline = canonical_research_case.result_for(PolicyName.APPLIED_SEQUENTIAL)
    asap = canonical_research_case.result_for(PolicyName.ASAP)

    assert baseline == run_applied_sequential_baseline(canonical_state)
    assert asap == run_asap_policy(canonical_state)
    assert baseline.metrics.assigned_events == asap.metrics.assigned_events == 18
    assert baseline.metrics.total_tardiness_days == asap.metrics.total_tardiness_days == 29


def test_three_policy_comparison_schema_is_common(canonical_research_case) -> None:
    table = comparison_table(canonical_research_case)

    assert tuple(table.index) == tuple(item.name for item in fields(PolicyMetrics))
    assert tuple(table.columns) == (
        "APPLIED_SEQUENTIAL",
        "ASAP",
        "RESOURCE_AWARE",
    )


def test_three_policy_case_repeats_identically(demo_scheduling_components) -> None:
    _, routes, availability, starts = demo_scheduling_components

    def factory():
        return build_scheduling_state(routes, availability, starts)

    first = run_experiment_case("seed-42", factory)
    second = run_experiment_case("seed-42", factory)

    assert first == second
    pd.testing.assert_frame_equal(comparison_table(first), comparison_table(second))


def test_five_seed_resource_aware_aggregates_are_deterministic() -> None:
    comparison = run_multi_seed_experiment()
    resource = comparison.aggregates_by_policy[PolicyName.RESOURCE_AWARE]

    assert resource.mean_assigned_events == 15.0
    assert resource.mean_pending_events == 5.0
    assert resource.mean_assignment_rate == 0.75
    assert resource.mean_late_assignments == 5.4
    assert resource.mean_total_tardiness_days == 40.0
    assert resource.mean_overbooking_assignments == 0.8
    assert resource.mean_route_completion_rate == 0.3


def test_five_seed_three_policy_output_repeats_identically() -> None:
    first = run_multi_seed_experiment()
    second = run_multi_seed_experiment()

    assert first == second
    pd.testing.assert_frame_equal(aggregate_table(first), aggregate_table(second))


def test_behavioral_differentiation_is_transparent() -> None:
    diagnostics = policy_differentiation(run_multi_seed_experiment())

    assert diagnostics.reference_policy is PolicyName.ASAP
    assert diagnostics.comparison_policy is PolicyName.RESOURCE_AWARE
    assert diagnostics.instances_with_different_final_assignments == 5
    assert diagnostics.decision_steps_differing == 29


def test_resource_aware_does_not_mutate_other_policy_state(
    demo_scheduling_components,
) -> None:
    _, routes, availability, starts = demo_scheduling_components
    untouched = build_scheduling_state(routes, availability, starts)
    resource_input = build_scheduling_state(routes, availability, starts)

    run_resource_aware_policy(resource_input)

    assert untouched.assignments == {}
    assert untouched.summary.used_capacity == 0
    assert resource_input.assignments == {}
