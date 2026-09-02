"""Bundled workbench peripheral catalog."""

from .catalog import load_catalog, spec_for
from .manifest import PeripheralSpec, RESERVED_PROPERTIES

__all__ = ["RESERVED_PROPERTIES", "PeripheralSpec", "load_catalog", "spec_for"]
