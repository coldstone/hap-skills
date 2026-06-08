"""Op builders: edit-spec op -> concrete ``hap`` Action(s).

Each builder takes the op dict and a live :class:`AppIndex` and returns
the list of :class:`Action`s needed to carry it out. Builders resolve
logical names to ids via the index and never mutate state themselves —
execution happens in :mod:`scripts.apply`, so the dry-run preview and the
real run share one code path.

Registered here: worksheet.* and view.* (P0). field.* (read-modify-write
with field lowering) lands in P1; role/custom-action/workflow/custom-page
in later phases.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from scripts.componentlower import lower_component
from scripts.errors import ResolveError
from scripts.fieldlower import lower_field
from scripts.models import Action
from scripts.reader import AppIndex


# ── worksheet ───────────────────────────────────────────────────────────
def _ws_create(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    section = op.get("section")
    sid = idx.section_id(section) if section else idx.first_section_id()
    argv = ["worksheet", "create", idx.app_id, op["name"], "--section-id", sid]
    if op.get("icon"):
        argv += ["--icon", op["icon"]]
    return [Action(f"create worksheet '{op['name']}'", argv)]


def _ws_update(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    ws_id = idx.worksheet_id(op["worksheet"])
    argv = ["worksheet", "update", ws_id, "-a", idx.app_id]
    for opt, key in (("--alias", "alias"), ("--desc", "desc"),
                     ("--name", "name"), ("--icon", "icon")):
        if op.get(key):
            argv += [opt, op[key]]
    return [Action(f"update worksheet '{op['worksheet']}'", argv)]


def _ws_delete(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    ws_id = idx.worksheet_id(op["worksheet"])
    # Existing V3 command (DELETE /v3/app/worksheets/{id}) — permanent.
    argv = ["worksheet", "delete", ws_id, "-a", idx.app_id]
    return [Action(f"delete worksheet '{op['worksheet']}'", argv)]


# ── view ────────────────────────────────────────────────────────────────
def _view_create(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    ws_id = idx.worksheet_id(op["worksheet"])
    argv = ["worksheet", "view", "create", ws_id, op["name"], "-a", idx.app_id]
    if op.get("view_type"):
        argv += ["--view-type", op["view_type"]]
    if op.get("config"):
        argv += ["--config-json", json.dumps(op["config"], ensure_ascii=False)]
    return [Action(f"create view '{op['name']}' on '{op['worksheet']}'", argv)]


def _view_update(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    ws_id = idx.worksheet_id(op["worksheet"])
    view_id = idx.view_id(op["worksheet"], op["view"])
    attrs = list(op.get("edit_attrs", []))
    set_obj = dict(op.get("set", {}))
    if op.get("name"):
        set_obj["name"] = op["name"]
        if "name" not in attrs:
            attrs.append("name")
    argv = ["worksheet", "view", "update", ws_id, view_id, "-a", idx.app_id]
    if set_obj:
        argv += ["--view-json", json.dumps(set_obj, ensure_ascii=False)]
    if attrs:
        argv += ["--edit-attrs", ",".join(attrs)]
    if op.get("edit_ad_keys"):
        argv += ["--edit-ad-keys", ",".join(op["edit_ad_keys"])]
    return [Action(f"update view '{op['view']}' on '{op['worksheet']}'", argv)]


def _view_delete(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    ws_id = idx.worksheet_id(op["worksheet"])
    view_id = idx.view_id(op["worksheet"], op["view"])
    argv = ["worksheet", "view", "delete", ws_id, view_id, "-a", idx.app_id]
    return [Action(f"delete view '{op['view']}' on '{op['worksheet']}'", argv)]


# ── field ───────────────────────────────────────────────────────────────
# Strategy (decision #10): add uses the incremental add-fields path (keeps
# auto reverse controls); update/delete/reorder read the COMPLETE control
# set, mutate only the target, then write the whole set back via
# update-fields — so reverse/system controls are never dropped.
def _field_add(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    ws_id = idx.worksheet_id(op["worksheet"])
    control = lower_field(op["field"])
    argv = ["worksheet", "add-fields", ws_id,
            "--controls", json.dumps([control], ensure_ascii=False)]
    return [Action(f"add field '{op['field']['name']}' to '{op['worksheet']}'",
                   argv)]


def _match_control(controls: list, ref: str) -> dict:
    for c in controls:
        if (c.get("controlId") == ref or c.get("controlName") == ref
                or c.get("alias") == ref):
            return c
    raise ResolveError(f"field {ref!r} not found")


def _field_update(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    ws_id = idx.worksheet_id(op["worksheet"])
    controls = [dict(c) for c in idx.controls(op["worksheet"])]  # full set, copy
    target = _match_control(controls, op["field"])
    if op.get("rename"):
        target["controlName"] = op["rename"]
    target.update(op.get("set", {}))
    argv = ["worksheet", "update-fields", ws_id,
            "--controls", json.dumps(controls, ensure_ascii=False)]
    return [Action(f"update field '{op['field']}' on '{op['worksheet']}' "
                   f"(full-set write-back of {len(controls)} controls)", argv)]


def _field_delete(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    ws_id = idx.worksheet_id(op["worksheet"])
    controls = idx.controls(op["worksheet"])
    target = _match_control(controls, op["field"])
    remaining = [c for c in controls if c.get("controlId") != target.get("controlId")]
    argv = ["worksheet", "update-fields", ws_id,
            "--controls", json.dumps(remaining, ensure_ascii=False)]
    return [Action(f"delete field '{op['field']}' from '{op['worksheet']}' "
                   f"(write-back of remaining {len(remaining)} controls)", argv)]


def _field_reorder(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    ws_id = idx.worksheet_id(op["worksheet"])
    controls = [dict(c) for c in idx.controls(op["worksheet"])]  # full set, copy
    by_ref: dict[str, dict] = {}
    for c in controls:
        for k in (c.get("controlId"), c.get("controlName"), c.get("alias")):
            if k:
                by_ref.setdefault(k, c)
    ordered: list[dict] = []
    seen_ids = set()
    for ref in op["order"]:
        c = by_ref.get(ref)
        if c is None:
            raise ResolveError(f"field {ref!r} not found for reorder")
        if c.get("controlId") not in seen_ids:
            ordered.append(c)
            seen_ids.add(c.get("controlId"))
    # Append any controls not named in `order`, preserving original order.
    for c in controls:
        if c.get("controlId") not in seen_ids:
            ordered.append(c)
            seen_ids.add(c.get("controlId"))
    # Field order in HAP is driven by each control's row/col, not array
    # order. Stack the controls full-width in the requested sequence.
    for i, c in enumerate(ordered):
        c["row"] = i
        c["col"] = 0
    argv = ["worksheet", "update-fields", ws_id,
            "--controls", json.dumps(ordered, ensure_ascii=False)]
    return [Action(f"reorder {len(op['order'])} field(s) on '{op['worksheet']}'",
                   argv)]


# ── role ────────────────────────────────────────────────────────────────
def _role_create(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    # permission_scope 0 (per-item) requires non-empty worksheet_permissions;
    # default to 20 (view-only) for a valid standalone role when unspecified.
    scope = str(op.get("permission_scope", "20"))
    argv = ["app", "role", "create", "-a", idx.app_id,
            "--name", op["name"],
            "--description", op.get("description", ""),
            "--type", "0",
            "--permission-scope", scope]
    if op.get("hide_app_for_members"):
        argv += ["--hide-app-for-members", "true"]
    if op.get("global_permissions") is not None:
        argv += ["--global-permissions-json",
                 json.dumps(op["global_permissions"], ensure_ascii=False)]
    if op.get("worksheet_permissions") is not None:
        argv += ["--worksheet-permissions-json",
                 json.dumps(op["worksheet_permissions"], ensure_ascii=False)]
    if op.get("page_permissions") is not None:
        argv += ["--page-permissions-json",
                 json.dumps(op["page_permissions"], ensure_ascii=False)]
    return [Action(f"create role '{op['name']}'", argv)]


def _role_update(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    role_id = idx.role_id(op["role"])
    actions: list[Action] = []
    if op.get("rename"):
        actions.append(Action(
            f"rename role '{op['role']}' -> '{op['rename']}'",
            ["app", "role", "rename", idx.app_id, role_id, "-n", op["rename"]]))
    if op.get("permissions") is not None:
        argv = ["app", "role", "set-permissions", idx.app_id, role_id,
                "-P", json.dumps(op["permissions"], ensure_ascii=False)]
        if op.get("permission_way") is not None:
            argv += ["--permission-way", str(op["permission_way"])]
        actions.append(Action(f"set permissions on role '{op['role']}'", argv))
    if not actions:
        raise ResolveError("role.update needs 'rename' and/or 'permissions'")
    return actions


def _role_delete(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    role_id = idx.role_id(op["role"])
    return [Action(f"delete role '{op['role']}'",
                   ["app", "role", "delete", role_id, "-a", idx.app_id])]


_MEMBER_OPTS = (
    ("user_ids", "--user-ids"), ("department_ids", "--department-ids"),
    ("department_tree_ids", "--department-tree-ids"), ("job_ids", "--job-ids"),
    ("org_role_ids", "--org-role-ids"),
)


def _member_argv(members: dict[str, Any]) -> list[str]:
    argv: list[str] = []
    for key, opt in _MEMBER_OPTS:
        vals = members.get(key)
        if vals:
            argv += [opt, ",".join(vals)]
    return argv


def _role_add_member(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    role_id = idx.role_id(op["role"])
    argv = ["app", "role", "add-member", role_id, "-a", idx.app_id]
    argv += _member_argv(op["members"])
    return [Action(f"add members to role '{op['role']}'", argv)]


def _role_remove_member(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    role_id = idx.role_id(op["role"])
    # remove-member uses --org-role-ids (not --project-organize-ids).
    argv = ["app", "role", "remove-member", role_id, "-a", idx.app_id]
    argv += _member_argv(op["members"])
    return [Action(f"remove members from role '{op['role']}'", argv)]


# ── custom action (button) ───────────────────────────────────────────────
def _action_create(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    ws_id = idx.worksheet_id(op["worksheet"])
    argv = ["worksheet", "create-custom-action", ws_id, "-a", idx.app_id]
    if op.get("action_spec") is not None:
        argv += ["--action-spec",
                 json.dumps(op["action_spec"], ensure_ascii=False)]
    elif op.get("config") is not None:
        argv += ["--config", json.dumps(op["config"], ensure_ascii=False)]
    else:
        raise ResolveError(
            "custom-action.create needs 'action_spec' or 'config'")
    return [Action(f"create custom action on '{op['worksheet']}'", argv)]


def _action_update(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    ws_id = idx.worksheet_id(op["worksheet"])
    btn_id = idx.action_id(op["worksheet"], op["action"])
    # Update in place via --btn-id (shadow workflow not rebuilt, decision #11).
    argv = ["worksheet", "create-custom-action", ws_id, "-a", idx.app_id,
            "--btn-id", btn_id]
    if op.get("action_spec") is not None:
        argv += ["--action-spec",
                 json.dumps(op["action_spec"], ensure_ascii=False)]
    elif op.get("config") is not None:
        argv += ["--config", json.dumps(op["config"], ensure_ascii=False)]
    else:
        raise ResolveError(
            "custom-action.update needs 'action_spec' or 'config'")
    return [Action(f"update custom action '{op['action']}' on "
                   f"'{op['worksheet']}'", argv)]


def _action_delete(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    ws_id = idx.worksheet_id(op["worksheet"])
    btn_id = idx.action_id(op["worksheet"], op["action"])
    return [Action(f"delete custom action '{op['action']}' on "
                   f"'{op['worksheet']}'",
                   ["worksheet", "delete-custom-action", ws_id, btn_id,
                    "-a", idx.app_id])]


# ── chatbot (AI assistant) ───────────────────────────────────────────────
def _chatbot_create(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    sid = idx.section_id(op["section"]) if op.get("section") \
        else idx.first_section_id()
    argv = ["app", "chatbot", "create", idx.app_id, op["name"],
            "--section-id", sid]
    if idx.org_id:
        argv += ["--org-id", idx.org_id]
    if op.get("prompt"):
        argv += ["--prompt", op["prompt"]]
    if op.get("welcome_text"):
        argv += ["--welcome-text", op["welcome_text"]]
    for q in op.get("preset_questions", []) or []:
        argv += ["--preset-question", q]
    if op.get("remark"):
        argv += ["--remark", op["remark"]]
    return [Action(f"create chatbot '{op['name']}'", argv)]


def _chatbot_update(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    cb_id = idx.item(op["chatbot"])["id"]
    argv = ["app", "chatbot", "update-config", cb_id]
    if op.get("name"):
        argv += ["--name", op["name"]]
    if op.get("welcome_text"):
        argv += ["--welcome-text", op["welcome_text"]]
    for q in op.get("preset_questions", []) or []:
        argv += ["--preset-question", q]
    return [Action(f"update chatbot '{op['chatbot']}'", argv)]


def _chatbot_delete(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    it = idx.item(op["chatbot"])
    argv = ["app", "chatbot", "delete", it["id"], "--app-id", idx.app_id,
            "--section-id", it["section"], "--yes"]
    if idx.org_id:
        argv += ["--org-id", idx.org_id]
    if op.get("permanent"):
        argv += ["--permanent"]
    return [Action(f"delete chatbot '{op['chatbot']}'", argv)]


# ── custom page (page-level metadata) ─────────────────────────────────────
def _page_create(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    sid = idx.section_id(op["section"]) if op.get("section") \
        else idx.first_section_id()
    argv = ["custom-page", "create", idx.app_id, op["name"], "--section-id", sid]
    if op.get("icon"):
        argv += ["--icon", op["icon"]]
    if op.get("remark"):
        argv += ["--remark", op["remark"]]
    return [Action(f"create custom page '{op['name']}'", argv)]


def _page_update(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    it = idx.item(op["page"])
    argv = ["custom-page", "rename", idx.app_id, it["id"],
            "--section-id", it["section"]]
    if op.get("name"):
        argv += ["--name", op["name"]]
    if op.get("icon"):
        argv += ["--icon", op["icon"]]
    return [Action(f"update custom page '{op['page']}'", argv)]


def _page_delete(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    it = idx.item(op["page"])
    argv = ["custom-page", "delete", idx.app_id, it["id"],
            "--section-id", it["section"], "--yes"]
    if idx.org_id:
        argv += ["--org-id", idx.org_id]
    if op.get("permanent"):
        argv += ["--permanently"]
    return [Action(f"delete custom page '{op['page']}'", argv)]


# ── workflow (process-level) ──────────────────────────────────────────────
def _wf_create(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    argv = ["workflow", "create", "-c", idx.org_id, "-n", op["name"],
            "-a", idx.app_id]
    if op.get("trigger_type") is not None:
        argv += ["--type", str(op["trigger_type"])]
    if op.get("desc"):
        argv += ["-d", op["desc"]]
    return [Action(f"create workflow '{op['name']}'", argv)]


def _wf_update(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    pid = idx.workflow_id(op["workflow"])
    argv = ["workflow", "update", pid]
    if op.get("name"):
        argv += ["-n", op["name"]]
    if op.get("desc"):
        argv += ["-d", op["desc"]]
    if op.get("icon_color"):
        argv += ["--icon-color", op["icon_color"]]
    return [Action(f"update workflow '{op['workflow']}'", argv)]


def _wf_delete(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    pid = idx.workflow_id(op["workflow"])
    return [Action(f"delete workflow '{op['workflow']}'",
                   ["workflow", "delete", pid, "--yes"])]


def _wf_publish(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    pid = idx.workflow_id(op["workflow"])
    argv = ["workflow", "publish", pid]
    if op.get("disable"):
        argv += ["--disable"]
    verb = "disable" if op.get("disable") else "publish"
    return [Action(f"{verb} workflow '{op['workflow']}'", argv)]


# ── custom-page component (read-modify-write of the page layout) ──────────
def _page_save_argv(idx: AppIndex, layout: dict, components: list) -> list[str]:
    import json as _json
    return ["custom-page", "save", layout["page_id"],
            "--version", str(layout["version"]),
            "--components", _json.dumps(components, ensure_ascii=False),
            "--owner-app-id", idx.app_id]


def _component_add(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    layout = idx.page_layout(op["page"])
    components = list(layout["components"])
    components.append(lower_component(op["component"]))
    return [Action(f"add component '{op['component']['name']}' to page "
                   f"'{op['page']}'", _page_save_argv(idx, layout, components))]


def _component_name(c: dict) -> str:
    """A page component's display name lives in web.title (top-level name
    is not round-tripped by HAP); fall back to name/id."""
    return (((c.get("web") or {}).get("title")) or c.get("name")
            or c.get("id") or "")


def _component_match(components: list, name: str) -> int:
    for i, c in enumerate(components):
        if _component_name(c) == name or c.get("id") == name:
            return i
    raise ResolveError(f"component {name!r} not found on page")


def _component_update(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    layout = idx.page_layout(op["page"])
    components = [dict(c) for c in layout["components"]]
    i = _component_match(components, op["component"])
    components[i].update(op["set"])
    return [Action(f"update component '{op['component']}' on page "
                   f"'{op['page']}'", _page_save_argv(idx, layout, components))]


def _component_delete(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    layout = idx.page_layout(op["page"])
    components = [dict(c) for c in layout["components"]]
    i = _component_match(components, op["component"])
    components.pop(i)
    return [Action(f"delete component '{op['component']}' from page "
                   f"'{op['page']}'", _page_save_argv(idx, layout, components))]


# ── workflow node (basic: append-after / rename / delete) ─────────────────
# The backend rewires connections when a node is appended after a given node
# (--after) or deleted, so these are safe. Mid-branch insertion / complex
# topology rewiring is out of scope.
def _node_add(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    pid = idx.workflow_id(op["workflow"])
    node = op["node"]
    after = idx.node_id(op["workflow"], node["after"]) if node.get("after") \
        else idx.start_node_id(op["workflow"])
    argv = ["workflow", "node", "add", pid, "--type", str(node["node_type"]),
            "-n", node["name"]]
    if after:
        argv += ["--after", after]
    if node.get("action_id"):
        argv += ["--action-id", str(node["action_id"])]
    if node.get("worksheet"):
        argv += ["--app-id", idx.worksheet_id(node["worksheet"])]
    if node.get("app_type") is not None:
        argv += ["--app-type", str(node["app_type"])]
    return [Action(f"add node '{node['name']}' to workflow "
                   f"'{op['workflow']}'", argv)]


def _node_rename(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    pid = idx.workflow_id(op["workflow"])
    nid = idx.node_id(op["workflow"], op["node"])
    return [Action(f"rename node '{op['node']}' in '{op['workflow']}'",
                   ["workflow", "node", "rename", pid, nid, "-n", op["name"]])]


def _node_delete(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    pid = idx.workflow_id(op["workflow"])
    nid = idx.node_id(op["workflow"], op["node"])
    return [Action(f"delete node '{op['node']}' from '{op['workflow']}'",
                   ["workflow", "node", "delete", pid, nid, "--yes"])]


def _node_update(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    """Update an existing node's full config IN PLACE (the node id is kept,
    so wiring/position survive). Mirrors how the backend's ``node save`` works:
    read current config with ``workflow node get``, fix it, pass it back here.

    ``node_type`` (the ``--type`` enum) defaults to the node's live ``typeId``
    when omitted.
    """
    pid = idx.workflow_id(op["workflow"])
    nid = idx.node_id(op["workflow"], op["node"])
    node_type = op.get("node_type")
    if node_type is None:
        live = idx.node_obj(op["workflow"], op["node"])
        node_type = live.get("typeId", live.get("type"))
        if node_type is None:
            raise ResolveError(
                f"node.update could not determine the node type for "
                f"{op['node']!r}; pass 'node_type' explicitly "
                f"(see 'workflow node save --help' for the enum)")
    argv = ["workflow", "node", "save", pid, nid,
            "--type", str(node_type),
            "-c", json.dumps(op["config"], ensure_ascii=False)]
    if op.get("name"):
        argv += ["-n", op["name"]]
    return [Action(f"update node '{op['node']}' config in '{op['workflow']}'",
                   argv)]


# ── application & section (app-level edits) ───────────────────────────────
def _app_update(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    argv = ["app", "update", idx.app_id]
    for opt, key in (("-n", "name"), ("-d", "desc"),
                     ("--icon-color", "icon_color"), ("--nav-color", "nav_color")):
        if op.get(key):
            argv += [opt, op[key]]
    if op.get("pc_nav_style") is not None:
        argv += ["--pc-nav-style", str(op["pc_nav_style"])]
    return [Action("update application", argv)]


def _section_add(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    return [Action(f"add section '{op['name']}'",
                   ["app", "add-section", idx.app_id, "-n", op["name"]])]


def _section_update(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    sid = idx.section_id(op["section"])
    return [Action(f"rename section '{op['section']}' -> '{op['name']}'",
                   ["app", "edit-section", idx.app_id, sid, "-n", op["name"]])]


def _section_delete(op: dict[str, Any], idx: AppIndex) -> list[Action]:
    sid = idx.section_id(op["section"])
    return [Action(f"delete section '{op['section']}'",
                   ["app", "delete-section", idx.app_id, sid, "-y"])]


REGISTRY: dict[str, Callable[[dict[str, Any], AppIndex], list[Action]]] = {
    "worksheet.create": _ws_create,
    "worksheet.update": _ws_update,
    "worksheet.delete": _ws_delete,
    "field.add": _field_add,
    "field.update": _field_update,
    "field.delete": _field_delete,
    "field.reorder": _field_reorder,
    "view.create": _view_create,
    "view.update": _view_update,
    "view.delete": _view_delete,
    "role.create": _role_create,
    "role.update": _role_update,
    "role.delete": _role_delete,
    "role.add_member": _role_add_member,
    "role.remove_member": _role_remove_member,
    "custom-action.create": _action_create,
    "custom-action.update": _action_update,
    "custom-action.delete": _action_delete,
    "chatbot.create": _chatbot_create,
    "chatbot.update": _chatbot_update,
    "chatbot.delete": _chatbot_delete,
    "custom-page.create": _page_create,
    "custom-page.update": _page_update,
    "custom-page.delete": _page_delete,
    "workflow.create": _wf_create,
    "workflow.update": _wf_update,
    "workflow.delete": _wf_delete,
    "workflow.publish": _wf_publish,
    "component.add": _component_add,
    "component.update": _component_update,
    "component.delete": _component_delete,
    "node.add": _node_add,
    "node.update": _node_update,
    "node.rename": _node_rename,
    "node.delete": _node_delete,
    "app.update": _app_update,
    "section.add": _section_add,
    "section.update": _section_update,
    "section.delete": _section_delete,
}
