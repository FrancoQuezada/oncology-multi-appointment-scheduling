import pytest

from appointment_scheduling.synthetic.generator import generate_demo_dataset
from appointment_scheduling.synthetic.validation import (
    ValidationError,
    validate_demo_dataset,
)


def test_generated_dataset_passes_validation() -> None:
    validate_demo_dataset(generate_demo_dataset())


def test_missing_required_column_is_rejected() -> None:
    datasets = generate_demo_dataset()
    datasets["demand"] = datasets["demand"].drop(columns="patient_id")

    with pytest.raises(ValidationError, match="missing required columns"):
        validate_demo_dataset(datasets)


def test_invalid_patient_identifier_is_rejected() -> None:
    datasets = generate_demo_dataset()
    datasets["demand"].loc[0, "patient_id"] = "PERSON-1"

    with pytest.raises(ValidationError, match="non-public identifier"):
        validate_demo_dataset(datasets)


def test_national_id_pattern_is_rejected() -> None:
    datasets = generate_demo_dataset()
    unsafe_pattern = ".".join(("12", "345", "678")) + "-X"
    datasets["demand"].loc[0, "care_type"] = unsafe_pattern

    with pytest.raises(ValidationError, match="national-ID-like"):
        validate_demo_dataset(datasets)


def test_unknown_route_resource_is_rejected() -> None:
    datasets = generate_demo_dataset()
    datasets["routes"].loc[0, "clinician_id"] = "CLINICIAN-99"

    with pytest.raises(ValidationError, match="unknown clinician/service/section/agenda"):
        validate_demo_dataset(datasets)


def test_unknown_block_reference_is_rejected() -> None:
    datasets = generate_demo_dataset()
    datasets["blocks"].loc[0, "schedule_key"] = "SCHEDULE-DEMO-999"

    with pytest.raises(ValidationError, match="unknown schedule/agenda/date"):
        validate_demo_dataset(datasets)


def test_missing_dependency_is_rejected() -> None:
    datasets = generate_demo_dataset()
    target = (datasets["routes"]["patient_id"] == "PAT-002") & (
        datasets["routes"]["event_number"] == 2
    )
    datasets["routes"].loc[target, "dependencies"] = "[99]"

    with pytest.raises(ValidationError, match="missing dependency"):
        validate_demo_dataset(datasets)


def test_dependency_cycle_is_rejected() -> None:
    datasets = generate_demo_dataset()
    target = (datasets["routes"]["patient_id"] == "PAT-002") & (
        datasets["routes"]["event_number"] == 1
    )
    datasets["routes"].loc[target, "dependencies"] = "[4]"

    with pytest.raises(ValidationError, match="dependency cycle"):
        validate_demo_dataset(datasets)


def test_invalid_timing_window_is_rejected() -> None:
    datasets = generate_demo_dataset()
    datasets["routes"].loc[0, "preferred_max_spacing_days"] = -1

    with pytest.raises(ValidationError, match="Preferred maximum spacing"):
        validate_demo_dataset(datasets)


def test_negative_capacity_is_rejected() -> None:
    datasets = generate_demo_dataset()
    datasets["supply"].loc[0, "base_capacity"] = -1

    with pytest.raises(ValidationError, match="base_capacity must be non-negative"):
        validate_demo_dataset(datasets)


def test_out_of_horizon_date_is_rejected() -> None:
    datasets = generate_demo_dataset()
    datasets["supply"].loc[0, "date"] = "2040-01-01"

    with pytest.raises(ValidationError, match="outside the demo horizon"):
        validate_demo_dataset(datasets)
