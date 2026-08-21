import pytest

from appointment_scheduling.research import PolicyName
from appointment_scheduling.scheduling import CapacityType, get_timing_window


def test_assignment_and_route_rates_use_documented_denominators(
    canonical_research_case,
) -> None:
    metrics = canonical_research_case.result_for(PolicyName.ASAP).metrics

    assert metrics.assignment_rate == metrics.assigned_events / metrics.total_events
    assert metrics.route_completion_rate == metrics.fully_completed_routes / 4


def test_canonical_tardiness_metrics_are_exact(canonical_research_case) -> None:
    metrics = canonical_research_case.result_for(PolicyName.ASAP).metrics

    assert metrics.late_assignments == 8
    assert metrics.total_tardiness_days == 29
    assert metrics.mean_tardiness_days == pytest.approx(29 / 18)
    assert metrics.max_tardiness_days == 9
    assert metrics.late_assignment_rate == pytest.approx(8 / 18)


def test_zero_tardiness_assignments_contribute_zero_to_mean(
    canonical_research_case,
) -> None:
    result = canonical_research_case.result_for(PolicyName.ASAP)
    tardiness = []
    for assignment in result.final_state.assignments.values():
        window = get_timing_window(
            result.final_state,
            assignment.patient_id,
            assignment.event_number,
        )
        tardiness.append(max((assignment.date - window.preferred_latest_date).days, 0))

    assert 0 in tardiness
    assert sum(tardiness) / len(tardiness) == result.metrics.mean_tardiness_days


def test_standard_and_overbooking_assignments_are_counted(
    canonical_research_case,
) -> None:
    result = canonical_research_case.result_for(PolicyName.ASAP)
    assignments = tuple(result.final_state.assignments.values())

    assert result.metrics.standard_assignments == sum(
        item.capacity_type is CapacityType.STANDARD for item in assignments
    )
    assert result.metrics.overbooking_assignments == sum(
        item.capacity_type is CapacityType.OVERBOOKING for item in assignments
    )


def test_overbooking_rate_uses_assigned_events(canonical_research_case) -> None:
    metrics = canonical_research_case.result_for(PolicyName.ASAP).metrics

    assert metrics.overbooking_rate == pytest.approx(1 / 18)


def test_capacity_metrics_reconcile(canonical_research_case) -> None:
    result = canonical_research_case.result_for(PolicyName.ASAP)
    metrics = result.metrics

    assert metrics.capacity_used == metrics.assigned_events
    assert metrics.capacity_used + metrics.capacity_remaining == 269


def test_common_metrics_have_no_combined_artificial_score(
    canonical_research_case,
) -> None:
    metrics = canonical_research_case.result_for(PolicyName.ASAP).metrics

    assert not hasattr(metrics, "score")
    assert metrics.total_tardiness_days >= 0
    assert metrics.overbooking_assignments >= 0
