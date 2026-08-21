"""Optional solver adapters. Importing this module does not import Gurobi."""

from appointment_scheduling.optimization.solvers.gurobi import (
    GurobiUnavailableError,
    gurobi_environment_info,
    historical_gurobi_config,
    run_deterministic_milp_policy,
    run_deterministic_milp_research_policy,
    solve_deterministic_milp,
)

__all__ = [
    "GurobiUnavailableError",
    "gurobi_environment_info",
    "historical_gurobi_config",
    "run_deterministic_milp_policy",
    "run_deterministic_milp_research_policy",
    "solve_deterministic_milp",
]
