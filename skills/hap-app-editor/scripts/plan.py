"""``python -m scripts plan [appId] <edit-spec.json> [--org ID]``

Validates the spec, reads the live app to resolve logical names, and
prints the exact ``hap`` calls that ``apply`` would run — a dry run. No
mutations are made (only read-only lookups). The app target is taken
from the spec's ``app`` field; an optional leading appId overrides it.
"""
from __future__ import annotations

import sys
from pathlib import Path

from scripts.editspec_loader import load_spec
from scripts.errors import EditorError
from scripts.planner import build_plan, render_plan
from scripts.reader import AppIndex


def _parse(argv: list[str]) -> tuple[str, Path, str]:
    org = ""
    if "--org" in argv:
        i = argv.index("--org")
        org = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    json_args = [a for a in argv if a.endswith(".json")]
    if not json_args:
        raise EditorError("no edit-spec .json file given")
    spec_path = Path(json_args[0])
    app_override = next((a for a in argv if not a.endswith(".json")), "")
    return app_override, spec_path, org


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python -m scripts plan [appId] <edit-spec.json> [--org ID]",
              file=sys.stderr)
        return 2
    try:
        app_override, spec_path, org = _parse(argv)
        spec = load_spec(spec_path)
        app_ref = app_override or spec["app"]
        idx = AppIndex.load(app_ref, org or spec.get("org", ""))
        planned = build_plan(spec, idx)
    except EditorError as exc:
        print(f"plan failed: {exc}", file=sys.stderr)
        return 1
    print(render_plan(planned))
    return 0
