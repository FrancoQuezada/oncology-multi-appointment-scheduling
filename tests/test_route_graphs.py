from pathlib import Path

import pandas as pd
import pytest

from appointment_scheduling.routes import (
    DependencyValidationError,
    PathwayConsistencyError,
    PathwayEventTemplate,
    PathwayTemplate,
    RouteCycleError,
    RouteValidationError,
    preprocess_routes,
)


ROUTES_PATH = Path(__file__).resolve().parents[1] / "data" / "demo" / "routes.csv"


def _routes() -> pd.DataFrame:
    return pd.read_csv(ROUTES_PATH)


def _target(routes: pd.DataFrame, patient: str, event: int) -> pd.Series:
    return (routes["patient_id"] == patient) & (routes["event_number"] == event)


def test_topological_order_respects_every_arc() -> None:
    result = preprocess_routes(_routes())

    for route in result.patient_routes:
        positions = {
            number: position
            for position, number in enumerate(route.graph.topological_order)
        }
        for event in route.events:
            assert all(
                positions[predecessor] < positions[event.event_number]
                for predecessor in event.dependencies
            )


def test_topological_order_uses_event_number_tie_breaking() -> None:
    result = preprocess_routes(_routes())

    assert result.route_for("PAT-001").graph.topological_order == (1, 2, 3, 4, 5)
    assert result.route_for("PAT-003").graph.topological_order == (1, 2, 3, 4, 5, 6)


def test_roots_and_terminals_support_nonlinear_routes() -> None:
    graph = preprocess_routes(_routes()).route_for("PAT-001").graph

    assert graph.root_events == (1,)
    assert graph.terminal_events == (4, 5)


def test_branches_and_joins_are_explicit() -> None:
    graph = preprocess_routes(_routes()).route_for("PAT-001").graph

    assert graph.branch_events == (1, 2)
    assert graph.join_events == (5,)
    assert graph.successors_of(1) == (2, 3)
    assert graph.predecessors_of(5) == (2, 3)


def test_multiple_roots_are_supported_deterministically() -> None:
    routes = _routes().query("patient_id == 'PAT-002'").iloc[:3].copy()
    routes["patient_id"] = "PAT-099"
    routes["pathway_id"] = "PATHWAY-Z"
    routes["event_id"] = ["EVENT-Z1", "EVENT-Z2", "EVENT-Z3"]
    routes["event_type"] = routes["event_id"]
    routes["dependencies"] = ["[]", "[]", "[1,2]"]
    routes["min_spacing_days"] = [0, 0, 1]
    routes["preferred_max_spacing_days"] = [1, 2, 3]
    template = PathwayTemplate(
        pathway_id="PATHWAY-Z",
        events=(
            PathwayEventTemplate(1, "EVENT-Z1", "EVENT-Z1", (), 0, 1),
            PathwayEventTemplate(2, "EVENT-Z2", "EVENT-Z2", (), 0, 2),
            PathwayEventTemplate(3, "EVENT-Z3", "EVENT-Z3", (1, 2), 1, 3),
        ),
    )

    graph = preprocess_routes(routes, pathway_templates=(template,)).patient_routes[0].graph

    assert graph.root_events == (1, 2)
    assert graph.terminal_events == (3,)
    assert graph.topological_order == (1, 2, 3)


def test_nonexistent_predecessor_is_rejected() -> None:
    routes = _routes()
    routes.loc[_target(routes, "PAT-002", 2), "dependencies"] = "[99]"

    with pytest.raises(DependencyValidationError, match="missing events"):
        preprocess_routes(routes)


def test_cycle_is_rejected() -> None:
    routes = _routes()
    routes.loc[_target(routes, "PAT-002", 1), "dependencies"] = "[4]"

    with pytest.raises(RouteCycleError, match="contains a cycle"):
        preprocess_routes(routes)


def test_self_dependency_is_rejected() -> None:
    routes = _routes()
    routes.loc[_target(routes, "PAT-002", 2), "dependencies"] = "[2]"

    with pytest.raises(DependencyValidationError, match="depends on itself"):
        preprocess_routes(routes)


def test_duplicate_dependency_is_rejected() -> None:
    routes = _routes()
    routes.loc[_target(routes, "PAT-002", 2), "dependencies"] = "[1,1]"

    with pytest.raises(DependencyValidationError, match="contains duplicates"):
        preprocess_routes(routes)


@pytest.mark.parametrize("value", ["not-json", "[1.5]", "[true]", "1"])
def test_malformed_dependency_is_rejected(value: str) -> None:
    routes = _routes()
    routes.loc[_target(routes, "PAT-002", 2), "dependencies"] = value

    with pytest.raises(DependencyValidationError):
        preprocess_routes(routes)


def test_duplicate_event_number_is_rejected() -> None:
    routes = _routes()
    routes.loc[_target(routes, "PAT-002", 2), "event_number"] = 1

    with pytest.raises(RouteValidationError, match="duplicate event number"):
        preprocess_routes(routes)


def test_duplicate_event_id_is_rejected() -> None:
    routes = _routes()
    routes.loc[_target(routes, "PAT-002", 2), "event_id"] = "EVENT-B1"

    with pytest.raises(RouteValidationError, match="duplicate event ID"):
        preprocess_routes(routes)


def test_noncontiguous_event_numbers_are_rejected() -> None:
    routes = _routes()
    routes.loc[_target(routes, "PAT-002", 4), "event_number"] = 5

    with pytest.raises(RouteValidationError, match="contiguous from 1"):
        preprocess_routes(routes)


def test_inconsistent_patient_pathway_is_rejected() -> None:
    routes = _routes()
    routes.loc[_target(routes, "PAT-002", 2), "pathway_id"] = "PATHWAY-A"

    with pytest.raises(RouteValidationError, match="inconsistent pathway IDs"):
        preprocess_routes(routes)


def test_patient_route_must_match_its_template() -> None:
    routes = _routes()
    routes.loc[_target(routes, "PAT-004", 5), "min_spacing_days"] = 3

    with pytest.raises(PathwayConsistencyError, match="does not match template"):
        preprocess_routes(routes)
