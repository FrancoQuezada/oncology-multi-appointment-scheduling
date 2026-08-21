# Research Scheduling Policies

## Applied operational baseline

`APPLIED_SEQUENTIAL` adapts the existing sequential scheduler to the common
research result contract. It represents the reconstructed operational
decision-support workflow: patient routes are processed in route-start and
patient order, events follow deterministic topological order, and the included
demo decision rule selects from the currently feasible alternatives.

The adapter calls the applied workflow unchanged. It only converts the workflow
trace and computes the shared research metrics.

## ASAP

`ASAP` is a distinct research policy with its own public identity and entry
point:

```python
from appointment_scheduling.research import run_asap_policy

result = run_asap_policy(initial_state)
```

For each currently processable event, ASAP assigns the earliest feasible
appointment returned by the shared feasibility engine. Patients are processed
by `route_start_date, patient_id`; events use deterministic topological order.
Ties use the established candidate fields:

```text
date, agenda_id, clinician_id, schedule_key, opportunity_id
```

ASAP may assign after the preferred maximum because that threshold is soft. It
never bypasses predecessors, fixed or compatible-set resource requirements,
remaining capacity, overbooking permission, or the planning horizon.

ASAP and the applied baseline can produce identical decisions. This is retained
as a valid result rather than changing data or tie-breaking to manufacture a
difference. Identical outcomes on one artificial instance do not make the two
methods conceptually or generally equivalent.

## RESOURCE_AWARE

`RESOURCE_AWARE` is a second research heuristic with the same patient and event
processing order as ASAP. Its local decision asks which currently feasible
opportunity has the strongest resource availability without abandoning the
intended timing region.

The timing region is selected first:

1. if one or more candidates are inside the preferred window, only those
   candidates are active;
2. if none are inside it, every feasible late candidate enters a fallback
   region.

Within that timing region, standard-capacity candidates form the first capacity
region whenever any exist. Their resource score is current remaining standard
capacity. If the region contains only overbooking candidates, their score is
current remaining total capacity. This prevents a large overbooking allowance
from displacing an available normal-capacity opportunity merely because its
total appears larger.

The public fixture has one quantitatively consumed capacity resource per exact
appointment opportunity, so this current opportunity capacity is the public
bottleneck measure. The policy does not invent unsupported multidimensional
resources. The score can later generalize to the minimum remaining capacity
across multiple represented requirements.

The selection order is:

```text
highest current resource score
→ earliest date
→ standard before overbooking
→ agenda_id
→ clinician_id
→ schedule_key
→ opportunity_id
```

Capacity is read from current candidates at each event. It is not precomputed:
an earlier assignment can reduce a score and change the resource or date chosen
for a later patient.

Illustrative policy-differentiation fixture:

```text
Candidate A: earlier, capacity = 1
Candidate B: slightly later, capacity = 4

ASAP           → Candidate A
RESOURCE_AWARE → Candidate B
```

This is a controlled unit-test example, not an empirical result. The heuristic
remains greedy and forward-only: it does not simulate future patients, reserve
capacity for known demand, backtrack, or solve a global optimization problem.

Each resource-aware assignment also records compact diagnostics: total and
preferred-window candidate counts, selected timing region, selected and best
resource score, date, and opportunity identifier.

## Method roles

| Method | Role | Candidate principle | Lookahead |
|---|---|---|---|
| `APPLIED_SEQUENTIAL` | Applied baseline | External/interchangeable decision rule | None |
| `ASAP` | Research heuristic | Earliest feasible | None |
| `RESOURCE_AWARE` | Research heuristic | Best current bottleneck/resource availability within timing region | Local |
| `MILP` | Deterministic optimization model | Global optimization | Global/offline |

## Shared feasibility

Both methods use the same scheduling-state and sequential progression
interfaces. The research layer does not duplicate:

- patient routes, branches, joins, or dependency eligibility;
- minimum spacing or preferred-window calculations;
- resource compatibility and alternative-resource behavior;
- blocked, standard, or overbooking capacity semantics;
- candidate generation, exact opportunity consumption, or pending propagation.

Only candidate-selection policy identity and rule differ. This shared feasibility
contract is what makes comparison with other heuristics and mathematical
optimization fair.

## Common metrics

Metrics are computed after a policy run by one policy-independent function.

Assignment and route completion:

```text
assignment_rate = assigned_events / total_events
route_completion_rate = fully_completed_routes / total_routes
```

A route is fully completed when every event is assigned, partially completed
when it has both assigned and unresolved events, and unresolved when it has no
assignments.

For every assigned event:

```text
tardiness_days = max(assigned_date - preferred_latest_date, 0)
total_tardiness_days = sum(tardiness_days)
mean_tardiness_days = total_tardiness_days / assigned_events
```

The mean includes assignments with zero tardiness. `max_tardiness_days` is the
largest event value, and:

```text
late_assignment_rate = late_assignments / assigned_events
```

Capacity metrics remain separate from timing metrics:

```text
overbooking_rate = overbooking_assignments / assigned_events
```

The metrics also report standard assignments, overbooking assignments, used
capacity, and remaining capacity. Rates are zero when their denominator is
zero. No artificial combined score is constructed.

## Experimental isolation

`run_experiment_case` calls an initial-state factory once per policy. It requires
the returned states to be distinct objects and logically equivalent before
execution. A completed policy result is never passed to another method. This
prevents assignment and capacity usage from leaking between policies.

`comparison_table` formats common metrics outside policy code. The three policies
receive distinct, equivalent initial states. The five-seed
runner regenerates each artificial instance, preprocesses it once, creates fresh
equivalent initial states, runs both methods, and computes descriptive policy
means. Repeated seeds are rejected, and the same seeds and code reproduce the
same cases, traces, tables, and aggregates.

## Synthetic scenarios

> Public experiments use artificial synthetic scenarios designed for software demonstration and reproducibility. They are not statistically calibrated representations of the original operational data.

The default five seeds demonstrate the experimental architecture. They are not
empirical validation, do not support statistical inference, and do not establish
policy superiority. No significance tests, confidence intervals, plots, or
benchmark claims are included at this stage.

## Reproducible examples

After installing the project:

```bash
python examples/compare_applied_vs_asap.py
python examples/compare_research_policies.py
python examples/run_research_demo.py
```

Both examples print aggregate metrics only. They do not print patient-level
schedules.
