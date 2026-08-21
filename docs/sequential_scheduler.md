# Sequential Applied Scheduler

## Applied workflow

The sequential scheduler reconstructs the public-safe engineering structure of
the applied appointment-scheduling workflow. It progresses through coordinated
patient routes, asks the shared feasibility engine for current alternatives,
applies an explicit decision, consumes capacity through the shared state
transition, and reevaluates downstream eligibility.

Patients are processed deterministically by:

```text
route_start_date, patient_id
```

Within each route, events are visited once in the route graph's deterministic
topological order. This preserves branches and joins: both branches may proceed
after their common predecessor is assigned, while a joining event is not
processed until every required predecessor is assigned.

## Candidate generation

The scheduler does not reproduce dependency, timing, resource, or capacity
logic. It calls `get_candidate_slots` from the shared scheduling-state layer.
The resulting candidates have already passed:

- dependency eligibility;
- the hard minimum-date boundary;
- fixed-resource or compatible-set matching;
- current standard/overbooking capacity checks;
- the event's overbooking permission.

Candidates beyond the preferred maximum remain feasible and retain
`within_preferred_window=False` for trace and outcome metrics.

## Decision rules

Workflow progression and candidate choice are separate interfaces. A
`DecisionRule` receives the current route event, all current candidates, and the
current immutable state. It may return only:

- `SchedulingDecision.assign(candidate)` for an actual current candidate; or
- `SchedulingDecision.pending(...)` with a controlled `PendingReason`.

The included `earliest_feasible_rule` chooses the first candidate from the
feasibility layer's deterministic ordering. It is a small executable demo rule,
not a claim that the sequential workflow intrinsically means earliest-first and
not the later standalone ASAP research algorithm.

Other candidate-selection approaches, including a human-facing adapter, can
use the same protocol without changing route progression or feasibility rules.

## State progression and trace

Assignments are made only through `assign_event`. One accepted decision consumes
one unit from one exact supply opportunity and returns a new state snapshot.
The workflow never edits an availability DataFrame directly.

Each processed event produces a numbered `SchedulingTraceEntry` containing the
patient-event key, status before and after, candidate count, action, selected
opportunity and date, capacity tier, preferred-window annotation, and controlled
pending reason. It contains no operational free text.

The result also reports aggregate assignment, pending, capacity, lateness, and
route-completion metrics. It does not expose patient-level details by default.

## Pending appointments

An eligible event with no candidates is marked:

- `HORIZON_EXCEEDED` when its earliest feasible date lies after all supplied
  availability dates;
- `NO_FEASIBLE_CAPACITY` otherwise.

A decision rule may also explicitly return a controlled pending decision. In a
complete applied run, every downstream event requiring a pending predecessor is
marked `PREDECESSOR_PENDING`. This propagation belongs to the applied scheduler;
the generic state layer continues to represent such events as dependency-blocked
until a workflow deliberately resolves them.

On a branch, an unresolved event does not prevent an independent sibling branch
from being processed. A later join remains unresolved if any required branch is
pending.

## Human-in-the-loop origin

The decision-rule boundary preserves the decision-support character of the
applied work: feasible appointment alternatives can be presented to an operator
and the chosen candidate returned through the same typed interface. Core code
does not read terminal input, and this public repository is not connected to a
healthcare organization or live scheduling system.

## Sequential limitation

The workflow is forward-only. Accepted assignments consume capacity and are not
reconsidered. There is no rescheduling, backtracking, local search, or global
optimization. This is both an operationally meaningful baseline and the
motivation for the heuristic and mathematical-optimization comparisons
documented in [`research_policies.md`](research_policies.md) and
[`deterministic_milp.md`](deterministic_milp.md).

## Research and application bridge

The applied scheduler, the ASAP and resource-aware research policies, and the
deterministic MILP model share the same synthetic instances and feasibility
semantics. This makes comparisons meaningful without maintaining a separate
implementation of dependencies, resource compatibility, timing, or capacity.

The clean-room implementation also uses safer modular boundaries than the
historical prototype: immutable state snapshots, exact opportunity-key capacity
updates, explicit resource modes, controlled pending reasons, and validated
decision objects. These preserve the applied concepts without reproducing
unsafe implementation details.

## Reproducible example

After installing the package, run:

```bash
python examples/run_sequential_demo.py
```

The example loads only the synthetic CSV fixtures and prints an aggregate
summary. It does not print patient-level assignments or candidates.
