from dataclasses import fields

import pandas as pd
import pytest

from appointment_scheduling.research import (
    ExperimentIsolationError,
    PolicyMetrics,
    PolicyName,
    comparison_table,
    run_applied_sequential_baseline,
    run_asap_policy,
    run_experiment_case,
)
from appointment_scheduling.schedulers import run_sequential_scheduler
from appointment_scheduling.scheduling import build_scheduling_state


def test_applied_adapter_reproduces_operational_scheduler(canonical_state) -> None:
    operational = run_sequential_scheduler(canonical_state)
    adapted = run_applied_sequential_baseline(canonical_state)

    assert adapted.policy_name is PolicyName.APPLIED_SEQUENTIAL
    assert adapted.final_state == operational.final_state
    assert adapted.metrics.assigned_events == operational.summary.events_assigned
    assert adapted.metrics.pending_events == operational.summary.events_pending


def test_policies_have_distinct_identity(canonical_research_case) -> None:
    assert tuple(result.policy_name for result in canonical_research_case.policy_results) == (
        PolicyName.APPLIED_SEQUENTIAL,
        PolicyName.ASAP,
        PolicyName.RESOURCE_AWARE,
    )


def test_identical_seed_42_outcomes_are_accepted(canonical_research_case) -> None:
    baseline = canonical_research_case.result_for(PolicyName.APPLIED_SEQUENTIAL)
    asap = canonical_research_case.result_for(PolicyName.ASAP)

    assert baseline.metrics == asap.metrics
    assert baseline.final_state.assignments == asap.final_state.assignments


def test_comparison_has_identical_metric_schema(canonical_research_case) -> None:
    table = comparison_table(canonical_research_case)

    assert tuple(table.index) == tuple(field.name for field in fields(PolicyMetrics))
    assert tuple(table.columns) == (
        "APPLIED_SEQUENTIAL",
        "ASAP",
        "RESOURCE_AWARE",
    )
    assert not table.isna().any().any()


def test_experiment_constructs_distinct_equivalent_states(
    demo_scheduling_components,
) -> None:
    _, routes, availability, starts = demo_scheduling_components
    state_ids = []

    def factory():
        state = build_scheduling_state(routes, availability, starts)
        state_ids.append(id(state))
        return state

    run_experiment_case("isolation-check", factory)

    assert len(state_ids) == 3
    assert len(set(state_ids)) == 3


def test_reused_state_object_is_rejected(canonical_state) -> None:
    with pytest.raises(ExperimentIsolationError, match="fresh state"):
        run_experiment_case("unsafe", lambda: canonical_state)


def test_baseline_cannot_mutate_asap_initial_state(
    demo_scheduling_components,
) -> None:
    _, routes, availability, starts = demo_scheduling_components
    baseline_state = build_scheduling_state(routes, availability, starts)
    asap_state = build_scheduling_state(routes, availability, starts)
    before = asap_state

    run_applied_sequential_baseline(baseline_state)

    assert asap_state == before
    assert asap_state.assignments == {}
    assert asap_state.summary.used_capacity == 0


def test_asap_cannot_mutate_baseline_initial_state(
    demo_scheduling_components,
) -> None:
    _, routes, availability, starts = demo_scheduling_components
    baseline_state = build_scheduling_state(routes, availability, starts)
    asap_state = build_scheduling_state(routes, availability, starts)
    before = baseline_state

    run_asap_policy(asap_state)

    assert baseline_state == before
    assert baseline_state.assignments == {}


def test_seed_42_comparison_is_deterministic(demo_scheduling_components) -> None:
    _, routes, availability, starts = demo_scheduling_components

    def factory():
        return build_scheduling_state(routes, availability, starts)

    first = run_experiment_case("seed-42", factory)
    second = run_experiment_case("seed-42", factory)

    assert first == second
    pd.testing.assert_frame_equal(comparison_table(first), comparison_table(second))
