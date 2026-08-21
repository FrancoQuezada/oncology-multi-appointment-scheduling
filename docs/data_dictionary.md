# Synthetic Data Dictionary

> All data included in this project are synthetic and were generated specifically for software demonstration and reproducibility. They do not correspond to real patients, clinicians, healthcare institutions, schedules, capacities, or clinical pathways.

> The fictional pathways and timing parameters are not clinical recommendations.

The canonical files use CSV so the core generator has no spreadsheet
dependency. Dates use ISO `YYYY-MM-DD` strings within the fixed artificial
horizon 2035-01-01 through 2035-01-28. Dependencies are JSON integer lists such
as `[]`, `[1]`, or `[2,3]`.

## `demand.csv`

| Column | Type | Purpose and typical synthetic value | Relationships and validation |
|---|---|---|---|
| `patient_id` | string | Fictional patient key, e.g. `PAT-001` | Must match `PAT-###`; route patients must exist here |
| `appointment_status` | category | `COMPLETED`, `SCHEDULED`, or `CANCELLED` | Restricted to the documented values |
| `event_type` | string | Artificial event label such as `EVENT-A1` | Must use the public event-ID format |
| `appointment_date` | date | Artificial appointment date | Must lie inside the demo horizon |
| `booking_date` | date | Artificial booking date | Must lie inside the horizon and not follow the appointment date |
| `care_type` | category | `STANDARD` or `FOLLOW_UP` | Restricted to the documented values |
| `agenda_id` | string | Generic agenda such as `AGENDA-DEMO-01` | Must form a valid resource tuple in `resource_mapping.csv` |
| `clinician_id` | string | Generic resource ID such as `CLINICIAN-01` | Must exist in `resource_mapping.csv` |
| `service_id` | string | Generic service such as `SERVICE-A` | Validated together with section, clinician, and agenda |
| `section_id` | string | Generic section such as `SECTION-A1` | Validated together with service |

This file is retained for schema completeness. It is not currently consumed by
route or timing extraction logic, which is built directly from `routes.csv`.
Its distribution is intentionally illustrative rather than representative.

## `supply.csv`

| Column | Type | Purpose and typical synthetic value | Relationships and validation |
|---|---|---|---|
| `block_id` | string | Unique supply-row key such as `SUPPLY-BLOCK-001` | Must be unique and match the public format |
| `clinician_id` | string | Generic scheduled resource | Must agree with `resource_mapping_key` |
| `date` | date | Date on which capacity is available | Must lie inside the demo horizon |
| `active` | boolean | Whether the supply row can be used | Canonical data use `true` |
| `base_capacity` | integer | Artificial regular capacity from 1 to 4 | Must be non-negative |
| `overbooking_capacity` | integer | Artificial extra capacity from 0 to 2 | Must be non-negative |
| `resource_mapping_key` | string | Mapping key such as `MAP-A1` | Must exist in `resource_mapping.csv` |
| `agenda_id` | string | Generic agenda | Must agree with the mapping key |
| `schedule_key` | string | Unique demo schedule reference | Used by `blocks.csv` |
| `modality` | category | `IN_PERSON` or `REMOTE` | Must match a documented category |
| `event_type` | string | Artificial event supported by the slot | Used to establish compatibility with routes |

## `blocks.csv`

| Column | Type | Purpose and typical synthetic value | Relationships and validation |
|---|---|---|---|
| `schedule_key` | string | Schedule being reduced | Must match a supply schedule/agenda/date tuple |
| `agenda_id` | string | Agenda being reduced | Must match the same supply tuple |
| `date` | date | Date of the reduction | Must lie inside the demo horizon |
| `blocked_capacity` | integer | Artificial unavailable capacity from 1 to 3 | Non-negative and no greater than total row capacity |
| `block_reason_code` | category | Generic `BLOCK-A`, `BLOCK-B`, or `BLOCK-C` | No free-text operational reasons are used |

The fixture deliberately contains both partial and full blockage.

## `resource_mapping.csv`

