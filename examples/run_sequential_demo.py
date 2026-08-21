"""Run the public synthetic sequential scheduling workflow."""

from dataclasses import fields
from datetime import date
from pathlib import Path

import pandas as pd

from appointment_scheduling.preprocessing import preprocess_supply
from appointment_scheduling.routes import preprocess_routes
from appointment_scheduling.schedulers import run_sequential_scheduler
from appointment_scheduling.scheduling import build_scheduling_state


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    data_dir = project_root / "data" / "demo"
    routes = preprocess_routes(pd.read_csv(data_dir / "routes.csv"))
    supply = preprocess_supply(
        pd.read_csv(data_dir / "supply.csv"),
        pd.read_csv(data_dir / "blocks.csv"),
        pd.read_csv(data_dir / "resource_mapping.csv"),
    )
    route_start_dates = {
        patient_id: date(2035, 1, 1) for patient_id in routes.routes_by_patient
    }
    state = build_scheduling_state(
        routes,
        supply.availability,
        route_start_dates,
    )
    result = run_sequential_scheduler(state)

    print("Sequential scheduling demo summary")
    for field in fields(result.summary):
        print(f"{field.name}: {getattr(result.summary, field.name)}")


if __name__ == "__main__":
    main()
