"""``python -m scripts inspect <appId|name> [--org ID]`` — print the live
name->id structure of an app (worksheets, sections, ...).

Useful before authoring an edit-spec: it shows the logical names the spec
can reference and the ids they resolve to.
"""
from __future__ import annotations

import json
import sys

from scripts.errors import EditorError
from scripts.reader import AppIndex


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python -m scripts inspect <appId|name> [--org ID]",
              file=sys.stderr)
        return 2
    app_ref = argv[0]
    org = ""
    if "--org" in argv:
        org = argv[argv.index("--org") + 1]
    try:
        idx = AppIndex.load(app_ref, org)
    except EditorError as exc:
        print(f"inspect failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(idx.summary(), ensure_ascii=False, indent=2))
    return 0