| Column | Type | Purpose and typical synthetic value | Relationships and validation |
|---|---|---|---|
| `resource_mapping_key` | string | Unique mapping key such as `MAP-A1` | Primary key referenced by supply |
| `clinician_id` | string | Generic schedulable resource | Used by demand, supply, and routes |
| `section_id` | string | Generic section | Part of the compatibility relationship |
| `service_id` | string | Generic service | Part of the compatibility relationship |
| `center_id` | string | Generic location such as `CENTER-01` | Must use the public center format |
| `agenda_id` | string | Generic agenda | Used by all scheduling datasets |

Resources that share service and section values can demonstrate alternative
compatible assignments. A route's clinician is its preferred resource.

## `routes.csv`

| Column | Type | Purpose and typical synthetic value | Relationships and validation |
|---|---|---|---|
| `patient_id` | string | Fictional patient key | Must exist in `demand.csv` |
| `pathway_id` | string | Artificial graph such as `PATHWAY-A` | Must match a declared pathway |
| `event_number` | integer | One-based event number within a route | Unique per patient |
| `event_id` | string | Artificial event ID such as `EVENT-A1` | Must match the pathway definition |
| `agenda_id` | string | Preferred generic agenda | Must form a valid resource tuple |
| `event_type` | string | Capability required from supply | Uses the public event-ID format |
| `min_spacing_days` | integer | Artificial minimum delay after predecessors | Must be non-negative |
| `preferred_max_spacing_days` | integer | Artificial preferred upper window | Must be at least the minimum |
| `dependencies` | JSON list | Predecessor event numbers, e.g. `[2,3]` | References must exist and form a DAG |
| `clinician_id` | string | Preferred generic resource | Must exist in the canonical mapping |
| `service_id` | string | Required generic service | Must exist with the section in the mapping |
| `section_id` | string | Required generic section | Must exist with the service in the mapping |
| `modality` | category | `IN_PERSON` or `REMOTE` | Used in supply compatibility |
| `resource_mode` | category | `FIXED` or `COMPATIBLE_SET` | States whether clinician and agenda are mandatory or preferred within the compatible service/section set |
| `overbooking_allowed` | boolean | Whether schedulers may use extra capacity for this event | Canonical routes contain both values |

The routes deliberately include branching dependencies, heterogeneous spacing,
one request without compatible supply, and one spacing requirement that extends
beyond the fixed horizon. These are software edge cases, not operational or
clinical claims. Their conversion into typed patient routes and dependency DAGs
is documented in [`route_model.md`](route_model.md).

## Preprocessed availability table

The availability table is returned in memory by the supply preprocessing API;
it is not another canonical input file.

| Column | Type | Meaning and validation |
|---|---|---|
| `date` | datetime | Normalized supply date used in stable ordering |
| `schedule_key` | string | Supply schedule reference and part of the block key |
| `block_id` | string | Unique source supply-row identifier |
| `agenda_id` | string | Generic agenda validated against the resource mapping |
| `clinician_id` | string | Generic clinician validated against the mapping |
| `resource_mapping_key` | string | Unique key used for the many-to-one metadata join |
| `service_id` | string | Generic service attached from the mapping |
| `section_id` | string | Generic section attached from the mapping |
| `center_id` | string | Generic center attached from the mapping |
| `modality` | category | Source supply modality |
| `event_type` | string | Artificial event capability offered by the row |
| `base_capacity` | integer | Configured ordinary capacity; non-negative |
| `overbooking_capacity` | integer | Visible optional additional capacity; non-negative |
| `blocked_capacity` | integer | Sum of matching block rows, or zero |
| `standard_available_capacity` | integer | `max(base_capacity - blocked_capacity, 0)` |
| `total_available_capacity` | integer | `base + overbooking - blocked`; non-negative |
| `used_capacity` | integer | Always zero during preprocessing |
| `remaining_capacity` | integer | Initially equal to total available capacity |
| `active` | boolean | Always true because inactive rows are omitted |

The resource join cannot multiply supply rows, and the block key must identify
exactly one supply opportunity. Full details are in
[`supply_preprocessing.md`](supply_preprocessing.md).
