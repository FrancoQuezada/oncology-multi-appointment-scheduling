from pathlib import Path

import pandas as pd
import pytest

from appointment_scheduling.preprocessing import (
    SupplyValidationError,
    preprocess_supply,
)


DEMO_DIR = Path(__file__).resolve().parents[1] / "data" / "demo"


def _inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_csv(DEMO_DIR / "supply.csv"),
        pd.read_csv(DEMO_DIR / "blocks.csv"),
        pd.read_csv(DEMO_DIR / "resource_mapping.csv"),
    )


def test_engineered_partial_blockage_capacity() -> None:
    supply, blocks, mapping = _inputs()

    availability = preprocess_supply(supply, blocks, mapping).availability
    row = availability[
        (availability["base_capacity"] == 4)
        & (availability["overbooking_capacity"] == 0)
        & (availability["blocked_capacity"] == 2)
    ].iloc[0]

    assert row["standard_available_capacity"] == 2
    assert row["total_available_capacity"] == 2
    assert row["remaining_capacity"] == 2


def test_engineered_full_blockage_capacity() -> None:
    supply, blocks, mapping = _inputs()

    availability = preprocess_supply(supply, blocks, mapping).availability
    row = availability[
        (availability["base_capacity"] == 3)
        & (availability["overbooking_capacity"] == 0)
        & (availability["blocked_capacity"] == 3)
    ].iloc[0]

    assert row["standard_available_capacity"] == 0
    assert row["total_available_capacity"] == 0
    assert row["remaining_capacity"] == 0


def test_overbooking_remains_explicit() -> None:
    supply, blocks, mapping = _inputs()

    availability = preprocess_supply(supply, blocks, mapping).availability
    with_overbooking = availability[availability["overbooking_capacity"] > 0]

    assert not with_overbooking.empty
    assert (
        with_overbooking["total_available_capacity"]
        >= with_overbooking["standard_available_capacity"]
    ).all()
    assert (
        with_overbooking["total_available_capacity"]
        > with_overbooking["standard_available_capacity"]
    ).any()


@pytest.mark.parametrize("column", ["base_capacity", "overbooking_capacity"])
def test_negative_supply_capacity_is_rejected(column: str) -> None:
    supply, blocks, mapping = _inputs()
    supply.loc[0, column] = -1

    with pytest.raises(SupplyValidationError, match=rf"{column}.*non-negative"):
        preprocess_supply(supply, blocks, mapping)


def test_negative_blocked_capacity_is_rejected() -> None:
    supply, blocks, mapping = _inputs()
    blocks.loc[0, "blocked_capacity"] = -1

    with pytest.raises(SupplyValidationError, match="blocked_capacity.*non-negative"):
        preprocess_supply(supply, blocks, mapping)


def test_excess_blockage_is_rejected() -> None:
    supply, blocks, mapping = _inputs()
    key = blocks.loc[0, ["schedule_key", "agenda_id", "date"]]
    target = (
        (supply["schedule_key"] == key["schedule_key"])
        & (supply["agenda_id"] == key["agenda_id"])
        & (supply["date"] == key["date"])
    )
    total = int(
        supply.loc[target, "base_capacity"].iloc[0]
        + supply.loc[target, "overbooking_capacity"].iloc[0]
    )
    blocks.loc[0, "blocked_capacity"] = total + 1

    with pytest.raises(SupplyValidationError, match="exceeds total configured capacity"):
        preprocess_supply(supply, blocks, mapping)


def test_repeated_block_rows_are_aggregated() -> None:
    supply, blocks, mapping = _inputs()
    source = supply[supply["base_capacity"] >= 3].iloc[0]
    repeated = pd.DataFrame(
        [
            {
                "schedule_key": source["schedule_key"],
                "agenda_id": source["agenda_id"],
                "date": source["date"],
                "blocked_capacity": 1,
                "block_reason_code": "BLOCK-A",
            },
            {
                "schedule_key": source["schedule_key"],
                "agenda_id": source["agenda_id"],
                "date": source["date"],
                "blocked_capacity": 1,
                "block_reason_code": "BLOCK-B",
            },
        ]
    )

    result = preprocess_supply(supply, repeated, mapping)
    row = result.availability[
        result.availability["schedule_key"] == source["schedule_key"]
    ].iloc[0]

    assert row["blocked_capacity"] == 2
    assert result.diagnostics.input_block_rows == 2
    assert result.diagnostics.aggregated_block_keys == 1


def test_row_and_aggregate_capacity_invariants() -> None:
    supply, blocks, mapping = _inputs()

    result = preprocess_supply(supply, blocks, mapping)
    availability = result.availability

    assert (availability["standard_available_capacity"] >= 0).all()
    assert (availability["total_available_capacity"] >= 0).all()
    assert (availability["remaining_capacity"] >= 0).all()
    assert (
        availability["standard_available_capacity"]
        <= availability["total_available_capacity"]
    ).all()
    assert (
        availability["remaining_capacity"]
        <= availability["total_available_capacity"]
    ).all()
    assert (
        availability["used_capacity"]
        <= availability["total_available_capacity"]
    ).all()
    assert availability["used_capacity"].eq(0).all()
    assert availability["remaining_capacity"].eq(
        availability["total_available_capacity"]
    ).all()

    expected_total = (
        availability["base_capacity"].sum()
        + availability["overbooking_capacity"].sum()
        - availability["blocked_capacity"].sum()
    )
    assert availability["total_available_capacity"].sum() == expected_total
    assert result.diagnostics.total_available_capacity == expected_total
