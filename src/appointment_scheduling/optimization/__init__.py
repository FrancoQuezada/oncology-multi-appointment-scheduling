"""Public deterministic optimization API with no mandatory solver import."""

from appointment_scheduling.optimization.deterministic import (
    build_deterministic_problem,
    build_state_from_milp_incumbent,
    evaluate_milp_incumbent,
    optimization_result_to_research_result,
)
from appointment_scheduling.optimization.formulation import (
    formulate_deterministic_milp,
)
from appointment_scheduling.optimization.models import (
    AssignmentOption,
    ConstraintSense,
    DependencyArc,
    DeterministicMILPFormulation,
    DeterministicMILPResult,
    DeterministicSchedulingProblem,
    GurobiConfig,
    GurobiEnvironmentInfo,
    IncumbentEvaluation,
    LinearConstraintSpec,
    LinearTerm,
    ModelStatistics,
    OptimizationEvent,
    OptimizationStatus,
    VariableKind,
    VariableSpec,
)
from appointment_scheduling.optimization.validation import (
    OptimizationValidationError,
    validate_deterministic_problem,
    validate_formulation,
)

__all__ = [
    "AssignmentOption",
    "ConstraintSense",
    "DependencyArc",
    "DeterministicMILPFormulation",
    "DeterministicMILPResult",
    "DeterministicSchedulingProblem",
    "GurobiConfig",
    "GurobiEnvironmentInfo",
    "IncumbentEvaluation",
    "LinearConstraintSpec",
    "LinearTerm",
    "ModelStatistics",
    "OptimizationEvent",
    "OptimizationStatus",
    "OptimizationValidationError",
    "VariableKind",
    "VariableSpec",
    "build_deterministic_problem",
    "build_state_from_milp_incumbent",
    "evaluate_milp_incumbent",
    "formulate_deterministic_milp",
    "optimization_result_to_research_result",
    "validate_deterministic_problem",
    "validate_formulation",
]
