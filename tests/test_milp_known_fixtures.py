from appointment_scheduling.optimization import (
    build_deterministic_problem,
    evaluate_milp_incumbent,
    formulate_deterministic_milp,
)


def _opportunity_ids(state):
    return {item.event_type: item.opportunity_id for item in state.opportunities}


def test_one_event_one_slot_has_zero_objective(milp_state_factory) -> None:
    state = milp_state_factory(
        ((1, "EVENT-Z1", (), 0, 0),),
        (("EVENT-Z1", 1, 1, 1),),
    )
    event_key = ("PAT-921", 1)
    result = evaluate_milp_incumbent(
        build_deterministic_problem(state),
        {event_key: _opportunity_ids(state)["EVENT-Z1"]},
        (),
    )

    assert result.objective_value == 0
    assert result.shared_metrics.assigned_events == 1


def test_earlier_slot_has_less_tardiness(milp_state_factory) -> None:
    state = milp_state_factory(
        ((1, "EVENT-Z1", (), 0, 0),),
        (("EVENT-Z1", 1, 1, 1), ("EVENT-Z1", 2, 1, 1)),
    )
    problem = build_deterministic_problem(state)
    options = sorted(state.opportunities, key=lambda item: item.date)
    early = evaluate_milp_incumbent(
        problem, {("PAT-921", 1): options[0].opportunity_id}, ()
    )
    late = evaluate_milp_incumbent(
        problem, {("PAT-921", 1): options[1].opportunity_id}, ()
    )

    assert early.objective_value == 0
    assert late.objective_value == 1


def test_capacity_competition_requires_one_penalized_outcome(
    milp_state_factory,
) -> None:
    state = milp_state_factory(
        ((1, "EVENT-Z1", (), 0, 0),),
        (("EVENT-Z1", 1, 1, 1),),
        patients=2,
    )
    opportunity = state.opportunities[0].opportunity_id
    evaluation = evaluate_milp_incumbent(
        build_deterministic_problem(state),
        {("PAT-921", 1): opportunity},
        (("PAT-922", 1),),
    )

    assert evaluation.shared_metrics.assigned_events == 1
    assert evaluation.shared_metrics.pending_events == 1
    assert evaluation.alternative_penalty == 200
    assert evaluation.objective_value == 200


def test_dependency_fixture_respects_minimum_spacing(milp_state_factory) -> None:
    state = milp_state_factory(
        (
            (1, "EVENT-Z1", (), 0, 0),
            (2, "EVENT-Z2", (1,), 2, 2),
        ),
        (("EVENT-Z1", 1, 1, 1), ("EVENT-Z2", 3, 1, 1)),
    )
    ids = _opportunity_ids(state)
    evaluation = evaluate_milp_incumbent(
        build_deterministic_problem(state),
        {("PAT-921", 1): ids["EVENT-Z1"], ("PAT-921", 2): ids["EVENT-Z2"]},
        (),
    )

    assert evaluation.eta_by_event[("PAT-921", 2)] == 2
    assert evaluation.objective_value == 0


def test_join_fixture_uses_latest_of_both_predecessors(milp_state_factory) -> None:
    state = milp_state_factory(
        (
            (1, "EVENT-Z1", (), 0, 1),
            (2, "EVENT-Z2", (), 0, 1),
            (3, "EVENT-Z3", (1, 2), 2, 2),
        ),
        (
            ("EVENT-Z1", 1, 1, 1),
            ("EVENT-Z2", 2, 1, 1),
            ("EVENT-Z3", 4, 1, 1),
        ),
    )
    ids = _opportunity_ids(state)
    evaluation = evaluate_milp_incumbent(
        build_deterministic_problem(state),
        {
            ("PAT-921", 1): ids["EVENT-Z1"],
            ("PAT-921", 2): ids["EVENT-Z2"],
            ("PAT-921", 3): ids["EVENT-Z3"],
        },
        (),
    )
    formulation = formulate_deterministic_milp(build_deterministic_problem(state))

    assert evaluation.eta_by_event[("PAT-921", 3)] == 2
    assert evaluation.objective_value == 0
    assert sum(variable.family == "latest_selector" for variable in formulation.variables) == 2


def test_no_internal_capacity_selects_explicit_fallback(milp_state_factory) -> None:
    state = milp_state_factory(
        ((1, "EVENT-Z1", (), 0, 0),),
        (("EVENT-UNRELATED", 1, 1, 1),),
    )
    problem = build_deterministic_problem(state)
    formulation = formulate_deterministic_milp(problem)
    evaluation = evaluate_milp_incumbent(problem, {}, (("PAT-921", 1),))

    assert problem.options_by_event[("PAT-921", 1)] == ()
    assert sum(variable.family == "y" for variable in formulation.variables) == 1
    assert evaluation.objective_value == 200
