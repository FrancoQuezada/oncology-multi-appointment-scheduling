# Deterministic MILP

## Scope

The deterministic model is an offline research baseline built over the same
synthetic patient routes, resource opportunities, timing parameters, and
capacity semantics as the applied sequential workflow. It does not replace
that workflow: it sees the complete finite horizon at once and jointly selects
event outcomes, whereas the applied scheduler progresses event by event.

The core model is solver-independent. `build_deterministic_problem` creates
validated immutable problem data and `formulate_deterministic_milp` creates
typed variables and linear constraints. Gurobi is an optional adapter imported
only when its solver module is used.

## Sets and parameters

- `E`: patient-event pairs `(patient_id, event_number)`.
- `O`: exact preprocessed supply opportunities.
- `O(e)`: sparse resource-compatible opportunities for event `e` with usable
  capacity and an allowed capacity tier.
- `A`: all dependency arcs `i -> j`, including every incoming arc at joins.
- `D`: regular calendar days from the first through last public opportunity.
- `POST_HORIZON`: the explicit penalized outcome outside `D`.
- `a(e)`: the patient's route-start day for a root event.
- `l(o)`: zero-based day index of opportunity `o`.
- `m(e)`: hard minimum spacing for event `e`.
- `p(e)`: soft preferred maximum spacing for event `e`.
- `c(o)` and `c_std(o)`: total and standard capacity after blocking.
- `M`: exposed penalty for a `POST_HORIZON` outcome; the public default `200`
  preserves the scale of the historical experiment and is not presented as a
  universally calibrated value.

## Variables

- `x[e,o]` is binary and selects compatible internal opportunity `o` for
  event `e`. Impossible event-opportunity combinations are never created.
- `y[e]` is binary and selects the single explicit `POST_HORIZON` outcome.
- `eta[e]` is the realized waiting/spacing duration. For a root it is measured
  from route start. For a dependent event it is measured from the latest
  realized predecessor.
- `fi[e]` is nonnegative preferred-window tardiness.

For joins, a continuous reference and binary selectors encode the exact
maximum realized predecessor date. These are formulation auxiliaries, not a
second route representation.

## Objective

The model minimizes

$$
\min \quad \sum_{e \in E} f_e + M\sum_{e \in E} y_e.
$$

The result reports the two terms independently as `timing_penalty` and
`alternative_penalty`, as well as their combined objective. No arbitrary cost
is attached to standard versus overbooking capacity.

## Constraints

### One outcome per event

$$
\sum_{o \in O(e)} x_{eo} + y_e = 1 \qquad \forall e \in E.
$$

An event with no compatible internal opportunity therefore remains explicit
through `POST_HORIZON`; it never disappears from the model.

### Root arrival and timing

An internally assigned root cannot precede route start plus its minimum
spacing. Its `eta` is the assigned day minus route start:

$$
\eta_e = \sum_{o \in O(e)} (\ell_o-a_e)x_{eo}, \qquad
\eta_e \ge m_e(1-y_e).
$$

### Dependency timing

For every arc `i -> j`, an internal successor satisfies:

$$
\sum_{o \in O(j)}\ell_o x_{jo}
- \sum_{o \in O(i)}\ell_o x_{io}
+ B y_j \ge m_j
\qquad \forall (i,j) \in A,
$$

If a predecessor is assigned `POST_HORIZON`, every downstream successor is
also propagated to that outcome. For a join, `eta[j]` uses
`max(date(i) for i in predecessors(j))`, matching the shared public timing
semantics.

### Preferred maximum

For an internal outcome:

$$
f_e \ge \eta_e-p_e, \qquad f_e \ge 0.
$$

The preferred maximum is deliberately soft. It is not a hard deadline and
does not remove a late but feasible opportunity.

### Capacity and overbooking

Assignments are indexed by exact opportunity. Total assignments cannot exceed
post-blocking total capacity:

$$
\sum_{e:o\in O(e)}x_{eo}\le c_o.
$$

Events that disallow overbooking also satisfy

$$
\sum_{e:o\in O(e),\;e\text{ disallows overbooking}}x_{eo}
\le c^{std}_o.
$$

Translation assigns standard capacity before the overbooking tier and validates
the result with the shared scheduling state. This two-limit treatment is an
explicit clean public extension: it retains the historical research model's
use of permitted total internal capacity while preserving the applied layer's
per-event overbooking permission.

## Historical fidelity and intentional corrections

The public formulation preserves the historical conceptual structure:
binary `x` assignment variables, penalized alternative `y` variables,
root/dependent duration `eta`, tardiness `fi`, dependency timing, opportunity
capacity, and the objective `sum(fi) + M sum(y)`. The original research work
used Gurobi with a seed of `123`, a long limit of roughly `11,400` seconds, and
cuts disabled in at least one experiment configuration.

Those expensive settings are available only through
`historical_gurobi_config()` and are never automatic. Public defaults use one
thread and a 60-second limit.

The clean-room version intentionally makes several semantics more explicit:

- the finite-horizon fallback is one `POST_HORIZON` outcome per event rather
  than pretending that an internal slot exists;
- every DAG arc is enforced, including joins;
- the join reference is the exact latest predecessor;
- missing compatible opportunities remain modeled through `y`;
- standard and total capacities are distinct, with no invented overbooking
  objective penalty;
- solver status distinguishes optimality, feasible time-limit incumbents,
  time limits without incumbents, infeasibility, and unboundedness.

## Optional Gurobi installation

Install the project and optional adapter with:

```bash
python -m pip install -e ".[dev,optimization]"
```

`gurobipy` also requires a separately configured usable Gurobi license. Use
`gurobi_environment_info()` to distinguish a missing package from an unusable
license without disclosing license details. Importing
`appointment_scheduling.optimization` does not import `gurobipy`.

## Small known fixture and comparison readiness

The test suite includes a two-event artificial chain. Its only all-internal
outcome schedules the root at day 0 and its successor three days later, against
a preferred spacing of two days, so `eta=(0,3)`, `fi=(0,1)`, and objective `1`.
An all-`POST_HORIZON` outcome has objective `400` at the default penalty.

Solved incumbents translate into the same immutable `SchedulingState` and
common `PolicyMetrics` used by `APPLIED_SEQUENTIAL`, `ASAP`, and
`RESOURCE_AWARE`. `run_deterministic_milp_research_policy` is an explicit
experiment-runner adapter. It is not included in the default five-seed suite,
so installing or licensing a commercial solver is never required for ordinary
research demonstrations.

All pathway and supply examples are artificial software fixtures. They do not
reproduce real patient pathways, clinical protocols, treatment recommendations,
staff schedules, or institutional capacity values.
