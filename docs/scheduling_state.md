# Dynamic Scheduling Feasibility

## Why state is needed

Multi-appointment scheduling is sequential. Assigning one event consumes a
specific unit of supply and can make downstream events eligible, so feasibility
must be evaluated against the current assignments and capacity usage rather
than against routes or availability in isolation.

`SchedulingState` combines three inputs while keeping their roles separate:

```text
immutable patient routes
+ immutable availability opportunities
+ copy-on-write assignments, capacity usage, and pending records
= current scheduling feasibility
```

The state layer answers *what is feasible*. It deliberately does not select,
rank, or optimize the returned alternatives.

## Public API

```python
from appointment_scheduling.scheduling import (
    assign_event,
    build_scheduling_state,
    get_candidate_slots,
    mark_pending,
)

state = build_scheduling_state(routes, availability, route_start_dates)
candidates = get_candidate_slots(state, "PAT-001", 1)
new_state = assign_event(state, "PAT-001", 1, candidates[0])
```

`route_start_dates` is an explicit patient-to-date mapping. It supplies the
temporal reference for root events because the synthetic route table does not
contain an arrival date. No hidden horizon-start assumption is made.

## Eligibility and event status

Every event in a constructed state has one derived status:

- `ELIGIBLE`: unassigned, not pending, and every predecessor is assigned;
- `BLOCKED_BY_PREDECESSOR`: at least one predecessor is unassigned;
- `ASSIGNED`: linked to one exact availability opportunity;
- `PENDING`: explicitly marked unresolved by the caller.

A separate stored `UNSCHEDULED` status is unnecessary: eligibility is evaluated
immediately, so every ordinary unassigned event is either eligible or
dependency-blocked. Finding no candidates does not change an eligible event to
pending.

For a root event, the route start date is the timing reference. For a dependent
event, the reference is the latest realized predecessor date:

```text
earliest_date = reference + min_spacing_days
preferred_latest_date = reference + preferred_max_spacing_days
```

The earliest date is a hard feasibility boundary. The preferred latest date is
only an annotation: later opportunities remain candidates and are marked
`within_preferred_window=False`.

## Resource compatibility

The public route schema includes an explicit `resource_mode`:

- `FIXED` requires service, section, event type, modality, clinician, and agenda
  to match the route event;
- `COMPATIBLE_SET` requires service, section, event type, and modality to match,
  while the listed clinician and agenda are preferences rather than hard keys.

Candidate generation returns every matching opportunity. There is no implicit
fallback and no preferred-resource selection. This explicit mode is the only
schema addition introduced for the feasibility layer.

## Capacity

Each availability row is represented by one immutable opportunity identified by
its unique public `block_id`. Dynamic capacity is indexed by that identifier,
never by a broad clinician/date predicate.

Each assignment consumes exactly one synthetic unit from exactly one
opportunity. Standard capacity is used while it remains. An opportunity is
marked `OVERBOOKING` only after standard capacity is exhausted, total capacity
remains, and the route event explicitly permits overbooking. The assignment
records the capacity tier for auditability.

Candidate slots expose both remaining-capacity values and the capacity tier the
assignment would require. Zero-total-capacity rows and disallowed
overbooking-only rows are excluded.

## Candidate generation

`get_candidate_slots` checks dependency status, calculates the timing window,
matches the explicit resource contract, filters to dates represented by supply,
and evaluates current capacity. Results are deterministic by:

```text
date, agenda_id, clinician_id, schedule_key, opportunity_id
```

This ordering is reproducible but is not a scheduling preference. Candidate
records include patient-event identity, the exact opportunity key, resource
metadata, remaining capacity, required capacity tier, preferred-window status,
and whether the opportunity uses the listed preferred resource.

## State transitions

`assign_event` verifies current eligibility and requires the exact candidate to
still exist in the current state. This rejects stale candidates after another
transition changes capacity. A successful transition records one assignment,
decrements one opportunity by one, and returns a new state snapshot. The old
state, route models, and source availability DataFrame remain unchanged.

`mark_pending` is also explicit and uses a controlled public reason enum. It
does not automatically propagate pending status downstream; successors remain
dependency-blocked until a scheduling policy defines propagation. The applied
sequential scheduler implements this propagation (see
[`sequential_scheduler.md`](sequential_scheduler.md)); this layer intentionally
does not, so that state transitions stay policy-neutral.

## State invariants

Validation enforces:

- at most one assignment per patient-event;
- no event is both assigned and pending;
- all assignment and opportunity references exist and agree;
- assigned predecessors and minimum spacing are satisfied;
- resource compatibility is preserved;
- used and remaining capacity are nonnegative and reconcile to initial supply;
- standard usage cannot exceed standard capacity;
- overbooking cannot precede standard exhaustion or exceed total capacity;
- events that disallow overbooking never consume it;
- assignment counts exactly reconcile with per-opportunity capacity usage.

## Research and application bridge

The operational sequential scheduler, ASAP and resource-aware heuristics can all
consume the same candidate and transition rules. Research experiments can use
the same engine to validate feasible heuristic or optimization outputs and to
compare lateness, resource choice, capacity use, and unresolved events without
creating a second interpretation of feasibility.

The public architecture intentionally improves one material implementation
detail: capacity is consumed by an exact immutable opportunity identifier. This
preserves the applied concept while preventing one assignment from changing
multiple rows that happen to share broad resource attributes.

No scheduler policy, candidate ranking, backtracking, or optimization model is
implemented in this layer.
