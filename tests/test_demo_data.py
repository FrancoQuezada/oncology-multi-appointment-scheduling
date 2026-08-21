import re
from pathlib import Path

import pandas as pd

from appointment_scheduling.config import DATASET_FILENAMES
from appointment_scheduling.synthetic.pathways import pathway_sizes
from appointment_scheduling.synthetic.validation import (
    analyze_engineered_cases,
    validate_demo_dataset,
)


DEMO_DIR = Path(__file__).resolve().parents[1] / "data" / "demo"


def _load_demo_data() -> dict[str, pd.DataFrame]:
    return {
        name: pd.read_csv(DEMO_DIR / filename)
        for name, filename in DATASET_FILENAMES.items()
    }


def test_committed_demo_data_passes_validation() -> None:
    validate_demo_dataset(_load_demo_data())


def test_three_artificial_pathways_have_expected_sizes() -> None:
    assert pathway_sizes() == {"PATHWAY-A": 5, "PATHWAY-B": 4, "PATHWAY-C": 6}


def test_capacity_and_dependency_cases_are_present() -> None:
    cases = analyze_engineered_cases(_load_demo_data())

    expected = {
        "normal_capacity",
        "scarce_capacity",
        "overbooking",
        "partial_blockage",
        "full_blockage",
        "multiple_clinicians",
        "multiple_services",
        "branching",
        "different_minimum_spacing",
        "preferred_windows",
    }
    assert all(cases[name] for name in expected)


def test_scheduling_edge_cases_are_present() -> None:
    cases = analyze_engineered_cases(_load_demo_data())

    assert cases["infeasible_event"]
    assert cases["infeasible_event_count"] == 1
    assert cases["horizon_overflow"]
    assert cases["alternative_resource"]


def test_identifiers_use_explicit_synthetic_formats() -> None:
    datasets = _load_demo_data()

    assert datasets["demand"]["patient_id"].str.fullmatch(r"PAT-\d{3}").all()
    for frame in datasets.values():
        if "clinician_id" in frame:
            assert frame["clinician_id"].str.fullmatch(r"CLINICIAN-\d{2}").all()
        text = "\n".join(frame.astype(str).to_numpy().ravel())
        assert not re.search(r"\b\d{1,2}(?:\.\d{3}){2}-[0-9A-Za-z]\b", text)


def test_demo_horizon_is_fixed_and_artificial() -> None:
    datasets = _load_demo_data()

    assert datasets["supply"]["date"].min() == "2035-01-01"
    assert datasets["supply"]["date"].max() == "2035-01-28"
