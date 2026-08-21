"""Domain-specific validation for supply preprocessing."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from appointment_scheduling.preprocessing.models import (
    AVAILABILITY_COLUMNS,
    BLOCK_MATCH_KEY,
    SUPPLY_OPPORTUNITY_KEY,
)
from appointment_scheduling.synthetic.schemas import (
    BLOCK_COLUMNS,
    RESOURCE_MAPPING_COLUMNS,
    SUPPLY_COLUMNS,
)


class SupplyValidationError(ValueError):
    """Base error for an invalid supply preprocessing input or result."""


class MappingCardinalityError(SupplyValidationError):
    """Raised when a mapping key cannot support a many-to-one join."""


class OrphanBlockError(SupplyValidationError):
    """Raised when a block key has no matching supply opportunity."""


class DuplicateSupplyError(SupplyValidationError):
    """Raised when supply contains duplicate or block-ambiguous rows."""


def _require_columns(
    frame: pd.DataFrame,
    required: Iterable[str],
    dataset_name: str,
) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise SupplyValidationError(
            f"{dataset_name} is missing required columns: {missing}"
        )
    null_columns = [column for column in required if frame[column].isna().any()]
    if null_columns:
        raise SupplyValidationError(
            f"{dataset_name} contains null required fields: {null_columns}"
        )


def _require_parseable_dates(
    frame: pd.DataFrame,
    column: str,
    dataset_name: str,
) -> None:
    if pd.to_datetime(frame[column], errors="coerce").isna().any():
        raise SupplyValidationError(f"{dataset_name}.{column} contains an invalid date")


def _require_nonnegative_integers(
    frame: pd.DataFrame,
    columns: Iterable[str],
    dataset_name: str,
) -> None:
    for column in columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any() or not np.isfinite(values).all():
            raise SupplyValidationError(
                f"{dataset_name}.{column} must contain finite integers"
            )
        if (values % 1 != 0).any():
            raise SupplyValidationError(f"{dataset_name}.{column} must contain integers")
        if (values < 0).any():
            raise SupplyValidationError(f"{dataset_name}.{column} must be non-negative")


def validate_supply_input(supply: pd.DataFrame) -> None:
    """Validate the canonical fields and primitive values in supply."""

    _require_columns(supply, SUPPLY_COLUMNS, "supply")
    _require_parseable_dates(supply, "date", "supply")
    _require_nonnegative_integers(
        supply,
        ("base_capacity", "overbooking_capacity"),
        "supply",
    )
    valid_active = supply["active"].map(
        lambda value: isinstance(value, (bool, np.bool_))
    )
    if not valid_active.all():
        raise SupplyValidationError("supply.active must contain booleans")


def validate_blocks_input(blocks: pd.DataFrame) -> None:
    """Validate block fields while allowing repeated block match keys."""

    _require_columns(blocks, BLOCK_COLUMNS, "blocks")
    _require_parseable_dates(blocks, "date", "blocks")
    _require_nonnegative_integers(blocks, ("blocked_capacity",), "blocks")


def validate_mapping_input(resource_mapping: pd.DataFrame) -> None:
    """Validate required resource-mapping fields."""

    _require_columns(
        resource_mapping,
        RESOURCE_MAPPING_COLUMNS,
        "resource_mapping",
    )


def validate_mapping_cardinality(resource_mapping: pd.DataFrame) -> None:
    """Require exactly one mapping row per resource mapping key."""

    counts = resource_mapping.groupby("resource_mapping_key", dropna=False).size()
    duplicates = counts[counts > 1]
    if not duplicates.empty:
        key = str(duplicates.index[0])
        count = int(duplicates.iloc[0])
        raise MappingCardinalityError(
            f"Ambiguous resource_mapping_key {key!r}: {count} mapping rows"
        )


def _duplicate_key_error(
    frame: pd.DataFrame,
    key: tuple[str, ...],
    description: str,
) -> DuplicateSupplyError | None:
    counts = frame.groupby(list(key), dropna=False).size()
    duplicates = counts[counts > 1]
    if duplicates.empty:
        return None
    first_key = duplicates.index[0]
    if not isinstance(first_key, tuple):
        first_key = (first_key,)
    rendered_key = ", ".join(
        f"{column}={value!r}" for column, value in zip(key, first_key)
    )
    return DuplicateSupplyError(
        f"Duplicate {description} ({rendered_key}): {int(duplicates.iloc[0])} rows"
    )


def validate_supply_uniqueness(supply: pd.DataFrame) -> None:
    """Reject duplicate opportunities and block-ambiguous supply rows."""

    if supply["block_id"].duplicated().any():
        block_id = str(supply.loc[supply["block_id"].duplicated(False), "block_id"].iloc[0])
        count = int((supply["block_id"] == block_id).sum())
        raise DuplicateSupplyError(
            f"Duplicate supply block_id {block_id!r}: {count} rows"
        )

    opportunity_error = _duplicate_key_error(
        supply,
        SUPPLY_OPPORTUNITY_KEY,
        "supply opportunity",
    )
    if opportunity_error:
        raise opportunity_error

    block_key_error = _duplicate_key_error(
        supply,
        BLOCK_MATCH_KEY,
        "block match key",
    )
    if block_key_error:
        raise block_key_error


def validate_orphan_blocks(supply: pd.DataFrame, blocks: pd.DataFrame) -> None:
    """Require every block match key to exist in supply."""

    supply_keys = set(
        supply[list(BLOCK_MATCH_KEY)].itertuples(index=False, name=None)
    )
    block_counts = blocks.groupby(list(BLOCK_MATCH_KEY), dropna=False).size()
    orphan_counts = [
        (key if isinstance(key, tuple) else (key,), int(count))
        for key, count in block_counts.items()
        if (key if isinstance(key, tuple) else (key,)) not in supply_keys
    ]
    if orphan_counts:
        key, count = orphan_counts[0]
        rendered_key = ", ".join(
            f"{column}={value!r}" for column, value in zip(BLOCK_MATCH_KEY, key)
        )
        raise OrphanBlockError(
            f"Orphan block key ({rendered_key}): {count} block rows"
        )


def validate_availability_output(
    availability: pd.DataFrame,
    expected_rows: int,
) -> None:
    """Validate final row count, schema, uniqueness, and capacity invariants."""

    _require_columns(availability, AVAILABILITY_COLUMNS, "availability")
    if len(availability) != expected_rows:
        raise MappingCardinalityError(
            "Availability row count differs from active supply row count: "
            f"expected {expected_rows}, got {len(availability)}"
        )
    duplicate_error = _duplicate_key_error(
        availability,
        SUPPLY_OPPORTUNITY_KEY,
        "availability opportunity",
    )
    if duplicate_error:
        raise duplicate_error

    capacity_columns = (
        "base_capacity",
        "overbooking_capacity",
        "blocked_capacity",
        "standard_available_capacity",
        "total_available_capacity",
        "used_capacity",
        "remaining_capacity",
    )
    _require_nonnegative_integers(availability, capacity_columns, "availability")
    if not availability["active"].eq(True).all():
        raise SupplyValidationError("Availability must contain only active supply")
    if not availability["used_capacity"].eq(0).all():
        raise SupplyValidationError("Preprocessed used capacity must be zero")
    if not availability["remaining_capacity"].eq(
        availability["total_available_capacity"]
    ).all():
        raise SupplyValidationError(
            "Initial remaining capacity must equal total available capacity"
        )
    if (
        availability["standard_available_capacity"]
        > availability["total_available_capacity"]
    ).any():
        raise SupplyValidationError(
            "Standard available capacity cannot exceed total available capacity"
        )
    if (
        availability["used_capacity"] > availability["total_available_capacity"]
    ).any():
        raise SupplyValidationError("Used capacity cannot exceed total capacity")

    expected_total = int(
        availability["base_capacity"].sum()
        + availability["overbooking_capacity"].sum()
        - availability["blocked_capacity"].sum()
    )
    actual_total = int(availability["total_available_capacity"].sum())
    if actual_total != expected_total:
        raise SupplyValidationError(
            "Aggregate available capacity does not match input capacity accounting"
        )
