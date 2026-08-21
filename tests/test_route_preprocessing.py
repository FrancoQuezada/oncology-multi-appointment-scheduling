from pathlib import Path

import pandas as pd

from appointment_scheduling.routes import preprocess_routes


ROUTES_PATH = Path(__file__).resolve().parents[1] / "data" / "demo" / "routes.csv"


def _routes() -> pd.DataFrame:
    return pd.read_csv(ROUTES_PATH)


def _structure(route: object) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            event.event_number,
            event.event_id,
            event.dependencies,
            event.min_spacing_days,
            event.preferred_max_spacing_days,
        )
        for event in route.events
    )


def test_canonical_routes_preprocess_successfully() -> None:
    result = preprocess_routes(_routes())

    assert len(result.patient_routes) == 4
    assert len(result.pathway_templates) == 3
    assert result.diagnostics.patients == 4
    assert result.diagnostics.events == 20


def test_all_demo_patients_are_directly_accessible() -> None:
    result = preprocess_routes(_routes())

    assert tuple(result.routes_by_patient) == (
        "PAT-001",
        "PAT-002",
        "PAT-003",
        "PAT-004",
    )
    assert result.route_for("PAT-003").pathway_id == "PATHWAY-C"


def test_dependency_lists_become_immutable_tuples() -> None:
    result = preprocess_routes(_routes())
    joining_event = result.route_for("PAT-001").event(5)

    assert joining_event.dependencies == (2, 3)
    assert isinstance(joining_event.dependencies, tuple)


def test_patient_instances_match_shared_pathway_templates() -> None:
    result = preprocess_routes(_routes())
    first_instance = result.route_for("PAT-001")
    second_instance = result.route_for("PAT-004")

    assert first_instance.pathway_id == second_instance.pathway_id == "PATHWAY-A"
    assert _structure(first_instance) == _structure(second_instance)
    assert first_instance.event(5).clinician_id != second_instance.event(5).clinician_id


def test_preprocessing_does_not_mutate_route_rows() -> None:
    routes = _routes()
    before = routes.copy(deep=True)

    preprocess_routes(routes)

    pd.testing.assert_frame_equal(routes, before)


def test_repeated_preprocessing_is_identical() -> None:
    routes = _routes()

    first = preprocess_routes(routes)
    second = preprocess_routes(routes)

    assert first == second


def test_input_row_order_does_not_change_route_structures() -> None:
    routes = _routes()
    shuffled = routes.sample(frac=1, random_state=17).reset_index(drop=True)

    ordered_result = preprocess_routes(routes)
    shuffled_result = preprocess_routes(shuffled)

    assert ordered_result == shuffled_result


def test_canonical_structural_diagnostics() -> None:
    diagnostics = preprocess_routes(_routes()).diagnostics

    assert diagnostics.patients == 4
    assert diagnostics.routes == 4
    assert diagnostics.events == 20
    assert diagnostics.dependency_arcs == 19
    assert diagnostics.root_events == 4
    assert diagnostics.terminal_events == 6
    assert diagnostics.branch_events == 5
    assert diagnostics.join_events == 3
    assert diagnostics.max_route_depth == 5
