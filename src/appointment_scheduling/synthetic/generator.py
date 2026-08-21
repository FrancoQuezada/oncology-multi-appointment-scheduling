"""Generate deterministic, artificial scheduling datasets."""

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from appointment_scheduling.config import (
    DATASET_FILENAMES,
    DEFAULT_SEED,
    DEMO_END_DATE,
    DEMO_START_DATE,
)
from appointment_scheduling.synthetic.pathways import PATHWAYS, PathwayEvent
from appointment_scheduling.synthetic.schemas import REQUIRED_COLUMNS

DatasetCollection = dict[str, pd.DataFrame]


_MAPPING_SPECS = (
    ("MAP-A1", "CLINICIAN-01", "SECTION-A1", "SERVICE-A", "CENTER-01", "AGENDA-DEMO-01"),
    ("MAP-A2", "CLINICIAN-02", "SECTION-A1", "SERVICE-A", "CENTER-01", "AGENDA-DEMO-02"),
    ("MAP-A3", "CLINICIAN-03", "SECTION-A2", "SERVICE-A", "CENTER-01", "AGENDA-DEMO-03"),
    ("MAP-B1", "CLINICIAN-04", "SECTION-B1", "SERVICE-B", "CENTER-01", "AGENDA-DEMO-04"),
    ("MAP-B2", "CLINICIAN-05", "SECTION-B1", "SERVICE-B", "CENTER-01", "AGENDA-DEMO-05"),
    ("MAP-C1", "CLINICIAN-06", "SECTION-C1", "SERVICE-C", "CENTER-02", "AGENDA-DEMO-06"),
    ("MAP-C2", "CLINICIAN-07", "SECTION-C2", "SERVICE-C", "CENTER-02", "AGENDA-DEMO-07"),
    ("MAP-D1", "CLINICIAN-08", "SECTION-D1", "SERVICE-D", "CENTER-02", "AGENDA-DEMO-08"),
)

_SUPPORTED_EVENTS = {
    "MAP-A1": ("EVENT-A1", "EVENT-A2", "EVENT-A4"),
    "MAP-A2": ("EVENT-A1", "EVENT-A2", "EVENT-A4"),
    "MAP-A3": ("EVENT-A3", "EVENT-A5"),
    "MAP-B1": ("EVENT-B1", "EVENT-B2", "EVENT-B3", "EVENT-B4"),
    "MAP-B2": ("EVENT-B1", "EVENT-B2", "EVENT-B3", "EVENT-B4"),
    "MAP-C1": ("EVENT-C1", "EVENT-C2", "EVENT-C4", "EVENT-C6"),
    "MAP-C2": ("EVENT-C3", "EVENT-C5"),
    "MAP-D1": ("EVENT-D1", "EVENT-D2"),
}


def _resource_mapping() -> pd.DataFrame:
    return pd.DataFrame(_MAPPING_SPECS, columns=REQUIRED_COLUMNS["resource_mapping"])


def _event_lookup() -> dict[str, PathwayEvent]:
    return {
        event.event_id: event
        for pathway_events in PATHWAYS.values()
        for event in pathway_events
    }


def _generate_demand(rng: np.random.Generator) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    patient_pathways = (
        "PATHWAY-A",
        "PATHWAY-B",
        "PATHWAY-C",
        "PATHWAY-A",
        "PATHWAY-B",
        "PATHWAY-C",
        "PATHWAY-A",
        "PATHWAY-B",
        "PATHWAY-C",
        "PATHWAY-A",
    )
    statuses = np.array(["COMPLETED", "SCHEDULED", "CANCELLED"])
    care_types = np.array(["STANDARD", "FOLLOW_UP"])

    for patient_number, pathway_id in enumerate(patient_pathways, start=1):
        patient_id = f"PAT-{patient_number:03d}"
        day_offset = int(rng.integers(0, 3))
        for event in PATHWAYS[pathway_id]:
            if event.number > 1:
                day_offset += int(rng.integers(1, 5))
            day_offset = min(day_offset, (DEMO_END_DATE - DEMO_START_DATE).days)
            appointment_date = DEMO_START_DATE + timedelta(days=day_offset)
            lead_days = int(rng.integers(0, 4))
            booking_date = max(
                DEMO_START_DATE,
                appointment_date - timedelta(days=lead_days),
            )
            rows.append(
                {
                    "patient_id": patient_id,
                    "appointment_status": str(rng.choice(statuses, p=[0.65, 0.25, 0.10])),
                    "event_type": event.event_id,
                    "appointment_date": appointment_date.isoformat(),
                    "booking_date": booking_date.isoformat(),
                    "care_type": str(rng.choice(care_types)),
                    "agenda_id": event.agenda_id,
                    "clinician_id": event.clinician_id,
                    "service_id": event.service_id,
                    "section_id": event.section_id,
                }
            )
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS["demand"])


