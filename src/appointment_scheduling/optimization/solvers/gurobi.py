"""Optional, lazily imported Gurobi adapter for the deterministic formulation."""

from __future__ import annotations

import importlib

from appointment_scheduling.optimization.deterministic import (
    build_deterministic_problem,
    build_state_from_milp_incumbent,
    optimization_result_to_research_result,
)
from appointment_scheduling.optimization.formulation import (
    eta_key,
    fi_key,
    formulate_deterministic_milp,
    x_key,
    y_key,
)
from appointment_scheduling.optimization.models import (
    ConstraintSense,
    DeterministicMILPFormulation,
    DeterministicMILPResult,
    DeterministicSchedulingProblem,
    GurobiConfig,
    GurobiEnvironmentInfo,
    OptimizationStatus,
    VariableKind,
)
from appointment_scheduling.research.experiments.metrics import compute_policy_metrics
from appointment_scheduling.research.models import ResearchSchedulingResult
from appointment_scheduling.scheduling import SchedulingState
from appointment_scheduling.optimization.validation import validate_formulation


class GurobiUnavailableError(RuntimeError):
    """Raised when Gurobi or a usable license is unavailable."""


def _import_gurobi():
    try:
        return importlib.import_module("gurobipy")
    except ImportError as exc:
        raise GurobiUnavailableError(
            "gurobipy is not installed; install the optional optimization dependency"
        ) from exc


def gurobi_environment_info() -> GurobiEnvironmentInfo:
    """Report package/version/license availability without credential details."""

    try:
        gp = _import_gurobi()
    except GurobiUnavailableError:
        return GurobiEnvironmentInfo(False, None, False, "gurobipy is not installed")
    version = ".".join(str(value) for value in gp.gurobi.version())
    environment = None
    try:
        environment = gp.Env(empty=True)
        environment.setParam("OutputFlag", 0)
        environment.start()
    except Exception:
        return GurobiEnvironmentInfo(
            True,
            version,
            False,
            "gurobipy is installed, but no usable license is available",
        )
    finally:
        if environment is not None:
            environment.dispose()
    return GurobiEnvironmentInfo(True, version, True, "Gurobi is available")


def historical_gurobi_config() -> GurobiConfig:
    """Return explicit historical experiment settings; never used by default."""

    return GurobiConfig(
        time_limit_seconds=11_400.0,
        seed=123,
        threads=1,
        mip_gap=0.0,
        output_flag=0,
        cuts=0,
    )


def _status_from_gurobi(gp, model) -> OptimizationStatus:
    has_incumbent = model.SolCount > 0
    if model.Status == gp.GRB.OPTIMAL:
        return OptimizationStatus.OPTIMAL
    if model.Status == gp.GRB.TIME_LIMIT:
        return (
            OptimizationStatus.TIME_LIMIT_WITH_INCUMBENT
            if has_incumbent
            else OptimizationStatus.TIME_LIMIT_WITHOUT_INCUMBENT
        )
    if model.Status == gp.GRB.INFEASIBLE:
        return OptimizationStatus.INFEASIBLE
    if model.Status == gp.GRB.UNBOUNDED:
        return OptimizationStatus.UNBOUNDED
    if model.Status == gp.GRB.INF_OR_UNBD:
        return OptimizationStatus.INFEASIBLE_OR_UNBOUNDED
    if has_incumbent:
        return OptimizationStatus.FEASIBLE_INCUMBENT
    return OptimizationStatus.NO_SOLUTION


