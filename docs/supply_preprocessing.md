# Supply Preprocessing

The preprocessing layer turns three synthetic DataFrames into a deterministic
availability table. It performs no file I/O, scheduling, or capacity
consumption.

## Inputs

- `supply`: dated opportunities, configured capacity, modality, and event type.
- `blocks`: reductions in capacity associated with supply opportunities.
- `resource_mapping`: canonical clinician, service, section, center, and agenda
  relationships.

Inputs are copied before normalization. Caller-owned DataFrames are never
modified. String identifiers are trimmed, dates are normalized to midnight
`datetime64[ns]` values, and capacity fields are represented as integers.

## Public API

```python
from appointment_scheduling.preprocessing import preprocess_supply

result = preprocess_supply(supply, blocks, resource_mapping)
availability = result.availability
diagnostics = result.diagnostics
```

The result contains a new availability DataFrame and an immutable diagnostics
record. Core preprocessing neither reads nor writes files.

## Join keys and cardinality

Supply is joined to resource metadata on:

```text
resource_mapping_key
```

Every mapping key must occur exactly once in `resource_mapping`. The join is
validated as `many_to_one`, and the output row count must equal the input supply
row count. Supply clinician and agenda values must also agree with their mapping.

Blocks are aggregated and joined on:

```text
schedule_key, agenda_id, date
```

Multiple block rows may share this key and are summed deterministically. The
aggregated block join is `one_to_one`: this key must identify exactly one supply
row. Every block key must already exist in supply, so blocks can never create
availability rows.

One unique supply opportunity is defined by:

```text
date, schedule_key, agenda_id, clinician_id, event_type, modality
```

Exact duplicates and semantic duplicates are rejected. The shorter block key is
also required to be unique in supply because otherwise one blocked-capacity
amount would ambiguously apply to multiple opportunities. No supply aggregation
is implicit.

## Capacity semantics

For every active supply row:

```text
standard_available_capacity = max(base_capacity - blocked_capacity, 0)
total_available_capacity = base_capacity + overbooking_capacity - blocked_capacity
used_capacity = 0
remaining_capacity = total_available_capacity
```

`base_capacity` represents ordinary capacity. `overbooking_capacity` is visible
additional capacity that the applied sequential scheduler and the research
policies may choose to use once standard capacity is exhausted. Blocked
capacity is unavailable capacity and is applied before scheduling.

All capacity inputs must be non-negative integers. The strict public policy
rejects a row when blocked capacity exceeds base plus overbooking capacity, so
total availability cannot become negative. Blocking may consume all ordinary
capacity while leaving overbooking capacity visible.

## Active supply

Inactive rows are fully validated and participate in referential and orphan-block
checks, but they are omitted from the availability table. Their removal is
reported in diagnostics. Consequently, every output row is directly schedulable
from an activity-status perspective.

## Stable output

Availability is sorted stably by:

```text
date, agenda_id, clinician_id, schedule_key, event_type
```

Initial capacity and aggregate totals are validated after all joins. In
particular:

```text
sum(total_available_capacity)
= sum(base_capacity) + sum(overbooking_capacity) - sum(blocked_capacity)
```

The equality applies to the retained active rows.

## Edge-case behavior

- Missing blocks produce zero blocked capacity.
- Repeated block rows aggregate to one block key.
- Partial and full blocking are accepted when they do not exceed total capacity.
- Excess blocking is rejected.
- Orphan blocks are rejected rather than dropped.
- Unknown or ambiguous resource mappings are rejected.
- Identical duplicate mappings are rejected rather than silently deduplicated.
- Any mapping or block join that changes the supply row count is an error.

The diagnostics record includes input, active, mapped, removed, and output row
counts; raw and aggregated block counts; and aggregate base, overbooking,
blocked, standard-available, and total-available capacity.