def _generate_supply(
    rng: np.random.Generator,
    mapping: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    horizon_days = (DEMO_END_DATE - DEMO_START_DATE).days + 1
    modality_by_event = {
        event.event_id: event.modality
        for events in PATHWAYS.values()
        for event in events
    }

    for _, resource in mapping.iterrows():
        mapping_key = resource["resource_mapping_key"]
        supported = _SUPPORTED_EVENTS[mapping_key]
        dates = np.sort(rng.choice(horizon_days, size=10, replace=False))
        offset = int(rng.integers(0, len(supported)))
        for local_index, day_offset in enumerate(dates):
            event_type = supported[(local_index + offset) % len(supported)]
            row_number = len(rows) + 1
            rows.append(
                {
                    "block_id": f"SUPPLY-BLOCK-{row_number:03d}",
                    "clinician_id": resource["clinician_id"],
                    "date": (DEMO_START_DATE + timedelta(days=int(day_offset))).isoformat(),
                    "active": True,
                    "base_capacity": int(rng.integers(1, 5)),
                    "overbooking_capacity": int(rng.integers(0, 3)),
                    "resource_mapping_key": mapping_key,
                    "agenda_id": resource["agenda_id"],
                    "schedule_key": f"SCHEDULE-DEMO-{row_number:03d}",
                    "modality": modality_by_event.get(event_type, "IN_PERSON"),
                    "event_type": event_type,
                }
            )

    supply = pd.DataFrame(rows, columns=REQUIRED_COLUMNS["supply"])

    def engineer(mapping_key: str, event_type: str, **values: object) -> int:
        index = supply.index[
            (supply["resource_mapping_key"] == mapping_key)
            & (supply["event_type"] == event_type)
        ][0]
        for column, value in values.items():
            supply.at[index, column] = value
        return int(index)

    # These fixed rows guarantee edge cases while all remaining rows vary by seed.
    engineer("MAP-A1", "EVENT-A1", date="2035-01-01", base_capacity=3, overbooking_capacity=0)
    engineer("MAP-A1", "EVENT-A2", date="2035-01-02", base_capacity=1, overbooking_capacity=0)
    engineer("MAP-A2", "EVENT-A2", date="2035-01-03", base_capacity=2, overbooking_capacity=2)
    engineer("MAP-B1", "EVENT-B1", date="2035-01-04", base_capacity=4, overbooking_capacity=0)
    engineer("MAP-B2", "EVENT-B2", date="2035-01-05", base_capacity=3, overbooking_capacity=0)
    supply.at[supply.index[-1], "date"] = DEMO_END_DATE.isoformat()

    return supply.sort_values(["date", "schedule_key"], ignore_index=True)


def _find_supply_index(
    supply: pd.DataFrame,
    mapping_key: str,
    event_type: str,
) -> int:
    return int(
        supply.index[
            (supply["resource_mapping_key"] == mapping_key)
            & (supply["event_type"] == event_type)
        ][0]
    )


def _generate_blocks(supply: pd.DataFrame) -> pd.DataFrame:
    partial_index = _find_supply_index(supply, "MAP-B1", "EVENT-B1")
    full_index = _find_supply_index(supply, "MAP-B2", "EVENT-B2")
    selected = [
        partial_index,
        full_index,
        _find_supply_index(supply, "MAP-A1", "EVENT-A1"),
        _find_supply_index(supply, "MAP-A2", "EVENT-A2"),
        _find_supply_index(supply, "MAP-A3", "EVENT-A3"),
        _find_supply_index(supply, "MAP-C1", "EVENT-C1"),
        _find_supply_index(supply, "MAP-C2", "EVENT-C3"),
        _find_supply_index(supply, "MAP-D1", "EVENT-D1"),
    ]
    rows = []
    for position, supply_index in enumerate(selected):
        source = supply.loc[supply_index]
        total = int(source["base_capacity"] + source["overbooking_capacity"])
        if supply_index == partial_index:
            blocked = 2
        elif supply_index == full_index:
            blocked = total
        else:
            blocked = 1 if total > 1 else total
        rows.append(
            {
                "schedule_key": source["schedule_key"],
                "agenda_id": source["agenda_id"],
                "date": source["date"],
                "blocked_capacity": blocked,
                "block_reason_code": f"BLOCK-{chr(65 + position % 3)}",
            }
        )
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS["blocks"])


