from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from appointment_scheduling.preprocessing import preprocess_supply
from appointment_scheduling.research import run_experiment_case
from appointment_scheduling.routes import preprocess_routes
from appointment_scheduling.routes import (
    PathwayEventTemplate,
    PathwayTemplate,
    ResourceMode,
)
from appointment_scheduling.schedulers import run_sequential_scheduler
from appointment_scheduling.scheduling import build_scheduling_state


DEMO_DIR = Path(__file__).resolve().parents[1] / "data" / "demo"


@pytest.fixture
def demo_scheduling_components():
    route_rows = pd.read_csv(DEMO_DIR / "routes.csv")
    supply = pd.read_csv(DEMO_DIR / "supply.csv")
    blocks = pd.read_csv(DEMO_DIR / "blocks.csv")
    mapping = pd.read_csv(DEMO_DIR / "resource_mapping.csv")
    routes = preprocess_routes(route_rows)
    availability = preprocess_supply(supply, blocks, mapping).availability
    starts = {patient_id: date(2035, 1, 1) for patient_id in routes.routes_by_patient}
    return route_rows, routes, availability, starts


@pytest.fixture
def canonical_state(demo_scheduling_components):
    _, routes, availability, starts = demo_scheduling_components
    return build_scheduling_state(routes, availability, starts)


@pytest.fixture
def canonical_sequential_result(canonical_state):
    return run_sequential_scheduler(canonical_state)


@pytest.fixture
def canonical_research_case(demo_scheduling_components):
    _, routes, availability, starts = demo_scheduling_components

    def factory():
        return build_scheduling_state(routes, availability, starts)

    return run_experiment_case("synthetic-seed-42", factory)


@pytest.fixture
def tiny_milp_state(demo_scheduling_components):
    """Two-event chain whose unique all-internal outcome has one tardy day."""

    _, _, demo_availability, _ = demo_scheduling_components
    rows = []
    for number, (event_type, day) in enumerate((("EVENT-Z1", 1), ("EVENT-Z2", 4)), 1):
        row = demo_availability.iloc[[0]].copy()
        row.loc[:, "block_id"] = f"SUPPLY-BLOCK-90{number}"
        row.loc[:, "schedule_key"] = f"SCHEDULE-DEMO-90{number}"
        row.loc[:, "date"] = pd.Timestamp(2035, 1, day)
        row.loc[:, "event_type"] = event_type
        row.loc[:, "base_capacity"] = 1
        row.loc[:, "overbooking_capacity"] = 0
        row.loc[:, "blocked_capacity"] = 0
        row.loc[:, "standard_available_capacity"] = 1
        row.loc[:, "total_available_capacity"] = 1
        row.loc[:, "used_capacity"] = 0
        row.loc[:, "remaining_capacity"] = 1
        rows.append(row)
    availability = pd.concat(rows, ignore_index=True)
    route_rows = pd.DataFrame(
        [
            {
                "patient_id": "PAT-901",
                "pathway_id": "PATHWAY-Z",
                "event_number": event_number,
                "event_id": event_type,
                "agenda_id": "AGENDA-DEMO-01",
                "event_type": event_type,
                "min_spacing_days": min_spacing,
                "preferred_max_spacing_days": preferred_max,
                "dependencies": dependencies,
                "clinician_id": "CLINICIAN-01",
                "service_id": "SERVICE-A",
                "section_id": "SECTION-A1",
                "modality": "IN_PERSON",
                "resource_mode": "COMPATIBLE_SET",
                "overbooking_allowed": False,
            }
            for event_number, event_type, min_spacing, preferred_max, dependencies in (
                (1, "EVENT-Z1", 0, 0, "[]"),
                (2, "EVENT-Z2", 2, 2, "[1]"),
            )
        ]
    )
    template = PathwayTemplate(
        "PATHWAY-Z",
        (
            PathwayEventTemplate(1, "EVENT-Z1", "EVENT-Z1", (), 0, 0, ResourceMode.COMPATIBLE_SET),
            PathwayEventTemplate(2, "EVENT-Z2", "EVENT-Z2", (1,), 2, 2, ResourceMode.COMPATIBLE_SET),
        ),
    )
    routes = preprocess_routes(route_rows, (template,))
    return build_scheduling_state(
        routes,
        availability,
        {"PAT-901": date(2035, 1, 1)},
    )


@pytest.fixture
def milp_state_factory(demo_scheduling_components):
    """Create compact artificial states for analytical MILP fixtures."""

    _, _, demo_availability, _ = demo_scheduling_components

    def factory(events, opportunities, *, patients=1):
        template = PathwayTemplate(
            "PATHWAY-Z",
            tuple(
                PathwayEventTemplate(
                    number,
                    event_type,
                    event_type,
                    tuple(dependencies),
                    minimum,
                    preferred,
                    ResourceMode.COMPATIBLE_SET,
                )
                for number, event_type, dependencies, minimum, preferred in events
            ),
        )
        route_rows = []
        for patient_number in range(1, patients + 1):
            patient_id = f"PAT-{920 + patient_number:03d}"
            for number, event_type, dependencies, minimum, preferred in events:
                route_rows.append(
                    {
                        "patient_id": patient_id,
                        "pathway_id": "PATHWAY-Z",
                        "event_number": number,
                        "event_id": event_type,
                        "agenda_id": "AGENDA-DEMO-01",
                        "event_type": event_type,
                        "min_spacing_days": minimum,
                        "preferred_max_spacing_days": preferred,
                        "dependencies": str(list(dependencies)),
                        "clinician_id": "CLINICIAN-01",
                        "service_id": "SERVICE-A",
                        "section_id": "SECTION-A1",
                        "modality": "IN_PERSON",
                        "resource_mode": "COMPATIBLE_SET",
                        "overbooking_allowed": False,
                    }
                )
        routes = preprocess_routes(pd.DataFrame(route_rows), (template,))
        availability_rows = []
        for index, (event_type, day, standard, total) in enumerate(opportunities, 1):
            row = demo_availability.iloc[[0]].copy()
            row.loc[:, "block_id"] = f"SUPPLY-BLOCK-{920 + index:03d}"
            row.loc[:, "schedule_key"] = f"SCHEDULE-DEMO-{920 + index:03d}"
            row.loc[:, "date"] = pd.Timestamp(2035, 1, day)
            row.loc[:, "event_type"] = event_type
            row.loc[:, "base_capacity"] = standard
            row.loc[:, "overbooking_capacity"] = total - standard
            row.loc[:, "blocked_capacity"] = 0
            row.loc[:, "standard_available_capacity"] = standard
            row.loc[:, "total_available_capacity"] = total
            row.loc[:, "used_capacity"] = 0
            row.loc[:, "remaining_capacity"] = total
            availability_rows.append(row)
        availability = pd.concat(availability_rows, ignore_index=True)
        starts = {
            patient_id: date(2035, 1, 1) for patient_id in routes.routes_by_patient
        }
        return build_scheduling_state(routes, availability, starts)

    return factory
