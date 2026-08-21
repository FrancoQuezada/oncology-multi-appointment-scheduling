"""Build the seed-42 MILP and solve it only when Gurobi is usable."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from appointment_scheduling.optimization import (
    build_deterministic_problem,
    formulate_deterministic_milp,
)
from appointment_scheduling.optimization.solvers import (
    gurobi_environment_info,
    solve_deterministic_milp,
)
from appointment_scheduling.preprocessing import preprocess_supply
from appointment_scheduling.routes import preprocess_routes
from appointment_scheduling.scheduling import build_scheduling_state


def main() -> None:
    demo = Path(__file__).resolve().parents[1] / "data" / "demo"
    routes = preprocess_routes(pd.read_csv(demo / "routes.csv"))
    availability = preprocess_supply(
        pd.read_csv(demo / "supply.csv"),
        pd.read_csv(demo / "blocks.csv"),
        pd.read_csv(demo / "resource_mapping.csv"),
    ).availability
    state = build_scheduling_state(
        routes,
        availability,
        {patient_id: date(2035, 1, 1) for patient_id in routes.routes_by_patient},
    )
    formulation = formulate_deterministic_milp(build_deterministic_problem(state))
    stats = formulation.statistics
    print(
        "model",
        {
            "patients": stats.patients,
            "events": stats.events,
            "opportunities": stats.opportunities,
            "x": stats.compatible_assignment_variables,
            "y": stats.alternative_variables,
            "timing": stats.continuous_timing_variables,
            "constraints": stats.total_constraints,
        },
    )

    environment = gurobi_environment_info()
    print(
        "gurobi",
        {
            "installed": environment.installed,
            "version": environment.version,
            "license_available": environment.license_available,
        },
    )
    if not environment.license_available:
        print("solve skipped: optional Gurobi license is unavailable")
        return

    result = solve_deterministic_milp(formulation)
    print(
        "result",
        {
            "status": result.status.value,
            "objective": result.objective_value,
            "timing_penalty": result.timing_penalty,
            "alternative_penalty": result.alternative_penalty,
            "assigned_events": (
                result.shared_metrics.assigned_events
                if result.shared_metrics is not None
                else None
            ),
            "pending_events": (
                result.shared_metrics.pending_events
                if result.shared_metrics is not None
                else None
            ),
        },
    )


if __name__ == "__main__":
    main()
