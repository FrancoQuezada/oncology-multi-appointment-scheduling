"""Schema, integrity, safety, and fixture-quality validation."""

from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from collections.abc import Mapping

import pandas as pd

from appointment_scheduling.config import DEMO_END_DATE, DEMO_START_DATE
from appointment_scheduling.synthetic.pathways import PATHWAYS
from appointment_scheduling.synthetic.schemas import DATE_COLUMNS, REQUIRED_COLUMNS


class ValidationError(ValueError):
    """Raised when a synthetic dataset violates its public data contract."""


_ID_PATTERNS = {
    "patient_id": re.compile(r"PAT-\d{3}"),
    "clinician_id": re.compile(r"CLINICIAN-\d{2}"),
    "service_id": re.compile(r"SERVICE-[A-Z]"),
    "section_id": re.compile(r"SECTION-[A-Z]\d"),
    "center_id": re.compile(r"CENTER-\d{2}"),
    "agenda_id": re.compile(r"AGENDA-DEMO-\d{2}"),
    "resource_mapping_key": re.compile(r"MAP-[A-Z]\d"),
    "schedule_key": re.compile(r"SCHEDULE-DEMO-\d{3}"),
    "block_id": re.compile(r"SUPPLY-BLOCK-\d{3}"),
    "pathway_id": re.compile(r"PATHWAY-[A-Z]"),
    "event_id": re.compile(r"EVENT-[A-Z]\d"),
    "event_type": re.compile(r"EVENT-[A-Z]\d"),
}
_NATIONAL_ID_PATTERN = re.compile(r"\b\d{1,2}(?:\.\d{3}){2}-[0-9A-Za-z]\b")
_ALLOWED_MODALITIES = {"IN_PERSON", "REMOTE"}
_ALLOWED_STATUSES = {"COMPLETED", "SCHEDULED", "CANCELLED"}
_ALLOWED_CARE_TYPES = {"STANDARD", "FOLLOW_UP"}
_ALLOWED_BLOCK_REASONS = {"BLOCK-A", "BLOCK-B", "BLOCK-C"}
_ALLOWED_RESOURCE_MODES = {"FIXED", "COMPATIBLE_SET"}


def parse_dependencies(value: object) -> list[int]:
    """Parse a compact JSON integer list such as ``[1,2]``."""

    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Invalid dependency representation: {value!r}") from exc
    if not isinstance(parsed, list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in parsed
    ):
        raise ValidationError(f"Dependencies must be a JSON list of integers: {value!r}")
    if len(parsed) != len(set(parsed)):
        raise ValidationError(f"Dependencies contain duplicates: {value!r}")
    return parsed


def _require_datasets(datasets: Mapping[str, pd.DataFrame]) -> None:
    missing = sorted(set(REQUIRED_COLUMNS) - set(datasets))
    if missing:
        raise ValidationError(f"Missing datasets: {', '.join(missing)}")


def validate_schemas(datasets: Mapping[str, pd.DataFrame]) -> None:
    """Validate dataset presence, required columns, nulls, and duplicate keys."""

    _require_datasets(datasets)
    for name, required in REQUIRED_COLUMNS.items():
        frame = datasets[name]
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise ValidationError(f"{name} is missing required columns: {missing}")
        null_columns = [column for column in required if frame[column].isna().any()]
        if null_columns:
            raise ValidationError(f"{name} contains null required fields: {null_columns}")

    unique_keys = {
        "supply": ["block_id"],
        "resource_mapping": ["resource_mapping_key"],
        "routes": ["patient_id", "event_number"],
    }
    for name, columns in unique_keys.items():
        if datasets[name].duplicated(columns).any():
            raise ValidationError(f"{name} contains duplicate key values for {columns}")


