"""Immutable public models for patient route instances and pathway graphs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class ResourceMode(str, Enum):
    """Whether a route resource is fixed or one compatible option."""

    FIXED = "FIXED"
    COMPATIBLE_SET = "COMPATIBLE_SET"


@dataclass(frozen=True, slots=True)
class RouteEvent:
    """One patient-specific event and its scheduling requirements."""

    patient_id: str
    pathway_id: str
    event_number: int
    event_id: str
    event_type: str
    dependencies: tuple[int, ...]
    min_spacing_days: int
    preferred_max_spacing_days: int
    clinician_id: str
    service_id: str
    section_id: str
    agenda_id: str
    modality: str
    resource_mode: ResourceMode
    overbooking_allowed: bool


@dataclass(frozen=True, slots=True)
class PathwayEventTemplate:
    """Patient-independent structural definition of an artificial event."""

    event_number: int
    event_id: str
    event_type: str
    dependencies: tuple[int, ...]
    min_spacing_days: int
    preferred_max_spacing_days: int
    resource_mode: ResourceMode = ResourceMode.COMPATIBLE_SET


@dataclass(frozen=True, slots=True)
class PathwayTemplate:
    """Artificial pathway structure shared by multiple patient instances."""

    pathway_id: str
    events: tuple[PathwayEventTemplate, ...]


@dataclass(frozen=True, slots=True)
class RouteGraph:
    """Immutable dependency graph derived from one patient route."""

    predecessors: Mapping[int, tuple[int, ...]]
    successors: Mapping[int, tuple[int, ...]]
    topological_order: tuple[int, ...]
    root_events: tuple[int, ...]
    terminal_events: tuple[int, ...]
    branch_events: tuple[int, ...]
    join_events: tuple[int, ...]
    depth_by_event: Mapping[int, int]
    max_depth: int

    @classmethod
    def create(
        cls,
        predecessors: Mapping[int, tuple[int, ...]],
        successors: Mapping[int, tuple[int, ...]],
        topological_order: tuple[int, ...],
        depth_by_event: Mapping[int, int],
    ) -> RouteGraph:
        """Create a graph with defensively copied, read-only mappings."""

        predecessor_copy = {
            number: tuple(values) for number, values in predecessors.items()
        }
        successor_copy = {
            number: tuple(values) for number, values in successors.items()
        }
        depth_copy = dict(depth_by_event)
        return cls(
            predecessors=MappingProxyType(predecessor_copy),
            successors=MappingProxyType(successor_copy),
            topological_order=topological_order,
            root_events=tuple(
                number for number in topological_order if not predecessor_copy[number]
            ),
            terminal_events=tuple(
                number for number in topological_order if not successor_copy[number]
            ),
            branch_events=tuple(
                number for number in topological_order if len(successor_copy[number]) > 1
            ),
            join_events=tuple(
                number for number in topological_order if len(predecessor_copy[number]) > 1
            ),
            depth_by_event=MappingProxyType(depth_copy),
            max_depth=max(depth_copy.values(), default=0),
        )

    def predecessors_of(self, event_number: int) -> tuple[int, ...]:
        """Return direct predecessors of an event."""

        return self.predecessors[event_number]

    def successors_of(self, event_number: int) -> tuple[int, ...]:
        """Return direct successors of an event."""

        return self.successors[event_number]


@dataclass(frozen=True, slots=True)
class PatientRoute:
    """One immutable patient-specific instance of a pathway template."""

    patient_id: str
    pathway_id: str
    events: tuple[RouteEvent, ...]
    graph: RouteGraph

    def event(self, event_number: int) -> RouteEvent:
        """Return an event by its one-based number."""

        for route_event in self.events:
            if route_event.event_number == event_number:
                return route_event
        raise KeyError(f"Unknown event number {event_number} for {self.patient_id}")

    def temporal_lower_bound(
        self,
        event_number: int,
        scheduled_predecessor_dates: Mapping[int, date | datetime],
    ) -> date | datetime:
        """Compute a dependent event's date lower bound without scheduling it.

        The reference is the latest realized predecessor date plus the dependent
        event's minimum spacing. Root events require an external route-start
        reference and therefore do not have a predecessor-derived lower bound.
        """

        from appointment_scheduling.routes.validation import RouteTimingError

        route_event = self.event(event_number)
        if not route_event.dependencies:
            raise RouteTimingError(
                f"Event {event_number} is a root and has no predecessor lower bound"
            )
        missing = [
            predecessor
            for predecessor in route_event.dependencies
            if predecessor not in scheduled_predecessor_dates
        ]
        if missing:
            raise RouteTimingError(
                f"Missing scheduled predecessor dates for event {event_number}: {missing}"
            )
        values = [
            scheduled_predecessor_dates[predecessor]
            for predecessor in route_event.dependencies
        ]
        if any(not isinstance(value, (date, datetime)) for value in values):
            raise RouteTimingError("Scheduled predecessor values must be dates")
        try:
            reference = max(values)
        except TypeError as exc:
            raise RouteTimingError(
                "Scheduled predecessor dates must use compatible date types"
            ) from exc
        return reference + timedelta(days=route_event.min_spacing_days)


@dataclass(frozen=True, slots=True)
class RoutePreprocessingDiagnostics:
    """Structural totals across all patient route instances."""

    patients: int
    routes: int
    events: int
    dependency_arcs: int
    root_events: int
    terminal_events: int
    branch_events: int
    join_events: int
    max_route_depth: int


@dataclass(frozen=True, slots=True)
class RoutePreprocessingResult:
    """Patient routes, their templates, and aggregate graph diagnostics."""

    patient_routes: tuple[PatientRoute, ...]
    pathway_templates: tuple[PathwayTemplate, ...]
    diagnostics: RoutePreprocessingDiagnostics

    @property
    def routes_by_patient(self) -> Mapping[str, PatientRoute]:
        """Return a read-only patient-to-route index."""

        return MappingProxyType(
            {route.patient_id: route for route in self.patient_routes}
        )

    def route_for(self, patient_id: str) -> PatientRoute:
        """Return the route for one patient."""

        try:
            return self.routes_by_patient[patient_id]
        except KeyError as exc:
            raise KeyError(f"Unknown patient route {patient_id!r}") from exc