def solve_deterministic_milp(
    formulation: DeterministicMILPFormulation | DeterministicSchedulingProblem,
    *,
    config: GurobiConfig | None = None,
) -> DeterministicMILPResult:
    """Solve a validated formulation and translate any incumbent safely."""

    if isinstance(formulation, DeterministicSchedulingProblem):
        formulation = formulate_deterministic_milp(formulation)
    validate_formulation(formulation)
    gp = _import_gurobi()
    config = config or GurobiConfig()
    if config.time_limit_seconds <= 0:
        raise ValueError("time_limit_seconds must be positive")
    if config.threads <= 0:
        raise ValueError("threads must be positive")
    if not 0 <= config.mip_gap <= 1:
        raise ValueError("mip_gap must be between zero and one")

    environment = None
    model = None
    try:
        environment = gp.Env(empty=True)
        environment.setParam("OutputFlag", config.output_flag)
        environment.start()
        model = gp.Model("deterministic_multi_appointment", env=environment)
        model.Params.TimeLimit = config.time_limit_seconds
        model.Params.Seed = config.seed
        model.Params.Threads = config.threads
        model.Params.MIPGap = config.mip_gap
        model.Params.OutputFlag = config.output_flag
        if config.cuts is not None:
            model.Params.Cuts = config.cuts

        solver_variables = {}
        for variable in formulation.variables:
            variable_type = (
                gp.GRB.BINARY
                if variable.kind is VariableKind.BINARY
                else gp.GRB.CONTINUOUS
            )
            solver_variables[variable.key] = model.addVar(
                lb=variable.lower_bound,
                ub=(gp.GRB.INFINITY if variable.upper_bound is None else variable.upper_bound),
                obj=variable.objective_coefficient,
                vtype=variable_type,
                name=variable.name,
            )
        model.ModelSense = gp.GRB.MINIMIZE
        model.update()
        for constraint in formulation.constraints:
            expression = gp.LinExpr(
                [term.coefficient for term in constraint.terms],
                [solver_variables[term.variable_key] for term in constraint.terms],
            )
            if constraint.sense is ConstraintSense.EQUAL:
                relation = expression == constraint.right_hand_side
            elif constraint.sense is ConstraintSense.LESS_EQUAL:
                relation = expression <= constraint.right_hand_side
            else:
                relation = expression >= constraint.right_hand_side
            model.addConstr(relation, name=constraint.name)
        model.optimize()

        status = _status_from_gurobi(gp, model)
        has_incumbent = model.SolCount > 0
        selected = {}
        penalized = ()
        eta_values = {}
        fi_values = {}
        final_state = None
        shared_metrics = None
        timing_penalty = None
        alternative_penalty = None
        objective_value = None
        mip_gap = None
        if has_incumbent:
            for option in formulation.problem.assignment_options:
                if solver_variables[x_key(option.event_key, option.opportunity_id)].X > 0.5:
                    selected[option.event_key] = option.opportunity_id
            penalized = tuple(
                event.key
                for event in formulation.problem.events
                if solver_variables[y_key(event.key)].X > 0.5
            )
            eta_values = {
                event.key: float(solver_variables[eta_key(event.key)].X)
                for event in formulation.problem.events
            }
            fi_values = {
                event.key: float(solver_variables[fi_key(event.key)].X)
                for event in formulation.problem.events
            }
            timing_penalty = sum(fi_values.values())
            alternative_penalty = formulation.problem.penalty_M * len(penalized)
            objective_value = float(model.ObjVal)
            if abs(objective_value - timing_penalty - alternative_penalty) > 1e-5:
                raise RuntimeError(
                    "Solver objective does not match sum(fi) + penalty_M * sum(y)"
                )
            mip_gap = float(model.MIPGap)
            final_state = build_state_from_milp_incumbent(
                formulation.problem, selected, penalized
            )
            shared_metrics = compute_policy_metrics(final_state, ())

        bound = None
        if status in {
            OptimizationStatus.OPTIMAL,
            OptimizationStatus.TIME_LIMIT_WITH_INCUMBENT,
            OptimizationStatus.TIME_LIMIT_WITHOUT_INCUMBENT,
            OptimizationStatus.FEASIBLE_INCUMBENT,
        }:
            try:
                bound = float(model.ObjBound)
            except (AttributeError, gp.GurobiError):
                bound = None
        return DeterministicMILPResult.create(
            status=status,
            solver_name="Gurobi",
            solver_version=".".join(str(value) for value in gp.gurobi.version()),
            runtime_seconds=float(model.Runtime),
            objective_value=objective_value,
            best_bound=bound,
            mip_gap=mip_gap,
            timing_penalty=timing_penalty,
            alternative_penalty=alternative_penalty,
            penalized_events=penalized,
            assignment_opportunity_by_event=selected,
            eta_by_event=eta_values,
            fi_by_event=fi_values,
            final_state=final_state,
            shared_metrics=shared_metrics,
            model_statistics=formulation.statistics,
        )
    except GurobiUnavailableError:
        raise
    except gp.GurobiError as exc:
        raise GurobiUnavailableError(
            "Gurobi could not start or solve; verify that a usable license is configured"
        ) from exc
    finally:
        if model is not None:
            model.dispose()
        if environment is not None:
            environment.dispose()


def run_deterministic_milp_policy(
    initial_state: SchedulingState,
    *,
    penalty_M: float = 200.0,
    config: GurobiConfig | None = None,
) -> DeterministicMILPResult:
    """Build and solve one state, suitable for explicit experiment opt-in."""

    problem = build_deterministic_problem(initial_state, penalty_M=penalty_M)
    return solve_deterministic_milp(
        formulate_deterministic_milp(problem),
        config=config,
    )


def run_deterministic_milp_research_policy(
    initial_state: SchedulingState,
) -> ResearchSchedulingResult:
    """Opt-in adapter for the existing experiment runner's policy contract."""

    return optimization_result_to_research_result(
        run_deterministic_milp_policy(initial_state)
    )
