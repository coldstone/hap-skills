"""Execute a plan against the live app.

``apply`` builds the same plan ``plan`` renders, then runs each Action's
``hap`` call in order, collecting an :class:`OpOutcome` per op. A failed
op records the error and, by default, stops the run (later ops may depend
on it); pass ``continue_on_error`` to push through.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from scripts import hap
from scripts import ops as ops_mod
from scripts.editspec_loader import load_spec
from scripts.errors import EditorError, HapCommandError
from scripts.models import OpOutcome
from scripts.planner import check_confirm
from scripts.reader import AppIndex
from scripts.recording import Recorder


def apply_spec(
    spec: dict,
    idx: AppIndex,
    *,
    continue_on_error: bool = False,
    recorder: Optional[Recorder] = None,
) -> list[OpOutcome]:
    """Apply every op in ``spec`` against ``idx``'s app. Returns outcomes.

    Actions are built op-by-op against a freshly-refreshed index so an op
    can reference an element a previous op just created (intra-spec
    chaining). The confirm gate is enforced up front for every op before
    anything executes.
    """
    ops = spec.get("ops", [])
    for op in ops:                       # pre-flight: fail fast on missing confirm
        check_confirm(op)

    outcomes: list[OpOutcome] = []
    for i, op in enumerate(ops):
        op_type = op.get("type", "")
        responses: list = []
        try:
            idx.refresh()                # see effects of prior ops
            builder = ops_mod.REGISTRY[op_type]
            for action in builder(op, idx):
                res = hap.run(action.argv)
                responses.append(res.data)
            outcome = OpOutcome(i, op_type, "ok", responses=responses)
        except (HapCommandError, EditorError) as exc:
            outcome = OpOutcome(i, op_type, "error", detail=str(exc),
                                responses=responses)
        outcomes.append(outcome)
        if recorder:
            recorder.record(outcome)
        if outcome.status == "error" and not continue_on_error:
            break
    return outcomes


def main(argv: list[str] | None = None) -> int:
    """``python -m scripts apply [appId] <edit-spec.json> [--org ID] [--continue]``"""
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python -m scripts apply [appId] <edit-spec.json> "
              "[--org ID] [--continue]", file=sys.stderr)
        return 2
    cont = "--continue" in argv
    argv = [a for a in argv if a != "--continue"]
    org = ""
    if "--org" in argv:
        i = argv.index("--org")
        org = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    json_args = [a for a in argv if a.endswith(".json")]
    if not json_args:
        print("apply failed: no edit-spec .json file given", file=sys.stderr)
        return 2
    spec_path = Path(json_args[0])
    app_override = next((a for a in argv if not a.endswith(".json")), "")
    try:
        spec = load_spec(spec_path)
        app_ref = app_override or spec["app"]
        idx = AppIndex.load(app_ref, org or spec.get("org", ""))
        outcomes = apply_spec(spec, idx, continue_on_error=cont,
                              recorder=Recorder())
    except EditorError as exc:
        print(f"apply failed: {exc}", file=sys.stderr)
        return 1
    errors = [o for o in outcomes if o.status == "error"]
    print(f"applied {len(outcomes) - len(errors)}/{len(outcomes)} ops"
          + (f", {len(errors)} failed" if errors else ""))
    return 1 if errors else 0
