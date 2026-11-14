"""Adaptadores de ingesta con unidades explícitas y preservación de valores ausentes."""

from .loader import convert_file, inspect_file
from .units import (
    ALIASES,
    MISSING_MARKERS,
    UnitConversionError,
    convert_unit,
    parse_nullable_float,
    suggest_canonical_column,
)

__all__ = [
    "ALIASES",
    "MISSING_MARKERS",
    "UnitConversionError",
    "convert_file",
    "convert_unit",
    "inspect_file",
    "parse_nullable_float",
    "suggest_canonical_column",
]
