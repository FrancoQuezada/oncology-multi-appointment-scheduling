"""Greedy resource-aware research policy using current dynamic capacity."""

from __future__ import annotations

from dataclasses import replace

from appointment_scheduling.routes import RouteEvent
from appointment_scheduling.schedulers import (
    SchedulingDecision,
    run_sequential_scheduler,
)
from appointment_scheduling.scheduling import (
    CandidateSlot,
    CapacityType,
    SchedulingState,
)

from appointment_scheduling.research.experiments.metrics import (
    research_result_from_sequential,
)
from appointment_scheduling.research.models import (
    CandidateRegion,
    PolicyName,
    ResearchSchedulingResult,
    ResourceAwareDecisionDiagnostics,
)


def _select_resource_aware_candidate(
    candidates: tuple[CandidateSlot, ...],
) -> tuple[CandidateSlot, ResourceAwareDecisionDiagnostics]:
    """Select by current bottleneck capacity within the active timing region."""

    preferred = tuple(
        candidate for candidate in candidates if candidate.within_preferred_window
    )
    active = preferred or candidates
    candidate_region = (
        CandidateRegion.PREFERRED_WINDOW
        if preferred
        else CandidateRegion.LATE_FALLBACK
    )

    standard = tuple(
        candidate
        for candidate in active
        if candidate.capacity_type_required is CapacityType.STANDARD
    )
    capacity_region = standard or active

    def resource_score(candidate: CandidateSlot) -> int:
        if standard:
            return candidate.standard_remaining_capacity
        return candidate.total_remaining_capacity

    selected = min(
        capacity_region,
        key=lambda candidate: (
            -resource_score(candidate),
            candidate.date,
            0
            if candidate.capacity_type_required is CapacityType.STANDARD
            else 1,
            candidate.agenda_id,
            candidate.clinician_id,
            candidate.schedule_key,
            candidate.opportunity_id,
        ),
    )
    best_score = max(resource_score(candidate) for candidate in capacity_region)
    return selected, ResourceAwareDecisionDiagnostics(
        patient_id=selected.patient_id,
        event_number=selected.event_number,
        candidate_count=len(candidates),
        preferred_window_candidate_count=len(preferred),
        candidate_region=candidate_region,
        selected_resource_score=resource_score(selected),
        best_resource_score=best_score,
        selected_date=selected.date,
        selected_opportunity_id=selected.opportunity_id,
    )


def run_resource_aware_policy(
    initial_state: SchedulingState,
) -> ResearchSchedulingResult:
    """Run the local, dynamic-capacity resource-aware research heuristic."""

    diagnostics: list[ResourceAwareDecisionDiagnostics] = []

    def resource_aware_rule(
        event: RouteEvent,
        candidates: tuple[CandidateSlot, ...],
        state: SchedulingState,
    ) -> SchedulingDecision:
        del event, state
        selected, diagnostic = _select_resource_aware_candidate(candidates)
        diagnostics.append(diagnostic)
        return SchedulingDecision.assign(selected)

    workflow_result = run_sequential_scheduler(
        initial_state,
        decision_rule=resource_aware_rule,
    )
    common_result = research_result_from_sequential(
        PolicyName.RESOURCE_AWARE,
        workflow_result,
    )
    return replace(common_result, policy_diagnostics=tuple(diagnostics))
