from pathlib import Path

import pandas as pd

from appointment_scheduling.preprocessing import (
    AVAILABILITY_COLUMNS,
    preprocess_supply,
)


DEMO_DIR = Path(__file__).resolve().parents[1] / "data" / "demo"


def _inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_csv(DEMO_DIR / "supply.csv"),
        pd.read_csv(DEMO_DIR / "blocks.csv"),
        pd.read_csv(DEMO_DIR / "resource_mapping.csv"),
    )


def test_canonical_supply_preprocesses_successfully() -> None:
    supply, blocks, mapping = _inputs()

    result = preprocess_supply(supply, blocks, mapping)

    assert not result.availability.empty
    assert tuple(result.availability.columns) == AVAILABILITY_COLUMNS
    assert result.diagnostics.input_supply_rows == len(supply)
    assert result.diagnostics.output_availability_rows == len(supply)


def test_mapping_join_preserves_active_supply_rows() -> None:
    supply, blocks, mapping = _inputs()

    result = preprocess_supply(supply, blocks, mapping)

    assert len(result.availability) == int(supply["active"].sum())
    assert result.diagnostics.mapped_rows == len(supply)
    assert result.diagnostics.unmapped_rows == 0


def test_output_resource_metadata_is_referentially_valid() -> None:
    supply, blocks, mapping = _inputs()

    availability = preprocess_supply(supply, blocks, mapping).availability
    expected = mapping.rename(
        columns={
            "clinician_id": "expected_clinician_id",
            "agenda_id": "expected_agenda_id",
        }
    )
    checked = availability.merge(
        expected,
        on="resource_mapping_key",
        validate="many_to_one",
    )

    assert checked["clinician_id"].eq(checked["expected_clinician_id"]).all()
    assert checked["agenda_id"].eq(checked["expected_agenda_id"]).all()
    assert checked["service_id_x"].eq(checked["service_id_y"]).all()
    assert checked["section_id_x"].eq(checked["section_id_y"]).all()
    assert checked["center_id_x"].eq(checked["center_id_y"]).all()


def test_supply_without_block_record_receives_zero_blockage() -> None:
    supply, blocks, mapping = _inputs()

    availability = preprocess_supply(supply, blocks, mapping).availability
    blocked_schedules = set(blocks["schedule_key"])
    unblocked = availability[~availability["schedule_key"].isin(blocked_schedules)]

    assert not unblocked.empty
    assert unblocked["blocked_capacity"].eq(0).all()


def test_inactive_supply_is_removed_and_reported() -> None:
    supply, blocks, mapping = _inputs()
    removed_schedule = supply.loc[0, "schedule_key"]
    supply.loc[0, "active"] = False

    result = preprocess_supply(supply, blocks, mapping)

    assert removed_schedule not in set(result.availability["schedule_key"])
    assert len(result.availability) == len(supply) - 1
    assert result.diagnostics.inactive_rows_removed == 1
    assert result.diagnostics.active_supply_rows == len(supply) - 1


def test_preprocessing_does_not_mutate_inputs() -> None:
    supply, blocks, mapping = _inputs()
    supply_before = supply.copy(deep=True)
    blocks_before = blocks.copy(deep=True)
    mapping_before = mapping.copy(deep=True)

    preprocess_supply(supply, blocks, mapping)

    pd.testing.assert_frame_equal(supply, supply_before)
    pd.testing.assert_frame_equal(blocks, blocks_before)
    pd.testing.assert_frame_equal(mapping, mapping_before)


def test_preprocessing_is_deterministic() -> None:
    supply, blocks, mapping = _inputs()

    first = preprocess_supply(supply, blocks, mapping)
    second = preprocess_supply(supply, blocks, mapping)

    pd.testing.assert_frame_equal(first.availability, second.availability)
    assert first.diagnostics == second.diagnostics
