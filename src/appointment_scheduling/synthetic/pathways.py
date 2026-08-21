"""Artificial event graphs with no clinical meaning."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PathwayEvent:
    """One event in an explicitly fictional scheduling pathway."""

    number: int
    event_id: str
    dependencies: tuple[int, ...]
    min_spacing_days: int
    preferred_max_spacing_days: int
    clinician_id: str
    service_id: str
    section_id: str
    agenda_id: str
    modality: str
    resource_mode: str


PATHWAYS: dict[str, tuple[PathwayEvent, ...]] = {
    "PATHWAY-A": (
        PathwayEvent(1, "EVENT-A1", (), 0, 2, "CLINICIAN-01", "SERVICE-A", "SECTION-A1", "AGENDA-DEMO-01", "IN_PERSON", "COMPATIBLE_SET"),
        PathwayEvent(2, "EVENT-A2", (1,), 2, 5, "CLINICIAN-01", "SERVICE-A", "SECTION-A1", "AGENDA-DEMO-01", "IN_PERSON", "COMPATIBLE_SET"),
        PathwayEvent(3, "EVENT-A3", (1,), 1, 4, "CLINICIAN-03", "SERVICE-A", "SECTION-A2", "AGENDA-DEMO-03", "REMOTE", "FIXED"),
        PathwayEvent(4, "EVENT-A4", (2,), 3, 7, "CLINICIAN-01", "SERVICE-A", "SECTION-A1", "AGENDA-DEMO-01", "IN_PERSON", "COMPATIBLE_SET"),
        PathwayEvent(5, "EVENT-A5", (2, 3), 2, 6, "CLINICIAN-03", "SERVICE-A", "SECTION-A2", "AGENDA-DEMO-03", "REMOTE", "FIXED"),
    ),
    "PATHWAY-B": (
        PathwayEvent(1, "EVENT-B1", (), 0, 1, "CLINICIAN-04", "SERVICE-B", "SECTION-B1", "AGENDA-DEMO-04", "IN_PERSON", "COMPATIBLE_SET"),
        PathwayEvent(2, "EVENT-B2", (1,), 1, 3, "CLINICIAN-04", "SERVICE-B", "SECTION-B1", "AGENDA-DEMO-04", "IN_PERSON", "COMPATIBLE_SET"),
        PathwayEvent(3, "EVENT-B3", (2,), 4, 8, "CLINICIAN-04", "SERVICE-B", "SECTION-B1", "AGENDA-DEMO-04", "REMOTE", "COMPATIBLE_SET"),
        PathwayEvent(4, "EVENT-B4", (3,), 2, 5, "CLINICIAN-04", "SERVICE-B", "SECTION-B1", "AGENDA-DEMO-04", "IN_PERSON", "COMPATIBLE_SET"),
    ),
    "PATHWAY-C": (
        PathwayEvent(1, "EVENT-C1", (), 0, 3, "CLINICIAN-06", "SERVICE-C", "SECTION-C1", "AGENDA-DEMO-06", "IN_PERSON", "FIXED"),
        PathwayEvent(2, "EVENT-C2", (1,), 3, 6, "CLINICIAN-06", "SERVICE-C", "SECTION-C1", "AGENDA-DEMO-06", "IN_PERSON", "FIXED"),
        PathwayEvent(3, "EVENT-C3", (2,), 2, 5, "CLINICIAN-07", "SERVICE-C", "SECTION-C2", "AGENDA-DEMO-07", "REMOTE", "FIXED"),
        PathwayEvent(4, "EVENT-C4", (2,), 5, 9, "CLINICIAN-06", "SERVICE-C", "SECTION-C1", "AGENDA-DEMO-06", "IN_PERSON", "FIXED"),
        PathwayEvent(5, "EVENT-C5", (3, 4), 1, 4, "CLINICIAN-07", "SERVICE-C", "SECTION-C2", "AGENDA-DEMO-07", "REMOTE", "FIXED"),
        PathwayEvent(6, "EVENT-C6", (5,), 31, 35, "CLINICIAN-06", "SERVICE-C", "SECTION-C1", "AGENDA-DEMO-06", "IN_PERSON", "FIXED"),
    ),
}


def pathway_sizes() -> dict[str, int]:
    """Return the number of events in each artificial pathway."""

    return {pathway_id: len(events) for pathway_id, events in PATHWAYS.items()}
