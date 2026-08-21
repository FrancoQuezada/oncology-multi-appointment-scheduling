# Project context

This document makes the provenance of this repository explicit: what problem the
original project addressed, what was actually built, and how the current public
repository relates to that historical work. It complements the top-level
[`README.md`](../README.md) with more detail than a portfolio front page should
carry.

## Operational challenge

Oncology patients rarely need a single appointment. A typical course of care is a
**route**: an ordered sequence of appointments — consultations, imaging, laboratory
work, procedures, follow-ups — where some appointments cannot be booked until
others have taken place, and all of them compete for the same limited clinical
resources (physicians, agendas, rooms). Scheduling one patient's route well
requires reasoning jointly about dependency order, timing windows, resource
compatibility, and shared, reducible capacity — not about one appointment at a
time in isolation.

## Applied collaboration

The applied part of the project was carried out in collaboration with
**Fundación Arturo López Pérez (FALP)**, a Chilean oncology-care foundation. The
collaboration involved FALP's own operational scheduling data: historical
appointment logs, physician and agenda schedules, blocked-capacity records, and
patient routes derived from that history. The goal was a decision-support
workflow that could take a patient's expected route and FALP's real, current
resource availability and propose a feasible, dependency-respecting sequence of
appointments, with a human operator confirming or adjusting each proposed date.

## Research component

In parallel, the same scheduling problem was formalized as a research
methodology: an ASAP heuristic, a resource-aware heuristic, and a deterministic
mixed-integer linear programming (MILP) model solved with Gurobi. This
methodology is associated with a research manuscript. The research code
generated its own synthetic instances (illustrative pathologies, procedurally
generated patient arrivals and resource capacities) rather than reading FALP's
operational data directly — the connection between the two parts of the project
is conceptual and methodological, not a shared codebase.

## Original implementation

The historical implementation existed as a small collection of standalone Python
scripts, run against real institutional Excel exports:

- a route-extraction script that derived, per patient, an ordered sequence of
  visit types and empirical inter-visit timing statistics from historical
  appointment logs;
- a supply-preprocessing script that combined physician schedule offers,
  blocked-capacity records, and a service/section directory into a net available-
  capacity table, splitting slots between new-patient and follow-up demand and
  classifying attention modality from free-text schedule labels;
- a sequential assignment script that walked a patient's route event by event,
  filtered available capacity by service/section/modality/physician, checked
  dependency prerequisites, and asked a human operator to confirm one of two
  candidate dates (soonest available, or most remaining capacity) for each
  appointment, explicitly marking an appointment "Pendiente" (unresolved) when no
  operator-approved slot existed;
- a menu-driven, interactive data-entry tool for manually building or editing a
  patient's route when automatic derivation from logs was not applicable.

Separately, the research codebase implemented the ASAP and resource-aware
heuristics and the deterministic MILP model against procedurally generated
synthetic instances, using Gurobi as the solver for the MILP.

## Public reconstruction

This public repository is a clean-room reconstruction written after the fact.
None of its source code was copied from the historical scripts, and none of the
historical data files are included, referenced, or statistically approximated.
The reconstruction preserves the computational structure and methodology of both
the applied prototype and the research methods — the same dependency, timing,
resource, and capacity concepts; the same three research methods; the same MILP
objective and constraint families — while replacing every data source with
independently generated synthetic fixtures and refactoring implementation
details that would have been unsafe or unclear to keep (see
[`applied_prototype.md`](applied_prototype.md) for the applied side, and
[`deterministic_milp.md`](deterministic_milp.md) for the optimization side).

The public reconstruction also adds things that did not exist historically:
package structure under `src/appointment_scheduling/`, a synthetic data
generator, a schema/data dictionary, and an automated test suite. These are
software-engineering additions made to document the project safely and are not
themselves part of the historical project.

## Confidentiality boundary

The historical scripts read real FALP operational files: appointment logs with
patient identity fields, physician schedules, blocked-capacity records, and
derived patient routes. Those files, and any value drawn from them, are excluded
from this repository without exception. Every dataset, identifier, date, and
capacity figure in this public repository was generated independently for
software demonstration; none of it was derived from, sampled from, or fit to
FALP's operational data.

## Historical versus reconstructed components

| Component | Historical | Public reconstruction |
|---|---|---|
| Route/periodicity extraction logic | Yes — derived from real appointment logs | Yes — reimplemented against synthetic routes |
| Supply preprocessing logic (capacity, blocking, overbooking) | Yes — ran against real schedule/blocking data | Yes — reimplemented against synthetic supply data |
| Sequential, dependency-aware allocation with operator confirmation | Yes — human-in-the-loop | Yes — reimplemented as a decision-rule interface |
| Manual route data-entry tool | Yes | Not reconstructed |
| ASAP heuristic | Yes — research code | Yes — reimplemented |
| Resource-aware heuristic | Yes — research code | Yes — reimplemented |
| Deterministic MILP (Gurobi) | Yes — research code | Yes — reimplemented formulation, optional solver adapter |
| Immutable state / copy-on-write architecture | No | Yes — public software-engineering improvement |
| Automated regression/validation test suite | No | Yes — public software-engineering addition |
| Synthetic data generator and data dictionary | No | Yes — public software-engineering addition |
| Real institutional data | Yes (confidential) | No — replaced entirely by synthetic fixtures |
