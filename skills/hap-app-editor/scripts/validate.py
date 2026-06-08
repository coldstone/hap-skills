"""``python -m scripts validate <edit-spec.json>`` — local, no API calls.

Validates an edit-spec against the envelope schema plus, per op, only the
module schema named by the op.type prefix. Exit 0 = valid, 2 = problems
(printed with their JSON paths). Run this before ``plan``/``apply`` so
structural mistakes are caught with zero network access.
"""
from __future__ import annotations

import sys
from pathlib import Path

from scripts.editspec_loader import load_spec
from scripts.errors import EditSpecError


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python -m scripts validate <edit-spec.json>",
              file=sys.stderr)
        return 2
    try:
        load_spec(Path(argv[0]))
    except EditSpecError as exc:
        print("edit-spec invalid:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2
    print("edit-spec OK")
    return 0
