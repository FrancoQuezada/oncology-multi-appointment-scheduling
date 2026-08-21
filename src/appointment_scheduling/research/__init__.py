"""Public research policies, metrics, and deterministic comparisons."""

from appointment_scheduling.research.experiments import (
    DEFAULT_POLICIES,
    ExperimentIsolationError,
    aggregate_table,
    comparison_table,
    compute_policy_metrics,
    policy_differentiation,
    run_applied_sequential_baseline,
    run_experiment_case,
    run_multi_seed_experiment,
)
from appointment_scheduling.research.models import (
    AggregatePolicyMetrics,
    ExperimentCaseResult,
    ExperimentComparison,
    PolicyMetrics,
    PolicyDifferentiationDiagnostics,
    PolicyName,
    CandidateRegion,
    ResearchOutcome,
    ResearchSchedulingResult,
    ResearchTraceEntry,
    ResourceAwareDecisionDiagnostics,
)
from appointment_scheduling.research.policies import (
    run_asap_policy,
    run_resource_aware_policy,
)

__all__ = [
    "AggregatePolicyMetrics",
    "CandidateRegion",
    "DEFAULT_POLICIES",
    "ExperimentCaseResult",
    "ExperimentComparison",
    "ExperimentIsolationError",
    "PolicyMetrics",
    "PolicyDifferentiationDiagnostics",
    "PolicyName",
    "ResearchOutcome",
    "ResearchSchedulingResult",
    "ResearchTraceEntry",
    "ResourceAwareDecisionDiagnostics",
    "aggregate_table",
    "comparison_table",
    "compute_policy_metrics",
    "policy_differentiation",
    "run_applied_sequential_baseline",
    "run_asap_policy",
    "run_resource_aware_policy",
    "run_experiment_case",
    "run_multi_seed_experiment",
]
