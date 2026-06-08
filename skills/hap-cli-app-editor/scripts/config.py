"""Runtime configuration — paths and timeouts.

No machine-specific absolute paths are baked in (this ships inside a
distributable skill): the ``hap`` binary defaults to the name ``hap``
resolved on ``PATH``, overridable with the ``HAP_BIN`` env var. On a
normal install ``PATH`` already points at the same binary that holds the
decryptable session token.
"""
from __future__ import annotations

import os
from pathlib import Path

# The installed CLI. Default to PATH lookup; override with HAP_BIN.
HAP_BIN = os.environ.get("HAP_BIN", "hap")

# Per-invocation timeout for a single ``hap`` call (seconds).
HAP_TIMEOUT = int(os.environ.get("HAP_EDITOR_TIMEOUT", "120"))

# Where edit-spec module schemas live.
EDITSPEC_DIR = Path(__file__).resolve().parent / "editspec"
