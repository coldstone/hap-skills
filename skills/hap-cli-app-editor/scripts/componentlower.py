"""Lower a clean custom-page component definition into the wire shape.

Covered well: value-based widgets — richText (2), embedUrl (3), image (8).
For data-bound widgets (chart/view/filter/button) that need resolved ids
or nested config, pass the wire object under ``raw`` (merged last, wins).

Wire shape mirrors pd-openweb ``src/pages/customPage/util.js`` and the
hap-cli-app-creator component builders: a widget carries ``type`` (int),
``value``/config, ``name``, and per-platform ``web``/``mobile`` blocks
holding the grid ``layout`` (48-col).
"""
from __future__ import annotations

from typing import Any

# clean type name -> numeric widget type.
COMPONENT_TYPE = {
    "chart": 1, "analysis": 1,
    "richText": 2, "rich_text": 2,
    "embedUrl": 3, "embed_url": 3,
    "button": 4,
    "view": 5,
    "filter": 6,
    "image": 8,
    "carousel": 9,
    "tabs": 10,
    "card": 11,
}

# default 48-col grid size per type name.
_DEFAULT_WH = {
    "richText": (48, 5), "rich_text": (48, 5),
    "embedUrl": (24, 12), "embed_url": (24, 12),
    "image": (24, 12), "view": (48, 12), "chart": (24, 10),
    "button": (24, 6), "filter": (24, 3),
}


def resolve_type(t) -> int:
    if isinstance(t, int):
        return t
    if isinstance(t, str):
        if t.isdigit():
            return int(t)
        if t in COMPONENT_TYPE:
            return COMPONENT_TYPE[t]
    raise ValueError(f"unknown component type: {t!r}")


def lower_component(comp: dict[str, Any]) -> dict[str, Any]:
    """Return the wire component dict for one clean component definition.

    Clean form: ``{name, type, [value], [layout:{x,y,w,h}], [raw:{...}]}``.
    """
    type_name = comp["type"]
    type_id = resolve_type(type_name)
    w, h = _DEFAULT_WH.get(type_name, (24, 8))
    layout = dict(comp.get("layout") or {})
    layout.setdefault("x", 0)
    layout.setdefault("y", 0)
    layout.setdefault("w", w)
    layout.setdefault("h", h)
    layout.setdefault("minW", 2)
    layout.setdefault("minH", 4)
    # HAP does not round-trip a top-level ``name`` on a page component —
    # the queryable/display name lives in ``web.title``. Set both so the
    # editor can resolve the component by name on a later read.
    wire: dict[str, Any] = {
        "type": type_id,
        "name": comp["name"],
        "web": {"title": comp["name"], "titleVisible": True, "visible": True,
                "layout": layout},
        "mobile": {"title": comp["name"], "titleVisible": True,
                   "visible": True, "layout": None},
    }
    if "value" in comp:
        wire["value"] = comp["value"]
    if isinstance(comp.get("raw"), dict):
        wire.update(comp["raw"])
    return wire
