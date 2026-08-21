"""Stable configuration for the public synthetic demonstration."""

from datetime import date

DEFAULT_SEED = 42
DEMO_START_DATE = date(2035, 1, 1)
DEMO_END_DATE = date(2035, 1, 28)

DATASET_FILENAMES = {
    "demand": "demand.csv",
    "supply": "supply.csv",
    "blocks": "blocks.csv",
    "resource_mapping": "resource_mapping.csv",
    "routes": "routes.csv",
}
