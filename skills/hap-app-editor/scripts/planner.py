"""Turn an edit-spec into an ordered list of concrete ``hap`` calls.

The planner is the single source of both the dry-run preview and the
real execution: ``plan`` renders the Actions it produces and ``apply``
runs the very same Actions, so the preview can never drift from what
actually happens (success criterion #5).

Each op is expanded by its builder (see :mod:`scripts.ops`) into one or
more :class:`Action`s. Builders may read live state through the index
(read-only) to compute the exact call — e.g. resolving a field name to a
controlId — which is why the index is passed in.
"""
from __future__ import annotations

from typing import Any

from scripts import ops as ops_mod
from scripts.editspec_loader import DESTRUCTIVE_TYPES
from scripts.errors import ConfirmRequiredError, EditSpecError, ResolveError
from scripts.models import Action, PlannedOp
from scripts.reader import AppIndex


def check_confirm(op: dict[str, Any]) -> None:
    """Raise if a destructive op lacks ``confirm: true``."""
    if op.get("type") in DESTRUCTIVE_TYPES and op.get("confirm") is not True:
        raise ConfirmRequiredError(
            f"op '{op.get('type')}' is destructive and requires "
            f"\"confirm\": true")


def build_plan(spec: dict[str, Any], idx: AppIndex) -> list[PlannedOp]:
    """Expand every op into actions for the dry-run preview.

    Enforces the confirm gate. Resolution happens against the *current*
    live state, so an op that depends on an element an earlier op will
    create cannot be resolved yet — that op gets a placeholder action
    noting the id is resolved at apply time (apply rebuilds per op
    against refreshed state).

    Raises :class:`ConfirmRequiredError` for an unconfirmed destructive
    op and :class:`EditSpecError` if an op type has no builder.
    """
    planned: list[PlannedOp] = []
    for i, op in enumerate(spec.get("ops", [])):
        check_confirm(op)
        builder = ops_mod.REGISTRY.get(op.get("type"))
        if builder is None:
            raise EditSpecError(
                [f"ops[{i}].type: no builder for '{op.get('type')}' "
                 f"(not implemented yet)"])
        try:
            actions = builder(op, idx)
        except ResolveError as exc:
            actions = [Action(
                f"(resolved at apply time — {exc})", [])]
        planned.append(PlannedOp(index=i, op=op, actions=actions))
    return planned


def render_plan(planned: list[PlannedOp]) -> str:
    """Human-readable dry-run preview of a plan."""
    lines: list[str] = []
    for p in planned:
        label = p.op.get("label") or p.op.get("type")
        lines.append(f"[{p.index}] {label}")
        for a in p.actions:
            lines.append(f"    - {a.description}")
            lines.append(f"      hap {' '.join(a.argv)}")
    return "\n".join(lines) if lines else "(no operations)"
