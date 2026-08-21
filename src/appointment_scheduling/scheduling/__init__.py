"""Policy-neutral scheduling state, eligibility, and capacity mechanics."""

from appointment_scheduling.scheduling.eligibility import (
    get_candidate_slots,
    get_event_status,
    get_timing_window,
    is_event_dependency_eligible,
    is_resource_compatible,
)
from appointment_scheduling.scheduling.models import (
    AvailabilityOpportunity,
    CandidateSlot,
    CapacityState,
    CapacityType,
    EventAssignment,
    EventStatus,
    PendingEvent,
    PendingReason,
    SchedulingState,
    SchedulingStateSummary,
    TimingWindow,
)
from appointment_scheduling.scheduling.state import (
    assign_event,
    build_scheduling_state,
    mark_pending,
)
from appointment_scheduling.scheduling.validation import (
    AssignmentConflictError,
    CapacityStateError,
    EventNotEligibleError,
    PendingStateError,
    SchedulingValidationError,
    StaleCandidateError,
    UnknownSchedulingEventError,
    validate_state,
)

__all__ = [
    "AssignmentConflictError",
    "AvailabilityOpportunity",
    "CandidateSlot",
    "CapacityState",
    "CapacityStateError",
    "CapacityType",
    "EventAssignment",
    "EventNotEligibleError",
    "EventStatus",
    "PendingEvent",
    "PendingReason",
    "PendingStateError",
    "SchedulingState",
    "SchedulingStateSummary",
    "SchedulingValidationError",
    "StaleCandidateError",
    "TimingWindow",
    "UnknownSchedulingEventError",
    "assign_event",
    "build_scheduling_state",
    "get_candidate_slots",
    "get_event_status",
    "get_timing_window",
    "is_event_dependency_eligible",
    "is_resource_compatible",
    "mark_pending",
    "validate_state",
]
