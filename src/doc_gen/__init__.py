"""Industry-Level Codebase-Aware Document Generator with Trainable RL Model."""

# Preload native libraries before any submodule imports a C extension
# (torch, numpy, transformers). This must stay first in the package import
# order; see native_libs.py for why LD_LIBRARY_PATH alone is insufficient.
from .native_libs import preload as _preload_native_libs

_preload_native_libs()

__version__ = "1.0.0"
