"""Native library preloading for NixOS and other non-standard host layouts.

PyTorch, NumPy, and Transformers all rely on ``dlopen`` to pull in C extension
modules at import time. On this host those modules fail with::

    libstdc++.so.6: cannot open shared object file
    libz.so.1: cannot open shared object file
    libz.so.1: wrong ELF class: ELFCLASS32

Mutating ``os.environ["LD_LIBRARY_PATH"]`` cannot fix this: glibc's dynamic
linker reads that variable once at ``exec`` time, so an in-process assignment
has no effect on later ``dlopen`` calls.

The working approach is to ``dlopen`` each missing library ourselves with
``RTLD_GLOBAL``. That places its symbols in the global namespace, so the next
``dlopen("libz.so.1")`` by NumPy resolves against the already-loaded object.
Trying each candidate in turn also filters out 32-bit builds, which a
``LD_LIBRARY_PATH`` glob cannot do (it only produces "wrong ELF class").

This module is imported from ``src.doc_gen.__init__`` so that every entry point
-- CLI, daemon, tests, ``python -c`` -- gets the same working environment
without a wrapper script or hardcoded /nix/store hashes.
"""

from __future__ import annotations

import ctypes
import glob
import os
import re

# Libraries that must be resolvable for the scientific Python stack to import.
REQUIRED_LIBS = ("libgcc_s.so.1", "libstdc++.so.6", "libz.so.1")

# GPU driver: torch resolves libcuda.so.1 by soname during import.
CUDA_LIBS = ("libcuda.so.1",)

SEARCH_DIRS = (
    "/nix/store/*-gcc-*-lib/lib",
    "/nix/store/*zlib*/lib",
    "/nix/store/*-nvidia-x11-*/lib",
    "/run/opengl-driver/lib",
    "/run/current-system/sw/lib",
    "/nix/store/*-ld-library-path*/share/nix-ld/lib",
)

_loaded: dict[str, str] = {}
_attempted = False


def _is_candidate(path: str) -> bool:
    """Reject musl and 32-bit builds; loading them would fail or corrupt the ABI."""
    lowered = path.lower()
    return "musl" in lowered or "lib32" in lowered


def _gcc_version_key(path: str) -> tuple[int, ...]:
    """Sort gcc store paths newest-first so the newest runtime is preferred."""
    found = re.search(r"-gcc-(\d+(?:\.\d+)*)-lib", path)
    return tuple(int(x) for x in found.group(1).split(".")) if found else (0,)


def candidate_dirs() -> list[str]:
    """Expand configured globs into a deterministic, arch-filtered directory list."""
    dirs: list[str] = []
    for pattern in SEARCH_DIRS:
        matches = [p for p in glob.glob(pattern) if not _is_candidate(p)]
        matches.sort(key=_gcc_version_key, reverse=True)
        for path in matches:
            if os.path.isdir(path) and path not in dirs:
                dirs.append(path)
    return dirs


def _load_first(libname: str, dirs: list[str]) -> str | None:
    """Load the first working candidate for ``libname`` into the global namespace."""
    for directory in dirs:
        candidate = os.path.join(directory, libname)
        if not os.path.exists(candidate):
            continue
        try:
            ctypes.CDLL(candidate, mode=ctypes.RTLD_GLOBAL)
            return candidate
        except OSError:
            # Wrong architecture, truncated store path, or a dependency we have
            # not loaded yet. Move on rather than aborting the whole process.
            continue
    return None


def preload() -> dict[str, str]:
    """Load every required native library. Safe to call repeatedly."""
    global _attempted
    if _attempted:
        return dict(_loaded)
    _attempted = True

    dirs = candidate_dirs()

    # Also export the directories for child processes. This does nothing for the
    # current process, but subprocesses (WordCraft MCP, helpers) benefit.
    if dirs:
        current = os.environ.get("LD_LIBRARY_PATH", "")
        missing = [d for d in dirs if d not in current]
        if missing:
            os.environ["LD_LIBRARY_PATH"] = (
                ":".join(missing) + (f":{current}" if current else "")
            )

    for libname in REQUIRED_LIBS + CUDA_LIBS:
        resolved = _load_first(libname, dirs)
        if resolved:
            _loaded[libname] = resolved

    return dict(_loaded)


def report() -> dict[str, str]:
    """Return the libraries resolved by :func:`preload`."""
    return dict(_loaded)
