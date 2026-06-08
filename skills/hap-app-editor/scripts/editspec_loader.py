"""Load + validate an edit-spec.

Validation is two-stage and *module-local* (decision #9): the envelope
schema checks the wrapper and each op's shared ``type``/``confirm``
fields; then, per op, only the one module schema named by the op.type
prefix is loaded and used for deep validation. A spec touching only
fields never loads the view/role/workflow schemas — keeping context
light.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts import config, jsonschema_mini
from scripts.errors import EditSpecError

# op.type prefix -> module schema filename. Extended per phase.
_MODULE_BY_PREFIX = {
    "worksheet": "worksheet.schema.json",
    "field": "field.schema.json",
    "view": "view.schema.json",
    "role": "role.schema.json",
    "custom-action": "custom-action.schema.json",
    "chatbot": "chatbot.schema.json",
    "custom-page": "custom-page.schema.json",
    "workflow": "workflow.schema.json",
    "component": "component.schema.json",
    "node": "node.schema.json",
    "app": "application.schema.json",
    "section": "application.schema.json",
}

# Destructive op types: apply refuses these without confirm:true.
DESTRUCTIVE_TYPES = {
    "worksheet.delete",
    "field.delete",
    "view.delete",
    "role.delete",
    "custom-action.delete",
    "chatbot.delete",
    "custom-page.delete",
    "workflow.delete",
    "component.delete",
    "node.delete",
    "section.delete",
}


def _load_schema(filename: str) -> dict[str, Any]:
    path = config.EDITSPEC_DIR / filename
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_spec(path: Path) -> dict[str, Any]:
    """Read an edit-spec JSON file and validate it. Returns the spec dict.

    Raises :class:`EditSpecError` with every problem found (envelope and
    per-op), each prefixed with its JSON path.
    """
    try:
        with path.open(encoding="utf-8") as fh:
            spec = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise EditSpecError([f"could not read edit-spec {path}: {exc}"]) from exc
    validate_spec(spec)
    return spec


def validate_spec(spec: Any) -> None:
    """Validate an already-parsed edit-spec; raise on any problem."""
    problems: list[str] = []
    envelope = _load_schema("envelope.schema.json")
    problems += jsonschema_mini.validate(spec, envelope)

    # Deep per-op validation, dispatched by type prefix. Only runs when
    # the envelope gave each op a known type.
    if isinstance(spec, dict) and isinstance(spec.get("ops"), list):
        for i, op in enumerate(spec["ops"]):
            if not isinstance(op, dict):
                continue
            op_type = op.get("type")
            if not isinstance(op_type, str) or "." not in op_type:
                continue  # envelope already flagged a bad/missing type
            prefix, verb = op_type.split(".", 1)
            module = _MODULE_BY_PREFIX.get(prefix)
            if module is None:
                problems.append(f"ops[{i}].type: '{op_type}' has no module "
                                f"schema (prefix '{prefix}' unsupported)")
                continue
            schema = _load_schema(module)
            # Dispatch to the specific verb branch so errors are precise
            # (e.g. "missing required 'confirm'") instead of a vague
            # "matched 0 of oneOf branches". Branch key is the verb
            # (create/update/...); when a module hosts two prefixes whose
            # verbs collide (app.update vs section.update) the $def uses the
            # full "<prefix>_<verb>" key, so fall back to that.
            defs = schema.get("$defs") or {}
            branch = defs.get(verb) or defs.get(op_type.replace(".", "_").replace("-", "_"))
            if branch is None:
                problems.append(f"ops[{i}].type: '{op_type}' has no '{verb}' "
                                f"branch in {module}")
                continue
            problems += jsonschema_mini.validate_against(
                op, branch, schema, f"ops[{i}]")

    if problems:
        raise EditSpecError(problems)
