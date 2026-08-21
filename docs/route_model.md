# Public Route Model

## Multi-appointment nature

The represented scheduling problem coordinates routes of related events rather
than treating appointments as independent requests. Each synthetic patient has
one patient-specific route instance associated with an artificial pathway
template. Events carry resource preferences and temporal parameters that the
scheduling and research modules consume.

The pathway examples are deliberately nonlinear: an event can depend on several
predecessors, and one predecessor can unlock several successors.

## Public API

```python
from appointment_scheduling.routes import preprocess_routes

result = preprocess_routes(routes)
patient_route = result.route_for("PAT-001")
graph = patient_route.graph
```

Core preprocessing accepts an in-memory DataFrame, performs no file I/O, does
not modify its input, and returns immutable route structures. It does not assign
dates or consume capacity.

The main models are:

- `RouteEvent`: one patient-specific event and its resource/timing requirements;
- `PatientRoute`: all events and the dependency graph for one patient;
- `RouteGraph`: predecessor/successor maps and derived DAG properties;
- `PathwayTemplate`: patient-independent artificial pathway structure;
- `RoutePreprocessingResult`: patient routes, templates, and diagnostics.

A pathway template and a patient route instance are intentionally separate. One
template can produce many patient routes, while resource preferences may vary by
patient without altering the shared dependency graph or timing structure.

Each route event also declares `resource_mode`. `FIXED` makes its clinician and
agenda mandatory; `COMPATIBLE_SET` makes them preferred choices within the
event's service, section, event-type, and modality compatibility set. This keeps
alternative-resource behavior explicit for the scheduling feasibility layer.

## Dependency graph

Dependencies in `routes.csv` use JSON integer lists:

```text
[]
[1]
[2,3]
```

They become immutable tuples. For a dependency from event `i` to event `j`, the
directed graph contains the arc:

```text
i -> j
```

Every patient route exposes:

```text
predecessors
successors
topological_order
root_events
terminal_events
branch_events
join_events
depth_by_event
max_depth
```

A root has no predecessors. A terminal has no successors. A branch has more
than one successor. A join has more than one predecessor. Multiple roots and
terminals are supported.

Topological ordering uses event number as a deterministic tie-breaker. Route
depth is the number of events on the longest dependency chain ending at an
event; roots have depth 1.

Preprocessing rejects malformed lists, noninteger or repeated dependencies,
self-dependencies, missing event references, duplicate event keys, noncontiguous
numbering, and dependency cycles. It does not repair invalid graphs.

## Temporal constraints

Each event preserves two deliberately distinct fields:

- `min_spacing_days`: the enforced lower spacing parameter used by every
  scheduling decision;
- `preferred_max_spacing_days`: a soft or preferred threshold used by the
  heuristics and the optimization objective.

The preferred maximum is validated to be no smaller than the minimum, but this
layer does not turn it into a hard deadline or impose scheduling consequences.

For a dependent event `j`, once all predecessors have realized dates, the public
lower-bound semantics are:

```text
reference_date = max(scheduled_date(i) for i in predecessors(j))
earliest_feasible_date(j) = reference_date + min_spacing_days(j)
```

`PatientRoute.temporal_lower_bound(...)` implements only this calculation. It
does not choose a slot or consume a resource. Root events require an external
route-start reference and therefore have no predecessor-derived lower bound.

## Branching and joining

Nonlinear routes are first-class structures. Branching supports concurrent or
independently constrained downstream work. Joining represents an event that
cannot become eligible until several upstream events have realized dates. The
latest predecessor supplies the temporal reference for such a join.

## Research and application bridge

The same representation serves two consumers:

- operational scheduling code (`scheduling/`, `schedulers/`) uses predecessors,
  successors, temporal lower bounds, resource requirements, and
  dependency-aware state transitions;
- optimization and experimental code (`research/`, `optimization/`) uses
  patient-event sets, dependency arcs, timing parameters, topological
  structure, and stable indexing.

Keeping one shared route model prevents the applied and research components from
developing incompatible interpretations of an event or dependency.

## Data provenance

> The pathway examples included in the public repository are artificial software fixtures. They do not reproduce real clinical protocols or treatment recommendations.

Their identifiers, graphs, timing values, and resource combinations were chosen
for reproducible software testing. They are not statistically calibrated to an
institution or population.