def validate_identifiers(datasets: Mapping[str, pd.DataFrame]) -> None:
    """Require clearly artificial identifiers and reject national-ID patterns."""

    _require_datasets(datasets)
    for name, frame in datasets.items():
        for column, pattern in _ID_PATTERNS.items():
            if column not in frame:
                continue
            invalid = ~frame[column].astype(str).str.fullmatch(pattern)
            if invalid.any():
                raise ValidationError(f"{name}.{column} contains a non-public identifier")
        for column in frame.columns:
            values = frame[column].dropna().astype(str)
            if values.str.contains(_NATIONAL_ID_PATTERN, regex=True).any():
                raise ValidationError(f"{name}.{column} contains a national-ID-like value")

    if not datasets["blocks"]["block_reason_code"].isin(_ALLOWED_BLOCK_REASONS).all():
        raise ValidationError("blocks.block_reason_code contains an unsupported value")
    if not datasets["supply"]["modality"].isin(_ALLOWED_MODALITIES).all():
        raise ValidationError("supply.modality contains an unsupported value")
    if not datasets["routes"]["modality"].isin(_ALLOWED_MODALITIES).all():
        raise ValidationError("routes.modality contains an unsupported value")
    if not datasets["routes"]["resource_mode"].isin(_ALLOWED_RESOURCE_MODES).all():
        raise ValidationError("routes.resource_mode contains an unsupported value")
    if not datasets["demand"]["appointment_status"].isin(_ALLOWED_STATUSES).all():
        raise ValidationError("demand.appointment_status contains an unsupported value")
    if not datasets["demand"]["care_type"].isin(_ALLOWED_CARE_TYPES).all():
        raise ValidationError("demand.care_type contains an unsupported value")


def validate_referential_integrity(datasets: Mapping[str, pd.DataFrame]) -> None:
    """Validate all cross-dataset keys and resource relationships."""

    _require_datasets(datasets)
    mapping = datasets["resource_mapping"]
    mapping_by_key = mapping.set_index("resource_mapping_key")
    valid_resource_tuples = set(
        mapping[["clinician_id", "service_id", "section_id", "agenda_id"]]
        .itertuples(index=False, name=None)
    )

    for _, row in datasets["supply"].iterrows():
        key = row["resource_mapping_key"]
        if key not in mapping_by_key.index:
            raise ValidationError(f"Supply references unknown resource mapping: {key}")
        expected = mapping_by_key.loc[key]
        if row["clinician_id"] != expected["clinician_id"]:
            raise ValidationError(f"Supply clinician does not match resource mapping: {key}")
        if row["agenda_id"] != expected["agenda_id"]:
            raise ValidationError(f"Supply agenda does not match resource mapping: {key}")

    for dataset_name in ("demand", "routes"):
        frame = datasets[dataset_name]
        for resource_tuple in frame[
            ["clinician_id", "service_id", "section_id", "agenda_id"]
        ].itertuples(index=False, name=None):
            if resource_tuple not in valid_resource_tuples:
                raise ValidationError(
                    f"{dataset_name} references an unknown clinician/service/section/agenda combination"
                )

    demand_patients = set(datasets["demand"]["patient_id"])
    route_patients = set(datasets["routes"]["patient_id"])
    if not route_patients <= demand_patients:
        raise ValidationError("Routes reference patients absent from demand")

    supply_references = set(
        datasets["supply"][["schedule_key", "agenda_id", "date"]]
        .astype(str)
        .itertuples(index=False, name=None)
    )
    for reference in (
        datasets["blocks"][["schedule_key", "agenda_id", "date"]]
        .astype(str)
        .itertuples(index=False, name=None)
    ):
        if reference not in supply_references:
            raise ValidationError("A block references an unknown schedule/agenda/date combination")


