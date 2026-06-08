"""Build a live name->id index of an app by reading it from HAP.

The editor's source of truth is the live app, not any cached store
(decision #1). :class:`AppIndex` resolves logical names (worksheet /
section / view / field) to their server ids using only read-only ``hap``
commands, and exposes the *complete* raw control set per worksheet so
field edits can do read-modify-write without dropping reverse/system
controls (decision #10).

Everything is fetched lazily and cached for the lifetime of the index.
"""
from __future__ import annotations

from typing import Any, Optional

from scripts import hap
from scripts.errors import ResolveError


class AppIndex:
    def __init__(self, app_id: str, org_id: str = "",
                 app_detail: Optional[dict] = None):
        self.app_id = app_id
        self.org_id = org_id
        self._app_detail = app_detail or {}
        self._sections: list[dict] = []          # [{id, name, items:[...]}]
        self._ws_controls: dict[str, list] = {}  # ws_id -> raw controls
        self._ws_views: dict[str, list] = {}     # ws_id -> [{viewId,name}]
        if app_detail:
            self._index_sections(app_detail)

    # ── construction ────────────────────────────────────────────────
    @classmethod
    def load(cls, app_ref: str, org: str = "") -> "AppIndex":
        """Resolve an app by id (preferred) or name and load its index."""
        org_id = org
        if not org_id:
            who = hap.whoami()
            org_id = who.get("current_org_id", "")
        app_id = cls._resolve_app(app_ref, org_id)
        detail = hap.unwrap(hap.run(["app", "info", "-a", app_id]).data)
        if not isinstance(detail, dict):
            raise ResolveError(f"could not read app info for {app_id!r}")
        return cls(app_id, org_id, detail)

    @staticmethod
    def _resolve_app(app_ref: str, org_id: str) -> str:
        args = ["app", "list"]
        if org_id:
            args += ["--org-id", org_id]
        data = hap.unwrap(hap.run(args, check=False).data)
        apps = data if isinstance(data, list) else []
        for a in apps:
            if a.get("appId") == app_ref or a.get("id") == app_ref:
                return app_ref
        for a in apps:
            if a.get("name") == app_ref:
                return a.get("appId") or a.get("id")
        # Not found by name in the active list — assume it's an id.
        return app_ref

    def _index_sections(self, detail: dict) -> None:
        self._sections = detail.get("sections") or []

    def refresh(self) -> None:
        """Re-read the app's structure from HAP and drop all caches.

        Called between ops during apply so an op can reference an element
        created by an earlier op in the same spec (intra-spec chaining).
        """
        detail = hap.unwrap(hap.run(["app", "info", "-a", self.app_id]).data)
        if isinstance(detail, dict):
            self._app_detail = detail
            self._index_sections(detail)
        self._ws_controls.clear()
        self._ws_views.clear()

    # ── sections ────────────────────────────────────────────────────
    def section_id(self, ref: str) -> str:
        for s in self._sections:
            if s.get("id") == ref or s.get("name") == ref:
                return s.get("id")
        raise ResolveError(f"section {ref!r} not found in app {self.app_id}")

    def first_section_id(self) -> str:
        if not self._sections:
            raise ResolveError(f"app {self.app_id} has no sections")
        return self._sections[0].get("id")

    # ── worksheets ──────────────────────────────────────────────────
    def _ws_items(self) -> list[tuple[str, dict]]:
        """Yield (section_id, item) for every worksheet item (type 0)."""
        out: list[tuple[str, dict]] = []
        for s in self._sections:
            for item in s.get("items", []):
                if item.get("type", 0) == 0:
                    out.append((s.get("id"), item))
        return out

    def worksheet_id(self, ref: str) -> str:
        for _sid, item in self._ws_items():
            if item.get("id") == ref or item.get("name") == ref:
                return item.get("id")
        raise ResolveError(f"worksheet {ref!r} not found in app {self.app_id}")

    def worksheet_exists(self, ref: str) -> bool:
        try:
            self.worksheet_id(ref)
            return True
        except ResolveError:
            return False

    def section_of_worksheet(self, ref: str) -> str:
        ws_id = self.worksheet_id(ref)
        for sid, item in self._ws_items():
            if item.get("id") == ws_id:
                return sid
        raise ResolveError(f"no section owns worksheet {ref!r}")

    # ── fields / controls ───────────────────────────────────────────
    def controls(self, ws_ref: str) -> list[dict]:
        """Return the COMPLETE raw control set for a worksheet (cached).

        Includes reverse/system controls — callers doing read-modify-write
        must write the full set back, mutating only their target.
        """
        ws_id = self.worksheet_id(ws_ref)
        if ws_id not in self._ws_controls:
            data = hap.unwrap(
                hap.run(["worksheet", "fields", ws_id, "--raw"]).data)
            self._ws_controls[ws_id] = data if isinstance(data, list) else []
        return self._ws_controls[ws_id]

    def control_id(self, ws_ref: str, field_ref: str) -> str:
        for c in self.controls(ws_ref):
            if (c.get("controlId") == field_ref
                    or c.get("controlName") == field_ref
                    or c.get("alias") == field_ref):
                return c.get("controlId")
        raise ResolveError(
            f"field {field_ref!r} not found in worksheet {ws_ref!r}")

    # ── views ───────────────────────────────────────────────────────
    def views(self, ws_ref: str) -> list[dict]:
        ws_id = self.worksheet_id(ws_ref)
        if ws_id not in self._ws_views:
            data = hap.unwrap(hap.run(["worksheet", "view", "list", ws_id]).data)
            self._ws_views[ws_id] = data if isinstance(data, list) else []
        return self._ws_views[ws_id]

    def view_id(self, ws_ref: str, view_ref: str) -> str:
        for v in self.views(ws_ref):
            if v.get("viewId") == view_ref or v.get("name") == view_ref:
                return v.get("viewId")
        raise ResolveError(
            f"view {view_ref!r} not found in worksheet {ws_ref!r}")

    # ── roles ───────────────────────────────────────────────────────
    def roles(self) -> list[dict]:
        if not hasattr(self, "_roles_cache"):
            data = hap.unwrap(hap.run(["app", "role", "list", "-a", self.app_id],
                                      check=False).data)
            if isinstance(data, dict):
                data = data.get("roles", [])
            self._roles_cache = data if isinstance(data, list) else []
        return self._roles_cache

    def role_id(self, ref: str) -> str:
        for r in self.roles():
            if r.get("id") == ref or r.get("name") == ref:
                return r.get("id")
        raise ResolveError(f"role {ref!r} not found in app {self.app_id}")

    # ── custom actions (buttons) ────────────────────────────────────
    def custom_actions(self, ws_ref: str) -> list[dict]:
        ws_id = self.worksheet_id(ws_ref)
        cache = getattr(self, "_btn_cache", None)
        if cache is None:
            cache = self._btn_cache = {}
        if ws_id not in cache:
            data = hap.unwrap(
                hap.run(["worksheet", "custom-actions", ws_id]).data)
            if isinstance(data, dict):
                data = data.get("btns") or data.get("buttons") or []
            cache[ws_id] = data if isinstance(data, list) else []
        return cache[ws_id]

    def action_id(self, ws_ref: str, ref: str) -> str:
        for b in self.custom_actions(ws_ref):
            if (b.get("btnId") == ref or b.get("id") == ref
                    or b.get("name") == ref):
                return b.get("btnId") or b.get("id")
        raise ResolveError(
            f"custom action {ref!r} not found on worksheet {ws_ref!r}")

    # ── sidebar items: pages / chatbots (type != 0) ─────────────────
    def _all_items(self) -> list[tuple[str, dict]]:
        out: list[tuple[str, dict]] = []
        for s in self._sections:
            for item in s.get("items", []):
                out.append((s.get("id"), item))
        return out

    def item(self, ref: str) -> dict:
        """Resolve a sidebar item (page/chatbot/worksheet) by name or id.

        Returns ``{id, name, section, type}``. Pages and chatbots are
        non-worksheet items; ids are unique and names are unique in a
        sidebar, so a name match is unambiguous.
        """
        for sid, it in self._all_items():
            if it.get("id") == ref or it.get("name") == ref:
                return {"id": it.get("id"), "name": it.get("name"),
                        "section": sid, "type": it.get("type", 0)}
        raise ResolveError(f"item {ref!r} not found in app {self.app_id}")

    # ── workflows ───────────────────────────────────────────────────
    def workflows(self) -> list[dict]:
        if not hasattr(self, "_wf_cache"):
            data = hap.unwrap(hap.run(
                ["workflow", "list", self.app_id], check=False).data)
            if isinstance(data, dict):
                data = (data.get("list") or data.get("processes")
                        or data.get("data") or [])
            self._wf_cache = data if isinstance(data, list) else []
        return self._wf_cache

    def workflow_id(self, ref: str) -> str:
        for w in self.workflows():
            if (w.get("id") == ref or w.get("processId") == ref
                    or w.get("name") == ref):
                return w.get("id") or w.get("processId")
        raise ResolveError(f"workflow {ref!r} not found in app {self.app_id}")

    # ── workflow nodes ──────────────────────────────────────────────
    def _wf_structure(self, wf_ref: str) -> dict:
        pid = self.workflow_id(wf_ref)
        data = hap.unwrap(hap.run(["workflow", "node", "list", pid]).data)
        return data if isinstance(data, dict) else {}

    def start_node_id(self, wf_ref: str) -> str:
        return self._wf_structure(wf_ref).get("startEventId", "")

    def node_id(self, wf_ref: str, ref: str) -> str:
        """Resolve a node by name or id within a workflow.

        'start' resolves to the trigger/start node.
        """
        struct = self._wf_structure(wf_ref)
        if ref == "start":
            return struct.get("startEventId", "")
        nodes = struct.get("flowNodeMap", {}) or {}
        if ref in nodes:
            return ref
        for nid, n in nodes.items():
            if n.get("name") == ref:
                return nid
        raise ResolveError(f"node {ref!r} not found in workflow {wf_ref!r}")

    def node_obj(self, wf_ref: str, ref: str) -> dict[str, Any]:
        """Return the live flow-node dict (from ``flowNodeMap``) for a node.

        Used by ``node.update`` to default the ``--type`` (node ``typeId``)
        when the spec omits ``node_type``.
        """
        struct = self._wf_structure(wf_ref)
        nodes = struct.get("flowNodeMap", {}) or {}
        nid = ref if ref in nodes else self.node_id(wf_ref, ref)
        return nodes.get(nid, {})

    # ── custom-page layout (components) ─────────────────────────────
    def page_layout(self, page_ref: str) -> dict[str, Any]:
        """Return {page_id, version, components} for a custom page.

        Custom pages are stored under the worksheet id space; the page's
        own id is what getPage/savePage take. Used for component
        read-modify-write.
        """
        page_id = self.item(page_ref)["id"]
        data = hap.unwrap(hap.run(["custom-page", "info", page_id]).data)
        if not isinstance(data, dict):
            raise ResolveError(f"could not read page layout for {page_ref!r}")
        return {
            "page_id": page_id,
            "version": data.get("version", 0),
            "components": data.get("components") or [],
        }

    # ── summary (for inspect) ───────────────────────────────────────
    def summary(self) -> dict[str, Any]:
        """A name->id structure map of the app (for the inspect command).

        Lists every element an edit-spec can reference: sections,
        worksheets, other sidebar items (pages/chatbots), roles and
        workflows. Roles/workflows are fetched best-effort so inspect
        still works if those reads fail.
        """
        worksheets = []
        for sid, item in self._ws_items():
            worksheets.append({"id": item.get("id"), "name": item.get("name"),
                               "section": sid})
        # Non-worksheet sidebar items (custom pages, chatbots, ...).
        other_items = [
            {"id": it.get("id"), "name": it.get("name"),
             "type": it.get("type"), "section": sid}
            for sid, it in self._all_items() if it.get("type", 0) != 0
        ]
        out: dict[str, Any] = {
            "app_id": self.app_id,
            "org_id": self.org_id,
            "name": self._app_detail.get("name"),
            "sections": [{"id": s.get("id"), "name": s.get("name")}
                         for s in self._sections],
            "worksheets": worksheets,
            "pages_and_chatbots": other_items,
        }
        try:
            out["roles"] = [{"id": r.get("id"), "name": r.get("name")}
                            for r in self.roles()]
        except Exception:  # noqa: BLE001 — best-effort enrichment
            out["roles"] = []
        try:
            out["workflows"] = [{"id": w.get("id") or w.get("processId"),
                                 "name": w.get("name")} for w in self.workflows()]
        except Exception:  # noqa: BLE001
            out["workflows"] = []
        return out
