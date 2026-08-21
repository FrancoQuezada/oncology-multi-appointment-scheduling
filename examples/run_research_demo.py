"""Run the five-seed synthetic research infrastructure demonstration."""

from appointment_scheduling.research import (
    aggregate_table,
    policy_differentiation,
    run_multi_seed_experiment,
)


def main() -> None:
    comparison = run_multi_seed_experiment(seeds=(42, 43, 44, 45, 46))

    print("Five-seed synthetic policy means")
    print(aggregate_table(comparison).to_string())
    differences = policy_differentiation(comparison)
    print(
        "\nASAP vs RESOURCE_AWARE: "
        f"{differences.instances_with_different_final_assignments} instances with "
        "different final assignments; "
        f"{differences.decision_steps_differing} differing decision steps."
    )
    print("\nInterpretation: reproducibility demonstration only; no superiority claim.")


if __name__ == "__main__":
    main()
