"""Typed models for policy-neutral scheduling feasibility and state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from appointment_scheduling.routes import (
    PatientRoute,
    RouteEvent,
    RoutePreprocessingResult,
)

EventKey = tuple[str, int]


class CapacityType(str, Enum):
    """Capacity tier required by one candidate or assignment."""

    STANDARD = "STANDARD"
    OVERBOOKING = "OVERBOOKING"


class EventStatus(str, Enum):
    """Current, mutually exclusive scheduling state of an event."""

    ELIGIBLE = "ELIGIBLE"
    BLOCKED_BY_PREDECESSOR = "BLOCKED_BY_PREDECESSOR"
    ASSIGNED = "ASSIGNED"
    PENDING = "PENDING"


class PendingReason(str, Enum):
    """Public-safe controlled reasons for an explicit unresolved event."""

    NO_FEASIBLE_CAPACITY = "NO_FEASIBLE_CAPACITY"
    HORIZON_EXCEEDED = "HORIZON_EXCEEDED"
    PREDECESSOR_PENDING = "PREDECESSOR_PENDING"
    MANUAL_DECISION = "MANUAL_DECISION"


@dataclass(frozen=True, slots=True)
class TimingWindow:
    """Hard lower date and soft preferred upper date for slot search."""

    earliest_date: date
    preferred_latest_date: date


@dataclass(frozen=True, slots=True)
class AvailabilityOpportunity:
    """One immutable, preprocessed day-level supply opportunity."""

    opportunity_id: str
    date: date
    schedule_key: str
    agenda_id: str
    clinician_id: str
    resource_mapping_key: str
    service_id: str
    section_id: str
    center_id: str
    modality: str
    event_type: str
    standard_available_capacity: int
    total_available_capacity: int


@dataclass(frozen=True, slots=True)
class CapacityState:
    """Copy-on-write usage for exactly one supply opportunity."""

    opportunity_id: str
    standard_capacity: int
    total_capacity: int
    used_standard_capacity: int = 0
    used_overbooking_capacity: int = 0

    @property
    def used_total_capacity(self) -> int:
        return self.used_standard_capacity + self.used_overbooking_capacity

    @property
    def remaining_standard_capacity(self) -> int:
        return self.standard_capacity - self.used_standard_capacity

    @property
    def remaining_total_capacity(self) -> int:
        return self.total_capacity - self.used_total_capacity

    def consume(self, capacity_type: CapacityType) -> CapacityState:
        """Return a new capacity value after one auditable unit is consumed."""

        if capacity_type is CapacityType.STANDARD:
            if self.remaining_standard_capacity <= 0:
                raise ValueError("No standard capacity remains")
            return CapacityState(
                opportunity_id=self.opportunity_id,
                standard_capacity=self.standard_capacity,
                total_capacity=self.total_capacity,
                used_standard_capacity=self.used_standard_capacity + 1,
                used_overbooking_capacity=self.used_overbooking_capacity,
            )
        if self.remaining_standard_capacity > 0:
            raise ValueError("Overbooking cannot be used before standard capacity")
        if self.remaining_total_capacity <= 0:
            raise ValueError("No total capacity remains")
        return CapacityState(
            opportunity_id=self.opportunity_id,
            standard_capacity=self.standard_capacity,
            total_capacity=self.total_capacity,
            used_standard_capacity=self.used_standard_capacity,
            used_overbooking_capacity=self.used_overbooking_capacity + 1,
        )


@dataclass(frozen=True, slots=True)
class CandidateSlot:
    """One currently feasible option, without any policy ranking."""

    patient_id: str
    event_number: int
    event_id: str
    opportunity_id: str
    date: date
    schedule_key: str
    agenda_id: str
    clinician_id: str
    service_id: str
    section_id: str
    center_id: str
    modality: str
    event_type: str
    standard_remaining_capacity: int
    total_remaining_capacity: int
    capacity_type_required: CapacityType
    within_preferred_window: bool
    uses_preferred_resource: bool


@dataclass(frozen=True, slots=True)
class EventAssignment:
    """One day-level assignment tied to one exact supply opportunity."""

    patient_id: str
    event_number: int
    event_id: str
    date: date
    opportunity_id: str
    schedule_key: str
    agenda_id: str
    clinician_id: str
    service_id: str
    section_id: str
    modality: str
    capacity_type: CapacityType


@dataclass(frozen=True, slots=True)
class PendingEvent:
    """An explicit unresolved transition selected by a caller."""

    patient_id: str
    event_number: int
    reason: PendingReason


@dataclass(frozen=True, slots=True)
class SchedulingStateSummary:
    """Compact diagnostics for a dynamic scheduling snapshot."""

    patients: int
    total_events: int
    assigned_events: int
    eligible_events: int
    dependency_blocked_events: int
    pending_events: int
    total_capacity: int
    used_capacity: int
    remaining_capacity: int
    overbooking_used: int


@dataclass(frozen=True, slots=True)
class SchedulingState:
    """Immutable snapshot combining routes, supply, and dynamic decisions."""

    routes: RoutePreprocessingResult
    opportunities: tuple[AvailabilityOpportunity, ...]
    route_start_dates: Mapping[str, date]
    assignments: Mapping[EventKey, EventAssignment]
    capacity_by_opportunity: Mapping[str, CapacityState]
    pending_events: Mapping[EventKey, PendingEvent]

    @classmethod
    def create(
        cls,
        routes: RoutePreprocessingResult,
        opportunities: tuple[AvailabilityOpportunity, ...],
        route_start_dates: Mapping[str, date],
        assignments: Mapping[EventKey, EventAssignment],
        capacity_by_opportunity: Mapping[str, CapacityState],
        pending_events: Mapping[EventKey, PendingEvent],
    ) -> SchedulingState:
        """Defensively copy mappings into a read-only state snapshot."""

        return cls(
            routes=routes,
            opportunities=tuple(opportunities),
            route_start_dates=MappingProxyType(dict(route_start_dates)),
            assignments=MappingProxyType(dict(assignments)),
            capacity_by_opportunity=MappingProxyType(dict(capacity_by_opportunity)),
            pending_events=MappingProxyType(dict(pending_events)),
        )

    @property
    def opportunities_by_id(self) -> Mapping[str, AvailabilityOpportunity]:
        return MappingProxyType(
            {item.opportunity_id: item for item in self.opportunities}
        )

    @property
    def horizon_start(self) -> date:
        return min(item.date for item in self.opportunities)

    @property
    def horizon_end(self) -> date:
        return max(item.date for item in self.opportunities)

    def route_for(self, patient_id: str) -> PatientRoute:
        return self.routes.route_for(patient_id)

    def event(self, patient_id: str, event_number: int) -> RouteEvent:
        return self.route_for(patient_id).event(event_number)

    def status_for(self, patient_id: str, event_number: int) -> EventStatus:
        from appointment_scheduling.scheduling.eligibility import get_event_status

        return get_event_status(self, patient_id, event_number)

    @property
    def summary(self) -> SchedulingStateSummary:
        from appointment_scheduling.scheduling.eligibility import summarize_state

        return summarize_state(self)
