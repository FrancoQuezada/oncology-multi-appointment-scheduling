"""Safe preprocessing of synthetic supply and capacity data."""

from appointment_scheduling.preprocessing.models import (
    AVAILABILITY_COLUMNS,
    SupplyPreprocessingDiagnostics,
    SupplyPreprocessingResult,
)
from appointment_scheduling.preprocessing.supply import preprocess_supply
from appointment_scheduling.preprocessing.validation import (
    DuplicateSupplyError,
    MappingCardinalityError,
    OrphanBlockError,
    SupplyValidationError,
)

__all__ = [
    "AVAILABILITY_COLUMNS",
    "DuplicateSupplyError",
    "MappingCardinalityError",
    "OrphanBlockError",
    "SupplyPreprocessingDiagnostics",
    "SupplyPreprocessingResult",
    "SupplyValidationError",
    "preprocess_supply",
]
