"""Public data structures and schemas for supply preprocessing."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

BLOCK_MATCH_KEY = ("schedule_key", "agenda_id", "date")

SUPPLY_OPPORTUNITY_KEY = (
    "date",
    "schedule_key",
    "agenda_id",
    "clinician_id",
    "event_type",
    "modality",
)

AVAILABILITY_COLUMNS = (
    "date",
    "schedule_key",
    "block_id",
    "agenda_id",
    "clinician_id",
    "resource_mapping_key",
    "service_id",
    "section_id",
    "center_id",
    "modality",
    "event_type",
    "base_capacity",
    "overbooking_capacity",
    "blocked_capacity",
    "standard_available_capacity",
    "total_available_capacity",
    "used_capacity",
    "remaining_capacity",
    "active",
)


@dataclass(frozen=True, slots=True)
class SupplyPreprocessingDiagnostics:
    """Compact counts and capacity totals from one preprocessing run."""

    input_supply_rows: int
    active_supply_rows: int
    output_availability_rows: int
    inactive_rows_removed: int
    input_block_rows: int
    aggregated_block_keys: int
    mapped_rows: int
    unmapped_rows: int
    total_base_capacity: int
    total_overbooking_capacity: int
    total_blocked_capacity: int
    total_standard_available_capacity: int
    total_available_capacity: int


@dataclass(frozen=True, slots=True)
class SupplyPreprocessingResult:
    """Availability table and diagnostics returned by preprocessing."""

    availability: pd.DataFrame
    diagnostics: SupplyPreprocessingDiagnostics
