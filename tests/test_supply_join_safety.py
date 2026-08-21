from pathlib import Path

import pandas as pd
import pytest

from appointment_scheduling.preprocessing import (
    DuplicateSupplyError,
    MappingCardinalityError,
    OrphanBlockError,
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


def test_identical_duplicate_mapping_is_rejected() -> None:
    supply, blocks, mapping = _inputs()
    duplicated = pd.concat([mapping, mapping.iloc[[0]]], ignore_index=True)
    duplicate_key = mapping.loc[0, "resource_mapping_key"]

    with pytest.raises(
        MappingCardinalityError,
        match=rf"{duplicate_key!s}.*2 mapping rows",
    ):
        preprocess_supply(supply, blocks, duplicated)


def test_incompatible_duplicate_mapping_is_rejected() -> None:
    supply, blocks, mapping = _inputs()
    conflicting = mapping.iloc[[0]].copy()
    conflicting["service_id"] = "SERVICE-Z"
    ambiguous = pd.concat([mapping, conflicting], ignore_index=True)
    duplicate_key = mapping.loc[0, "resource_mapping_key"]

    with pytest.raises(
        MappingCardinalityError,
        match=rf"{duplicate_key!s}.*2 mapping rows",
    ):
        preprocess_supply(supply, blocks, ambiguous)


def test_orphan_block_is_rejected() -> None:
    supply, blocks, mapping = _inputs()
    blocks.loc[0, "schedule_key"] = "SCHEDULE-DEMO-999"

    with pytest.raises(OrphanBlockError, match="Orphan block key"):
        preprocess_supply(supply, blocks, mapping)


def test_exact_duplicate_supply_row_is_rejected() -> None:
    supply, blocks, mapping = _inputs()
    duplicated = pd.concat([supply, supply.iloc[[0]]], ignore_index=True)

    with pytest.raises(DuplicateSupplyError, match="Duplicate supply block_id"):
        preprocess_supply(duplicated, blocks, mapping)


def test_semantic_duplicate_supply_opportunity_is_rejected() -> None:
    supply, blocks, mapping = _inputs()
    duplicate = supply.iloc[[0]].copy()
    duplicate["block_id"] = "SUPPLY-BLOCK-999"
    duplicated = pd.concat([supply, duplicate], ignore_index=True)

    with pytest.raises(DuplicateSupplyError, match="supply opportunity"):
        preprocess_supply(duplicated, blocks, mapping)


def test_block_ambiguous_supply_key_is_rejected() -> None:
    supply, blocks, mapping = _inputs()
    duplicate = supply.iloc[[0]].copy()
    duplicate["block_id"] = "SUPPLY-BLOCK-999"
    duplicate["event_type"] = "EVENT-Z9"
    duplicated = pd.concat([supply, duplicate], ignore_index=True)

    with pytest.raises(DuplicateSupplyError, match="block match key"):
        preprocess_supply(duplicated, blocks, mapping)


def test_unknown_mapping_key_is_rejected() -> None:
    supply, blocks, mapping = _inputs()
    supply.loc[0, "resource_mapping_key"] = "MAP-Z9"

    with pytest.raises(SupplyValidationError, match="unknown mapping key"):
        preprocess_supply(supply, blocks, mapping)


def test_supply_mapping_disagreement_is_rejected() -> None:
    supply, blocks, mapping = _inputs()
    supply.loc[0, "clinician_id"] = "CLINICIAN-99"

    with pytest.raises(SupplyValidationError, match="clinician disagrees"):
        preprocess_supply(supply, blocks, mapping)
