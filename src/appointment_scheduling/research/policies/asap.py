"""Explicit earliest-feasible research policy with stable ASAP identity."""

from __future__ import annotations

from appointment_scheduling.routes import RouteEvent
from appointment_scheduling.schedulers import (
    SchedulingDecision,
    run_sequential_scheduler,
)
from appointment_scheduling.scheduling import CandidateSlot, SchedulingState

from appointment_scheduling.research.experiments.metrics import (
    research_result_from_sequential,
)
from appointment_scheduling.research.models import (
    PolicyName,
    ResearchSchedulingResult,
)


def _asap_decision_rule(
    event: RouteEvent,
    candidates: tuple[CandidateSlot, ...],
    state: SchedulingState,
) -> SchedulingDecision:
    """Choose the earliest current candidate with documented stable ties."""

    del event, state
    candidate = min(
        candidates,
        key=lambda item: (
            item.date,
            item.agenda_id,
            item.clinician_id,
            item.schedule_key,
            item.opportunity_id,
        ),
    )
    return SchedulingDecision.assign(candidate)


def run_asap_policy(initial_state: SchedulingState) -> ResearchSchedulingResult:
    """Run ASAP from one clean state using shared workflow and feasibility APIs."""

    workflow_result = run_sequential_scheduler(
        initial_state,
        decision_rule=_asap_decision_rule,
    )
    return research_result_from_sequential(PolicyName.ASAP, workflow_result)
