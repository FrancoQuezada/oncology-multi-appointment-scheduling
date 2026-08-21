"""Compare all public scheduling methods on the canonical synthetic fixture."""

from datetime import date
from pathlib import Path

import pandas as pd

from appointment_scheduling.preprocessing import preprocess_supply
from appointment_scheduling.research import comparison_table, run_experiment_case
from appointment_scheduling.routes import preprocess_routes
from appointment_scheduling.scheduling import build_scheduling_state


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    data_dir = project_root / "data" / "demo"
    routes = preprocess_routes(pd.read_csv(data_dir / "routes.csv"))
    availability = preprocess_supply(
        pd.read_csv(data_dir / "supply.csv"),
        pd.read_csv(data_dir / "blocks.csv"),
        pd.read_csv(data_dir / "resource_mapping.csv"),
    ).availability
    starts = {
        patient_id: date(2035, 1, 1) for patient_id in routes.routes_by_patient
    }

    def initial_state_factory():
        return build_scheduling_state(routes, availability, starts)

    result = run_experiment_case("synthetic-seed-42", initial_state_factory)
    selected_metrics = (
        "assigned_events",
        "pending_events",
        "assignment_rate",
        "fully_completed_routes",
        "route_completion_rate",
        "late_assignments",
        "total_tardiness_days",
        "mean_tardiness_days",
        "max_tardiness_days",
        "overbooking_assignments",
        "capacity_remaining",
    )
    print("Canonical synthetic three-policy comparison")
    print(comparison_table(result).loc[list(selected_metrics)].to_string())


if __name__ == "__main__":
    main()
