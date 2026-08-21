from pathlib import Path

import pandas as pd

from appointment_scheduling.config import DATASET_FILENAMES
from appointment_scheduling.synthetic.generator import (
    generate_demo_dataset,
    write_demo_dataset,
)


def test_same_seed_produces_identical_datasets() -> None:
    first = generate_demo_dataset(seed=42)
    second = generate_demo_dataset(seed=42)

    for name in first:
        pd.testing.assert_frame_equal(first[name], second[name])


def test_different_seed_changes_generated_components() -> None:
    first = generate_demo_dataset(seed=42)
    second = generate_demo_dataset(seed=314)

    assert any(not first[name].equals(second[name]) for name in first)


def test_generator_has_expected_demo_scale() -> None:
    datasets = generate_demo_dataset()

    assert datasets["demand"]["patient_id"].nunique() == 10
    assert len(datasets["demand"]) == 50
    assert len(datasets["supply"]) == 80
    assert len(datasets["blocks"]) == 8
    assert len(datasets["resource_mapping"]) == 8
    assert len(datasets["routes"]) == 20


def test_all_csv_files_are_written_and_readable(tmp_path: Path) -> None:
    datasets = generate_demo_dataset()
    write_demo_dataset(datasets, tmp_path)

    assert {path.name for path in tmp_path.iterdir()} == set(DATASET_FILENAMES.values())
    for filename in DATASET_FILENAMES.values():
        frame = pd.read_csv(tmp_path / filename)
        assert not frame.empty
