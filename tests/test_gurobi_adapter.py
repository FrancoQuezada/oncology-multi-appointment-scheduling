import sys
import os
import subprocess
from pathlib import Path

import pytest

from appointment_scheduling.optimization import (
    GurobiConfig,
    OptimizationStatus,
    build_deterministic_problem,
    formulate_deterministic_milp,
)
from appointment_scheduling.optimization.solvers import (
    GurobiUnavailableError,
    gurobi_environment_info,
    historical_gurobi_config,
    solve_deterministic_milp,
)
from appointment_scheduling.optimization.solvers.gurobi import _status_from_gurobi


def test_public_optimization_import_is_solver_lazy() -> None:
    source = Path(__file__).resolve().parents[1] / "src"
    code = "import appointment_scheduling.optimization, sys; assert 'gurobipy' not in sys.modules"
    completed = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "PYTHONPATH": str(source)},
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_environment_info_distinguishes_package_and_license() -> None:
    info = gurobi_environment_info()

    assert isinstance(info.installed, bool)
    assert isinstance(info.license_available, bool)
    assert info.license_available is False or info.installed is True


def test_public_defaults_are_lightweight() -> None:
    config = GurobiConfig()

    assert config.time_limit_seconds == 60
    assert config.seed == 123
    assert config.cuts is None


def test_historical_settings_require_explicit_opt_in() -> None:
    config = historical_gurobi_config()

    assert config.time_limit_seconds == 11_400
    assert config.seed == 123
    assert config.cuts == 0


def test_status_mapping_keeps_time_limit_with_incumbent_distinct() -> None:
    class Constants:
        OPTIMAL = 1
        TIME_LIMIT = 2
        INFEASIBLE = 3
        UNBOUNDED = 4
        INF_OR_UNBD = 5

    class FakeGP:
        GRB = Constants

    model = type("Model", (), {"Status": 2, "SolCount": 1})()
    assert _status_from_gurobi(FakeGP, model) is OptimizationStatus.TIME_LIMIT_WITH_INCUMBENT


def test_status_mapping_keeps_time_limit_without_incumbent_distinct() -> None:
    class Constants:
        OPTIMAL = 1
        TIME_LIMIT = 2
        INFEASIBLE = 3
        UNBOUNDED = 4
        INF_OR_UNBD = 5

    class FakeGP:
        GRB = Constants

    model = type("Model", (), {"Status": 2, "SolCount": 0})()
    assert _status_from_gurobi(FakeGP, model) is OptimizationStatus.TIME_LIMIT_WITHOUT_INCUMBENT


@pytest.mark.parametrize(
    ("raw_status", "expected"),
    [
        (3, OptimizationStatus.INFEASIBLE),
        (4, OptimizationStatus.UNBOUNDED),
        (5, OptimizationStatus.INFEASIBLE_OR_UNBOUNDED),
        (99, OptimizationStatus.NO_SOLUTION),
    ],
)
def test_terminal_statuses_are_reported_honestly(raw_status, expected) -> None:
    class Constants:
        OPTIMAL = 1
        TIME_LIMIT = 2
        INFEASIBLE = 3
        UNBOUNDED = 4
        INF_OR_UNBD = 5

    class FakeGP:
        GRB = Constants

    model = type("Model", (), {"Status": raw_status, "SolCount": 0})()
    assert _status_from_gurobi(FakeGP, model) is expected


def test_one_event_known_optimum_with_gurobi_when_licensed(
    milp_state_factory,
) -> None:
    info = gurobi_environment_info()
    if not info.license_available:
        pytest.skip(info.message)
    state = milp_state_factory(
        ((1, "EVENT-Z1", (), 0, 0),),
        (("EVENT-Z1", 1, 1, 1),),
    )
    formulation = formulate_deterministic_milp(
        build_deterministic_problem(state)
    )

    result = solve_deterministic_milp(
        formulation,
        config=GurobiConfig(time_limit_seconds=10),
    )

    assert result.status is OptimizationStatus.OPTIMAL
    assert result.objective_value == pytest.approx(0)
    assert result.timing_penalty == pytest.approx(0)
    assert result.alternative_penalty == pytest.approx(0)