def _generate_routes() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    patient_pathways = {
        "PAT-001": "PATHWAY-A",
        "PAT-002": "PATHWAY-B",
        "PAT-003": "PATHWAY-C",
        "PAT-004": "PATHWAY-A",
    }
    mapping_d = {
        "clinician_id": "CLINICIAN-08",
        "service_id": "SERVICE-D",
        "section_id": "SECTION-D1",
        "agenda_id": "AGENDA-DEMO-08",
        "modality": "IN_PERSON",
    }

    for patient_id, pathway_id in patient_pathways.items():
        for event in PATHWAYS[pathway_id]:
            resource = {
                "clinician_id": event.clinician_id,
                "service_id": event.service_id,
                "section_id": event.section_id,
                "agenda_id": event.agenda_id,
                "modality": event.modality,
            }
            # This fictional request has a valid mapping but no compatible slot.
            if patient_id == "PAT-004" and event.event_id == "EVENT-A5":
                resource = mapping_d
            rows.append(
                {
                    "patient_id": patient_id,
                    "pathway_id": pathway_id,
                    "event_number": event.number,
                    "event_id": event.event_id,
                    "agenda_id": resource["agenda_id"],
                    "event_type": event.event_id,
                    "min_spacing_days": event.min_spacing_days,
                    "preferred_max_spacing_days": event.preferred_max_spacing_days,
                    "dependencies": json.dumps(list(event.dependencies), separators=(",", ":")),
                    "clinician_id": resource["clinician_id"],
                    "service_id": resource["service_id"],
                    "section_id": resource["section_id"],
                    "modality": resource["modality"],
                    "resource_mode": event.resource_mode,
                    "overbooking_allowed": event.number % 2 == 0,
                }
            )
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS["routes"])


def generate_demo_dataset(seed: int = DEFAULT_SEED) -> DatasetCollection:
    """Return five validated synthetic datasets generated from a local RNG.

    The data are artificial software fixtures. They have no clinical meaning and
    are not calibrated to any real organization, population, or schedule.
    """

    rng = np.random.default_rng(seed)
    resource_mapping = _resource_mapping()
    supply = _generate_supply(rng, resource_mapping)
    datasets = {
        "demand": _generate_demand(rng),
        "supply": supply,
        "blocks": _generate_blocks(supply),
        "resource_mapping": resource_mapping,
        "routes": _generate_routes(),
    }

    from appointment_scheduling.synthetic.validation import validate_demo_dataset

    validate_demo_dataset(datasets)
    return datasets


def write_demo_dataset(
    datasets: Mapping[str, pd.DataFrame],
    output_dir: Path,
) -> None:
    """Validate and write the canonical CSV files."""

    from appointment_scheduling.synthetic.validation import validate_demo_dataset

    validate_demo_dataset(datasets)
    output_dir.mkdir(parents=True, exist_ok=True)
    for dataset_name, filename in DATASET_FILENAMES.items():
        datasets[dataset_name].to_csv(output_dir / filename, index=False)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def main() -> None:
    """Command-line entry point for regenerating the public demo CSV files."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_project_root() / "data" / "demo",
    )
    args = parser.parse_args()
    datasets = generate_demo_dataset(seed=args.seed)
    write_demo_dataset(datasets, args.output_dir)
    print(f"Wrote {len(datasets)} validated synthetic datasets to {args.output_dir}")


if __name__ == "__main__":
    main()
