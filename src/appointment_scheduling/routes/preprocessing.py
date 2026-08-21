"""Pure preprocessing of patient route rows into deterministic DAG models."""

from __future__ import annotations

import heapq
from collections import defaultdict
from collections.abc import Sequence

import pandas as pd

from appointment_scheduling.routes.models import (
    PatientRoute,
    PathwayEventTemplate,
    PathwayTemplate,
    RouteEvent,
    RouteGraph,
    RoutePreprocessingDiagnostics,
    RoutePreprocessingResult,
    ResourceMode,
)
from appointment_scheduling.routes.validation import (
    PathwayConsistencyError,
    RouteCycleError,
    parse_dependency_list,
    validate_dependency_references,
    validate_pathway_instance,
    validate_patient_identity,
    validate_route_input,
)
from appointment_scheduling.synthetic.pathways import PATHWAYS


def _normalize_routes(routes: pd.DataFrame) -> pd.DataFrame:
    normalized = routes.copy(deep=True)
    string_columns = (
        "patient_id",
        "pathway_id",
        "event_id",
        "agenda_id",
        "event_type",
        "dependencies",
        "clinician_id",
        "service_id",
        "section_id",
        "modality",
        "resource_mode",
    )
    for column in string_columns:
        normalized[column] = normalized[column].str.strip()
    for column in (
        "event_number",
        "min_spacing_days",
        "preferred_max_spacing_days",
    ):
        normalized[column] = normalized[column].astype("int64")
    normalized["overbooking_allowed"] = normalized["overbooking_allowed"].astype(bool)
    return normalized


def _build_graph(patient_id: str, events: tuple[RouteEvent, ...]) -> RouteGraph:
    numbers = tuple(event.event_number for event in events)
    valid_numbers = set(numbers)
    predecessors = {event.event_number: event.dependencies for event in events}
    successor_lists: dict[int, list[int]] = defaultdict(list)

    for event in events:
        validate_dependency_references(
            patient_id,
            event.event_number,
            event.dependencies,
            valid_numbers,
        )
        for predecessor in event.dependencies:
            successor_lists[predecessor].append(event.event_number)

    successors = {
        number: tuple(sorted(successor_lists.get(number, ()))) for number in numbers
    }
    indegree = {number: len(predecessors[number]) for number in numbers}
    ready = [number for number in numbers if indegree[number] == 0]
    heapq.heapify(ready)
    order: list[int] = []
    while ready:
        number = heapq.heappop(ready)
        order.append(number)
        for successor in successors[number]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                heapq.heappush(ready, successor)
    if len(order) != len(numbers):
        unresolved = tuple(sorted(number for number, degree in indegree.items() if degree > 0))
        raise RouteCycleError(
            f"Patient {patient_id} route contains a cycle involving events {unresolved}"
        )

    depth_by_event: dict[int, int] = {}
    for number in order:
        depth_by_event[number] = (
            1
            if not predecessors[number]
            else max(depth_by_event[pred] for pred in predecessors[number]) + 1
        )
    return RouteGraph.create(
        predecessors=predecessors,
        successors=successors,
        topological_order=tuple(order),
        depth_by_event=depth_by_event,
    )


def _build_default_templates() -> tuple[PathwayTemplate, ...]:
    templates = []
    for pathway_id in sorted(PATHWAYS):
        events = tuple(
            PathwayEventTemplate(
                event_number=event.number,
                event_id=event.event_id,
                event_type=event.event_id,
                dependencies=tuple(event.dependencies),
                min_spacing_days=event.min_spacing_days,
                preferred_max_spacing_days=event.preferred_max_spacing_days,
                resource_mode=ResourceMode(event.resource_mode),
            )
            for event in sorted(PATHWAYS[pathway_id], key=lambda item: item.number)
        )
        templates.append(PathwayTemplate(pathway_id=pathway_id, events=events))
    return tuple(templates)


def _build_patient_route(patient_id: str, rows: pd.DataFrame) -> PatientRoute:
    validate_patient_identity(rows, patient_id)
    rows = rows.sort_values("event_number", kind="mergesort")
    events = tuple(
        RouteEvent(
            patient_id=patient_id,
            pathway_id=str(row["pathway_id"]),
            event_number=int(row["event_number"]),
            event_id=str(row["event_id"]),
            event_type=str(row["event_type"]),
            dependencies=parse_dependency_list(row["dependencies"]),
            min_spacing_days=int(row["min_spacing_days"]),
            preferred_max_spacing_days=int(row["preferred_max_spacing_days"]),
            clinician_id=str(row["clinician_id"]),
            service_id=str(row["service_id"]),
            section_id=str(row["section_id"]),
            agenda_id=str(row["agenda_id"]),
            modality=str(row["modality"]),
            resource_mode=ResourceMode(str(row["resource_mode"])),
            overbooking_allowed=bool(row["overbooking_allowed"]),
        )
        for _, row in rows.iterrows()
    )
    return PatientRoute(
        patient_id=patient_id,
        pathway_id=events[0].pathway_id,
        events=events,
        graph=_build_graph(patient_id, events),
    )


def preprocess_routes(
    routes: pd.DataFrame,
    pathway_templates: Sequence[PathwayTemplate] | None = None,
) -> RoutePreprocessingResult:
    """Convert route rows into validated patient DAGs and shared templates.

    ``pathway_templates`` defaults to the repository's artificial templates. It
    may be replaced explicitly for future synthetic experiments without changing
    the patient route representation.
    """

    validate_route_input(routes)
    normalized = _normalize_routes(routes)
    templates = (
        _build_default_templates()
        if pathway_templates is None
        else tuple(sorted(pathway_templates, key=lambda template: template.pathway_id))
    )
    template_ids = [template.pathway_id for template in templates]
    duplicate_template_ids = sorted(
        template_id
        for template_id in set(template_ids)
        if template_ids.count(template_id) > 1
    )
    if duplicate_template_ids:
        raise PathwayConsistencyError(
            f"Duplicate pathway template IDs: {duplicate_template_ids}"
        )
    templates_by_id = {template.pathway_id: template for template in templates}

    patient_routes = tuple(
        _build_patient_route(str(patient_id), rows)
        for patient_id, rows in normalized.groupby("patient_id", sort=True)
    )
    for route in patient_routes:
        if route.pathway_id not in templates_by_id:
            raise PathwayConsistencyError(
                f"Patient {route.patient_id} references unknown template {route.pathway_id}"
            )
        validate_pathway_instance(route, templates_by_id[route.pathway_id])

    diagnostics = RoutePreprocessingDiagnostics(
        patients=len({route.patient_id for route in patient_routes}),
        routes=len(patient_routes),
        events=sum(len(route.events) for route in patient_routes),
        dependency_arcs=sum(
            len(event.dependencies)
            for route in patient_routes
            for event in route.events
        ),
        root_events=sum(len(route.graph.root_events) for route in patient_routes),
        terminal_events=sum(
            len(route.graph.terminal_events) for route in patient_routes
        ),
        branch_events=sum(len(route.graph.branch_events) for route in patient_routes),
        join_events=sum(len(route.graph.join_events) for route in patient_routes),
        max_route_depth=max(
            (route.graph.max_depth for route in patient_routes),
            default=0,
        ),
    )
    return RoutePreprocessingResult(
        patient_routes=patient_routes,
        pathway_templates=templates,
        diagnostics=diagnostics,
    )
