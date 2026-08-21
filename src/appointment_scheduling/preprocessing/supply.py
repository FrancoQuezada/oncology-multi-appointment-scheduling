"""Pure supply preprocessing for synthetic scheduling inputs."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
from pandas.errors import MergeError

from appointment_scheduling.preprocessing.models import (
    AVAILABILITY_COLUMNS,
    BLOCK_MATCH_KEY,
    SupplyPreprocessingDiagnostics,
    SupplyPreprocessingResult,
)
from appointment_scheduling.preprocessing.validation import (
    MappingCardinalityError,
    SupplyValidationError,
    validate_availability_output,
    validate_blocks_input,
    validate_mapping_cardinality,
    validate_mapping_input,
    validate_orphan_blocks,
    validate_supply_input,
    validate_supply_uniqueness,
)


def _strip_strings(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    for column in columns:
        frame[column] = frame[column].str.strip()


def _normalize_supply(supply: pd.DataFrame) -> pd.DataFrame:
    normalized = supply.copy(deep=True)
    _strip_strings(
        normalized,
        (
            "block_id",
            "clinician_id",
            "resource_mapping_key",
            "agenda_id",
            "schedule_key",
            "modality",
            "event_type",
        ),
    )
    normalized["date"] = pd.to_datetime(normalized["date"]).dt.normalize()
    normalized["base_capacity"] = normalized["base_capacity"].astype("int64")
    normalized["overbooking_capacity"] = normalized[
        "overbooking_capacity"
    ].astype("int64")
    normalized["active"] = normalized["active"].astype(bool)
    return normalized


def _normalize_blocks(blocks: pd.DataFrame) -> pd.DataFrame:
    normalized = blocks.copy(deep=True)
    _strip_strings(
        normalized,
        ("schedule_key", "agenda_id", "block_reason_code"),
    )
    normalized["date"] = pd.to_datetime(normalized["date"]).dt.normalize()
    normalized["blocked_capacity"] = normalized["blocked_capacity"].astype("int64")
    return normalized


def _normalize_mapping(resource_mapping: pd.DataFrame) -> pd.DataFrame:
    normalized = resource_mapping.copy(deep=True)
    _strip_strings(
        normalized,
        (
            "resource_mapping_key",
            "clinician_id",
            "section_id",
            "service_id",
            "center_id",
            "agenda_id",
        ),
    )
    return normalized


def attach_resource_metadata(
    supply: pd.DataFrame,
    resource_mapping: pd.DataFrame,
) -> pd.DataFrame:
    """Attach service, section, and center fields with a many-to-one join."""

    metadata = resource_mapping.rename(
        columns={
            "clinician_id": "mapped_clinician_id",
            "agenda_id": "mapped_agenda_id",
        }
    )
    input_rows = len(supply)
    try:
        mapped = supply.merge(
            metadata,
            how="left",
            on="resource_mapping_key",
            validate="many_to_one",
            indicator=True,
        )
    except MergeError as exc:
        raise MappingCardinalityError(
            "Resource mapping cannot satisfy a many-to-one join"
        ) from exc

    if len(mapped) != input_rows:
        raise MappingCardinalityError(
            "Resource mapping join changed the supply row count: "
            f"before {input_rows}, after {len(mapped)}"
        )
    unmapped = mapped["_merge"] != "both"
    if unmapped.any():
        key = str(mapped.loc[unmapped, "resource_mapping_key"].iloc[0])
        raise SupplyValidationError(f"Supply references unknown mapping key {key!r}")
    if not mapped["clinician_id"].eq(mapped["mapped_clinician_id"]).all():
        key = str(
            mapped.loc[
                ~mapped["clinician_id"].eq(mapped["mapped_clinician_id"]),
                "resource_mapping_key",
            ].iloc[0]
        )
        raise SupplyValidationError(
            f"Supply clinician disagrees with resource mapping {key!r}"
        )
    if not mapped["agenda_id"].eq(mapped["mapped_agenda_id"]).all():
        key = str(
            mapped.loc[
                ~mapped["agenda_id"].eq(mapped["mapped_agenda_id"]),
                "resource_mapping_key",
            ].iloc[0]
        )
        raise SupplyValidationError(
            f"Supply agenda disagrees with resource mapping {key!r}"
        )
    return mapped.drop(
        columns=["mapped_clinician_id", "mapped_agenda_id", "_merge"]
    )


def aggregate_blocks(blocks: pd.DataFrame) -> pd.DataFrame:
    """Deterministically sum repeated block rows by the public block key."""

    return (
        blocks.groupby(list(BLOCK_MATCH_KEY), as_index=False, sort=True)[
            "blocked_capacity"
        ]
        .sum()
        .sort_values(list(BLOCK_MATCH_KEY), ignore_index=True)
    )


def apply_blocked_capacity(
    mapped_supply: pd.DataFrame,
    aggregated_blocks: pd.DataFrame,
) -> pd.DataFrame:
    """Attach aggregated blocks without adding or removing supply rows."""

    input_rows = len(mapped_supply)
    try:
        result = mapped_supply.merge(
            aggregated_blocks,
            how="left",
            on=list(BLOCK_MATCH_KEY),
            validate="one_to_one",
        )
    except MergeError as exc:
        raise MappingCardinalityError(
            "Block application cannot satisfy a one-to-one join"
        ) from exc
    if len(result) != input_rows:
        raise MappingCardinalityError(
            "Block join changed the supply row count: "
            f"before {input_rows}, after {len(result)}"
        )
    result["blocked_capacity"] = (
        result["blocked_capacity"].fillna(0).astype("int64")
    )
    return result


def compute_capacity_fields(supply: pd.DataFrame) -> pd.DataFrame:
    """Calculate explicit standard, total, used, and remaining capacities."""

    result = supply.copy(deep=True)
    total_configured = result["base_capacity"] + result["overbooking_capacity"]
    excess = result["blocked_capacity"] > total_configured
    if excess.any():
        key = str(result.loc[excess, "schedule_key"].iloc[0])
        raise SupplyValidationError(
            f"Blocked capacity exceeds total configured capacity for {key!r}"
        )
    result["standard_available_capacity"] = (
        result["base_capacity"] - result["blocked_capacity"]
    ).clip(lower=0)
    result["total_available_capacity"] = (
        total_configured - result["blocked_capacity"]
    )
    result["used_capacity"] = 0
    result["remaining_capacity"] = result["total_available_capacity"]
    return result


def preprocess_supply(
    supply: pd.DataFrame,
    blocks: pd.DataFrame,
    resource_mapping: pd.DataFrame,
) -> SupplyPreprocessingResult:
    """Return validated active availability without mutating any input frame.

    Inactive supply is validated and mapped, then removed. Blocked capacity is
    aggregated by ``(schedule_key, agenda_id, date)`` and applied to exactly one
    supply opportunity. Initial used capacity is always zero.
    """

    validate_supply_input(supply)
    validate_blocks_input(blocks)
    validate_mapping_input(resource_mapping)

    normalized_supply = _normalize_supply(supply)
    normalized_blocks = _normalize_blocks(blocks)
    normalized_mapping = _normalize_mapping(resource_mapping)

    validate_supply_uniqueness(normalized_supply)
    validate_mapping_cardinality(normalized_mapping)
    validate_orphan_blocks(normalized_supply, normalized_blocks)

    mapped = attach_resource_metadata(normalized_supply, normalized_mapping)
    aggregated_blocks = aggregate_blocks(normalized_blocks)
    with_blocks = apply_blocked_capacity(mapped, aggregated_blocks)
    with_capacity = compute_capacity_fields(with_blocks)

    active_rows = int(with_capacity["active"].sum())
    availability = with_capacity.loc[with_capacity["active"]].copy()
    availability = availability.loc[:, AVAILABILITY_COLUMNS].sort_values(
        ["date", "agenda_id", "clinician_id", "schedule_key", "event_type"],
        ignore_index=True,
        kind="mergesort",
    )
    validate_availability_output(availability, expected_rows=active_rows)

    diagnostics = SupplyPreprocessingDiagnostics(
        input_supply_rows=len(normalized_supply),
        active_supply_rows=active_rows,
        output_availability_rows=len(availability),
        inactive_rows_removed=len(normalized_supply) - active_rows,
        input_block_rows=len(normalized_blocks),
        aggregated_block_keys=len(aggregated_blocks),
        mapped_rows=len(mapped),
        unmapped_rows=0,
        total_base_capacity=int(availability["base_capacity"].sum()),
        total_overbooking_capacity=int(
            availability["overbooking_capacity"].sum()
        ),
        total_blocked_capacity=int(availability["blocked_capacity"].sum()),
        total_standard_available_capacity=int(
            availability["standard_available_capacity"].sum()
        ),
        total_available_capacity=int(
            availability["total_available_capacity"].sum()
        ),
    )
    return SupplyPreprocessingResult(
        availability=availability,
        diagnostics=diagnostics,
    )