def _validate_one_route(patient_id: str, route: pd.DataFrame) -> bool:
    numbers = set(int(value) for value in route["event_number"])
    adjacency: dict[int, list[int]] = defaultdict(list)
    indegree = {number: 0 for number in numbers}
    branching = False

    for _, row in route.iterrows():
        event_number = int(row["event_number"])
        dependencies = parse_dependencies(row["dependencies"])
        for dependency in dependencies:
            if dependency not in numbers:
                raise ValidationError(
                    f"Route {patient_id} references missing dependency {dependency}"
                )
            if dependency == event_number:
                raise ValidationError(f"Route {patient_id} contains a self-dependency")
            adjacency[dependency].append(event_number)
            indegree[event_number] += 1

    branching = any(len(children) > 1 for children in adjacency.values())
    queue = deque(number for number, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        number = queue.popleft()
        visited += 1
        for child in adjacency[number]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(numbers):
        raise ValidationError(f"Route {patient_id} contains a dependency cycle")
    return branching


def validate_pathways(datasets: Mapping[str, pd.DataFrame]) -> None:
    """Validate timing, dependencies, DAGs, branching, and pathway definitions."""

    routes = datasets["routes"]
    minimum = pd.to_numeric(routes["min_spacing_days"], errors="coerce")
    preferred = pd.to_numeric(routes["preferred_max_spacing_days"], errors="coerce")
    if minimum.isna().any() or (minimum < 0).any():
        raise ValidationError("Route minimum spacing must be a non-negative number")
    if preferred.isna().any() or (preferred < minimum).any():
        raise ValidationError("Preferred maximum spacing must be at least the minimum")

    branching_found = False
    for patient_id, route in routes.groupby("patient_id"):
        branching_found |= _validate_one_route(str(patient_id), route)
    if not branching_found:
        raise ValidationError("At least one branching route is required")

    for pathway_id, expected_events in PATHWAYS.items():
        instances = routes[routes["pathway_id"] == pathway_id]
        if instances.empty:
            raise ValidationError(f"No route instantiates {pathway_id}")
        expected = {
            event.number: (
                event.event_id,
                list(event.dependencies),
                event.min_spacing_days,
                event.preferred_max_spacing_days,
            )
            for event in expected_events
        }
        for patient_id, instance in instances.groupby("patient_id"):
            actual = {
                int(row["event_number"]): (
                    row["event_id"],
                    parse_dependencies(row["dependencies"]),
                    int(row["min_spacing_days"]),
                    int(row["preferred_max_spacing_days"]),
                )
                for _, row in instance.iterrows()
            }
            if actual != expected:
                raise ValidationError(
                    f"Route {patient_id} does not match artificial definition {pathway_id}"
                )


def validate_capacity(datasets: Mapping[str, pd.DataFrame]) -> None:
    """Validate non-negative capacities and valid block magnitudes."""

    supply = datasets["supply"]
    blocks = datasets["blocks"]
    for column in ("base_capacity", "overbooking_capacity"):
        values = pd.to_numeric(supply[column], errors="coerce")
        if values.isna().any() or (values < 0).any():
            raise ValidationError(f"supply.{column} must be non-negative")
    blocked = pd.to_numeric(blocks["blocked_capacity"], errors="coerce")
    if blocked.isna().any() or (blocked < 0).any():
        raise ValidationError("blocks.blocked_capacity must be non-negative")

    capacities = supply.set_index(["schedule_key", "agenda_id", "date"])
    grouped_blocks = blocks.groupby(["schedule_key", "agenda_id", "date"])[
        "blocked_capacity"
    ].sum()
    for key, amount in grouped_blocks.items():
        row = capacities.loc[key]
        total = int(row["base_capacity"] + row["overbooking_capacity"])
        if int(amount) > total:
            raise ValidationError("Blocked capacity exceeds total available capacity")


def validate_dates(datasets: Mapping[str, pd.DataFrame]) -> None:
    """Validate parseable dates within the fixed artificial horizon."""

    lower = pd.Timestamp(DEMO_START_DATE)
    upper = pd.Timestamp(DEMO_END_DATE)
    for name, columns in DATE_COLUMNS.items():
        for column in columns:
            parsed = pd.to_datetime(datasets[name][column], errors="coerce")
            if parsed.isna().any():
                raise ValidationError(f"{name}.{column} contains an invalid date")
            if ((parsed < lower) | (parsed > upper)).any():
                raise ValidationError(f"{name}.{column} falls outside the demo horizon")
    booking = pd.to_datetime(datasets["demand"]["booking_date"])
    appointment = pd.to_datetime(datasets["demand"]["appointment_date"])
    if (booking > appointment).any():
        raise ValidationError("Demand booking dates must not follow appointment dates")


def _supply_with_remaining_capacity(
    datasets: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    supply = datasets["supply"].copy()
    blocks = datasets["blocks"]
    mapping = datasets["resource_mapping"]
    blocked = (
        blocks.groupby(["schedule_key", "agenda_id", "date"], as_index=False)[
            "blocked_capacity"
        ].sum()
    )
    supply = supply.merge(
        blocked,
        how="left",
        on=["schedule_key", "agenda_id", "date"],
    )
    supply["blocked_capacity"] = supply["blocked_capacity"].fillna(0)
    supply["remaining_capacity"] = (
        supply["base_capacity"]
        + supply["overbooking_capacity"]
        - supply["blocked_capacity"]
    )
    return supply.merge(
        mapping[["resource_mapping_key", "service_id", "section_id"]],
        on="resource_mapping_key",
        how="left",
        validate="many_to_one",
    )


def analyze_engineered_cases(
    datasets: Mapping[str, pd.DataFrame],
) -> dict[str, bool | int]:
    """Report whether all intentionally engineered scheduling cases exist."""

    supply = _supply_with_remaining_capacity(datasets)
    blocked = supply["blocked_capacity"]
    total = supply["base_capacity"] + supply["overbooking_capacity"]
    routes = datasets["routes"]
    horizon_days = (DEMO_END_DATE - DEMO_START_DATE).days + 1

    infeasible_count = 0
    alternative_found = False
    for _, route in routes.iterrows():
        compatible = supply[
            (supply["active"] == True)  # noqa: E712 - pandas elementwise comparison
            & (supply["remaining_capacity"] > 0)
            & (supply["event_type"] == route["event_type"])
            & (supply["service_id"] == route["service_id"])
            & (supply["section_id"] == route["section_id"])
            & (supply["modality"] == route["modality"])
        ]
        if compatible.empty:
            infeasible_count += 1
        if compatible["clinician_id"].nunique() > 1:
            alternative_found = True

    branching = False
    for _, route in routes.groupby("patient_id"):
        downstream: dict[int, int] = defaultdict(int)
        for value in route["dependencies"]:
            for dependency in parse_dependencies(value):
                downstream[dependency] += 1
        branching |= any(count > 1 for count in downstream.values())

    return {
        "normal_capacity": bool(((supply["base_capacity"] >= 2) & (blocked == 0)).any()),
        "scarce_capacity": bool((supply["base_capacity"] == 1).any()),
        "overbooking": bool((supply["overbooking_capacity"] > 0).any()),
        "partial_blockage": bool(((blocked > 0) & (blocked < total)).any()),
        "full_blockage": bool(((blocked > 0) & (blocked == total)).any()),
        "multiple_clinicians": supply["clinician_id"].nunique() > 1,
        "multiple_services": supply["service_id"].nunique() > 1,
        "branching": branching,
        "different_minimum_spacing": routes["min_spacing_days"].nunique() > 1,
        "preferred_windows": bool(
            (routes["preferred_max_spacing_days"] > routes["min_spacing_days"]).any()
        ),
        "infeasible_event": infeasible_count >= 1,
        "infeasible_event_count": infeasible_count,
        "horizon_overflow": bool((routes["min_spacing_days"] >= horizon_days).any()),
        "alternative_resource": alternative_found,
    }


def validate_engineered_cases(datasets: Mapping[str, pd.DataFrame]) -> None:
    """Ensure the canonical fixture retains all deliberate edge cases."""

    cases = analyze_engineered_cases(datasets)
    missing = [
        name
        for name, present in cases.items()
        if name != "infeasible_event_count" and not present
    ]
    if missing:
        raise ValidationError(f"Synthetic fixture is missing engineered cases: {missing}")


def validate_demo_dataset(datasets: Mapping[str, pd.DataFrame]) -> None:
    """Run the complete validation suite and raise on the first violation."""

    validate_schemas(datasets)
    validate_identifiers(datasets)
    validate_dates(datasets)
    validate_referential_integrity(datasets)
    validate_pathways(datasets)
    validate_capacity(datasets)
    validate_engineered_cases(datasets)
