from hashlib import sha256
from pathlib import Path

from appointment_scheduling.research import (
    PolicyName,
    aggregate_table,
    run_multi_seed_experiment,
)


DEMO_DIR = Path(__file__).resolve().parents[1] / "data" / "demo"


def _fixture_hashes() -> dict[str, str]:
    return {
        path.name: sha256(path.read_bytes()).hexdigest()
        for path in sorted(DEMO_DIR.glob("*.csv"))
    }


def test_five_seed_experiment_runs() -> None:
    comparison = run_multi_seed_experiment()

    assert len(comparison.cases) == 5
    assert tuple(case.instance_id for case in comparison.cases) == tuple(
        f"synthetic-seed-{seed}" for seed in (42, 43, 44, 45, 46)
    )
    assert all(len(case.policy_results) == 3 for case in comparison.cases)


def test_five_seed_aggregate_metrics_are_expected() -> None:
    comparison = run_multi_seed_experiment()

    for policy in (PolicyName.APPLIED_SEQUENTIAL, PolicyName.ASAP):
        aggregate = comparison.aggregates_by_policy[policy]
        assert aggregate.cases == 5
        assert aggregate.mean_assigned_events == 15.4
        assert aggregate.mean_pending_events == 4.6
        assert aggregate.mean_assignment_rate == 0.77
        assert aggregate.mean_late_assignments == 6.4
        assert aggregate.mean_total_tardiness_days == 28.6
        assert aggregate.mean_overbooking_assignments == 1.2
        assert aggregate.mean_route_completion_rate == 0.35


def test_multi_seed_experiment_is_deterministic() -> None:
    first = run_multi_seed_experiment()
    second = run_multi_seed_experiment()

    assert first == second
    assert aggregate_table(first).equals(aggregate_table(second))


def test_per_seed_policy_metric_schema_is_stable() -> None:
    comparison = run_multi_seed_experiment()

    for case in comparison.cases:
        baseline = case.result_for(PolicyName.APPLIED_SEQUENTIAL)
        asap = case.result_for(PolicyName.ASAP)
        assert type(baseline.metrics) is type(asap.metrics)


def test_multi_seed_experiment_does_not_change_committed_fixtures() -> None:
    before = _fixture_hashes()

    run_multi_seed_experiment()

    assert _fixture_hashes() == before
