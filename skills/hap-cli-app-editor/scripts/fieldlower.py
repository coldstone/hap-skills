"""Lower a clean field definition into a raw HAP control dict.

The clean form is what an edit-spec carries:
``{"name": "金额", "type": "Number", "required": true, ...}``. HAP's
``AddWorksheetControls`` / ``SaveWorksheetControls`` accept partial
control objects and fill per-type defaults server-side, so the lowering
only needs to set the discriminating keys.

Covered well: scalar types (Text/Number/Date/Email/...) and select types
(SingleSelect/MultipleSelect/Dropdown, with options). For advanced types
(Relation/Lookup/Rollup/Formula/SubTable) pass a raw override under the
field's ``control`` key — it is merged last and wins.
"""
from __future__ import annotations

import uuid
from typing import Any

from scripts._hapmeta import control_type_codes as codes

_OPTION_COLORS = [
    "#C9E6FC", "#C3F2F2", "#C2F1D2", "#FFE7B1", "#FBD2BF",
    "#FDD2DC", "#E6CFF1", "#D2D2D2",
]


def _normalize_options(opts: list) -> list[dict[str, Any]]:
    """Mirror the CLI's option shape (key/value/index/checked/color)."""
    out: list[dict[str, Any]] = []
    any_default = any(isinstance(o, dict) and o.get("checked") for o in opts)
    for i, o in enumerate(opts):
        if isinstance(o, dict):
            out.append({
                "key": o.get("key") or str(uuid.uuid4()),
                "value": o["value"],
                "isDeleted": o.get("isDeleted", False),
                "index": o.get("index", i + 1),
                "checked": o.get("checked", False),
                "color": o.get("color", _OPTION_COLORS[i % len(_OPTION_COLORS)]),
            })
        else:
            out.append({
                "key": str(uuid.uuid4()),
                "value": str(o),
                "isDeleted": False,
                "index": i + 1,
                "checked": (not any_default and i == 0),
                "color": _OPTION_COLORS[i % len(_OPTION_COLORS)],
            })
    return out


def lower_field(field: dict[str, Any]) -> dict[str, Any]:
    """Return the raw control dict for one clean field definition."""
    type_id = codes.resolve(field["type"])
    ctrl: dict[str, Any] = {"type": type_id, "controlName": field["name"]}
    if field.get("required"):
        ctrl["required"] = True
    if field.get("unique"):
        ctrl["unique"] = True
    if type_id in codes.SELECT_TYPE_IDS and field.get("options") is not None:
        ctrl["options"] = _normalize_options(field["options"])
    # Raw escape hatch for advanced types — merged last, wins.
    if isinstance(field.get("control"), dict):
        ctrl.update(field["control"])
    return ctrl
