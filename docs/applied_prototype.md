# Applied Prototype

This document describes the historical applied scheduling prototype developed
with Fundación Arturo López Pérez (FALP) at a conceptual level, and how each part
of it maps to the public reconstruction in this repository. No confidential
values, institutional identifiers, or real operational figures are reproduced
anywhere below.

## Demand and route extraction

**Historical implementation concept.** A patient's expected care route was not
entered from a fixed protocol; it was derived statistically from that patient's
own history of past appointments. Past appointments were grouped by patient,
ordered chronologically, and converted into consecutive (previous visit type,
next visit type, day gap) observations. Gaps for the same visit-type transition
were pooled across patients to obtain an empirical distribution, from which a
typical, minimum, and maximum spacing was derived for each step of a route.

**Public-safe reconstruction.** `routes/` accepts route records with explicit
`min_spacing_days` and `preferred_max_spacing_days` fields and validates them
into an immutable per-patient dependency graph. The statistical derivation step
itself — computing spacing from historical logs — is not reconstructed, since it
has no meaning without real historical data; the repository instead documents
the resulting route *representation* that step fed into.

## Resource and supply preprocessing

**Historical implementation concept.** Medical-resource availability was
computed by combining three sources: raw physician schedule offers, a table of
blocked/unavailable time, and a directory mapping physicians to service,
section, and center. Offer blocks were classified by attention modality from
free-text labels, split between new-patient and follow-up capacity when a block
served both, and netted against blocked time to obtain remaining capacity.

**Public-safe reconstruction.** `preprocessing/` implements the same net-capacity
logic against three synthetic input tables (supply, blocks, resource mapping):
join validation, capacity aggregation, blocked-capacity netting, and a standard
versus overbooking capacity split. See
[`supply_preprocessing.md`](supply_preprocessing.md) for the exact contract.

## Blockages and capacity

**Historical implementation concept.** Blocked capacity represented time an
agenda could not be used (holidays, reserved administrative time, and similar
operational reasons) and was always netted out before computing what remained
schedulable. Overbooking represented additional capacity usable only after
standard capacity was exhausted.

**Public-safe reconstruction.** The same standard/overbooking/blocked
distinction is implemented explicitly as typed capacity fields and enforced
invariants (standard capacity consumed first; overbooking never exceeds total;
blocked capacity applied before scheduling).

## Sequential appointment allocation

**Historical implementation concept.** Appointments were allocated one route
event at a time. Before assigning an event, its route dependency was checked —
if a prerequisite appointment was itself unresolved, the event was marked
unresolved too rather than assigned out of order. Available capacity was
filtered by required service, section, physician, and modality, and by a
timing window derived from the patient's prior appointment date.

**Public-safe reconstruction.** `scheduling/` and `schedulers/` implement the
same dependency-eligibility check, timing-window computation, and resource
filtering, exposed as a feasibility engine (`scheduling/`) driving a forward-only
sequential workflow (`schedulers/`). See
[`scheduling_state.md`](scheduling_state.md) and
[`sequential_scheduler.md`](sequential_scheduler.md).

## Operator decision support

**Historical implementation concept.** The historical tool was not a fully
automated optimizer. For each event, it proposed candidate dates (typically, the
soonest available date and the date with the most remaining capacity) and a
human operator confirmed one, declined it, or requested another option. Nothing
was booked without that confirmation step.

**Public-safe reconstruction.** The sequential scheduler exposes a typed
`DecisionRule` boundary: it computes and presents every currently feasible
candidate, and a decision rule chooses (or defers) an outcome, without the core
package reading interactive input itself. This preserves the possibility of a
human-facing decision rule without embedding a command-line interaction loop in
the reusable logic. The bundled example rule (earliest-feasible) is a
demonstration choice, not a claim about how the historical tool actually chose
between candidates.

## Capacity consumption and unresolved appointments

**Historical implementation concept.** Confirming an appointment reduced the
remaining capacity of the specific schedule block used. If dependency,
resource, or capacity constraints left no valid candidate, the event was
explicitly recorded as unresolved ("Pendiente") rather than silently dropped or
retried indefinitely.

**Public-safe reconstruction.** `assign_event` consumes exactly one unit from
exactly one immutable availability opportunity and returns a new state
snapshot; `mark_pending` records an explicit, enumerated pending reason
(`HORIZON_EXCEEDED`, `NO_FEASIBLE_CAPACITY`, `PREDECESSOR_PENDING`). This is a
direct reconstruction of the historical unresolved-appointment concept, using
an exact-opportunity capacity key rather than the historical prototype's
broader row-matching updates.

## What was not reconstructed

The historical project also included a menu-driven, interactive command-line
tool for manually entering or editing a patient's route when statistical
derivation from logs was not applicable. This was operational data-entry
tooling, not a scheduling method, and it is not part of this public
reconstruction.
