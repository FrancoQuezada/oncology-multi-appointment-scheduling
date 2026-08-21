"""Canonical column schemas for the public CSV datasets."""

DEMAND_COLUMNS = (
    "patient_id",
    "appointment_status",
    "event_type",
    "appointment_date",
    "booking_date",
    "care_type",
    "agenda_id",
    "clinician_id",
    "service_id",
    "section_id",
)

SUPPLY_COLUMNS = (
    "block_id",
    "clinician_id",
    "date",
    "active",
    "base_capacity",
    "overbooking_capacity",
    "resource_mapping_key",
    "agenda_id",
    "schedule_key",
    "modality",
    "event_type",
)

BLOCK_COLUMNS = (
    "schedule_key",
    "agenda_id",
    "date",
    "blocked_capacity",
    "block_reason_code",
)

RESOURCE_MAPPING_COLUMNS = (
    "resource_mapping_key",
    "clinician_id",
    "section_id",
    "service_id",
    "center_id",
    "agenda_id",
)

ROUTE_COLUMNS = (
    "patient_id",
    "pathway_id",
    "event_number",
    "event_id",
    "agenda_id",
    "event_type",
    "min_spacing_days",
    "preferred_max_spacing_days",
    "dependencies",
    "clinician_id",
    "service_id",
    "section_id",
    "modality",
    "resource_mode",
    "overbooking_allowed",
)

REQUIRED_COLUMNS = {
    "demand": DEMAND_COLUMNS,
    "supply": SUPPLY_COLUMNS,
    "blocks": BLOCK_COLUMNS,
    "resource_mapping": RESOURCE_MAPPING_COLUMNS,
    "routes": ROUTE_COLUMNS,
}

DATE_COLUMNS = {
    "demand": ("appointment_date", "booking_date"),
    "supply": ("date",),
    "blocks": ("date",),
    "resource_mapping": (),
    "routes": (),
}
