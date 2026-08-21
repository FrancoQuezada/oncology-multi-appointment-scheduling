from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from appointment_scheduling.routes import (
    RouteTimingError,
    RouteValidationError,
    preprocess_routes,
)


ROUTES_PATH = Path(__file__).resolve().parents[1] / "data" / "demo" / "routes.csv"


def _routes() -> pd.DataFrame:
    return pd.read_csv(ROUTES_PATH)


def _target(routes: pd.DataFrame, patient: str, event: int) -> pd.Series:
    return (routes["patient_id"] == patient) & (routes["event_number"] == event)


def test_negative_minimum_spacing_is_rejected() -> None:
    routes = _routes()
    routes.loc[_target(routes, "PAT-002", 2), "min_spacing_days"] = -1

    with pytest.raises(RouteValidationError, match="Minimum spacing.*non-negative"):
        preprocess_routes(routes)


def test_preferred_maximum_below_minimum_is_rejected() -> None:
    routes = _routes()
    routes.loc[_target(routes, "PAT-002", 3), "preferred_max_spacing_days"] = 2

    with pytest.raises(RouteValidationError, match="at least the minimum"):
        preprocess_routes(routes)


def test_single_predecessor_temporal_lower_bound() -> None:
    route = preprocess_routes(_routes()).route_for("PAT-002")

    lower_bound = route.temporal_lower_bound(2, {1: date(2035, 1, 4)})

    assert lower_bound == date(2035, 1, 5)


def test_multiple_predecessors_use_latest_realized_date() -> None:
    route = preprocess_routes(_routes()).route_for("PAT-001")

    lower_bound = route.temporal_lower_bound(
        5,
        {2: date(2035, 1, 10), 3: date(2035, 1, 12)},
    )

    assert lower_bound == date(2035, 1, 14)
    assert route.event(5).preferred_max_spacing_days == 6


def test_temporal_lower_bound_preserves_datetime_type() -> None:
    route = preprocess_routes(_routes()).route_for("PAT-002")

    lower_bound = route.temporal_lower_bound(2, {1: datetime(2035, 1, 4, 9, 30)})

    assert lower_bound == datetime(2035, 1, 5, 9, 30)


def test_missing_predecessor_date_is_rejected() -> None:
    route = preprocess_routes(_routes()).route_for("PAT-001")

    with pytest.raises(RouteTimingError, match="Missing scheduled predecessor dates"):
        route.temporal_lower_bound(5, {2: date(2035, 1, 10)})


def test_root_event_requires_external_start_reference() -> None:
    route = preprocess_routes(_routes()).route_for("PAT-001")

    with pytest.raises(RouteTimingError, match="root.*no predecessor"):
        route.temporal_lower_bound(1, {})


def test_nondate_predecessor_value_is_rejected() -> None:
    route = preprocess_routes(_routes()).route_for("PAT-002")

    with pytest.raises(RouteTimingError, match="must be dates"):
        route.temporal_lower_bound(2, {1: "2035-01-04"})
