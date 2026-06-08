"""Local, network-free self-checks for the editor framework.

Run with ``python3 -m scripts selftest``. Covers (mock-only):
  - edit-spec validation: valid passes; bad shape / missing confirm fail
  - module-local dispatch: a field-only spec validates
  - confirm gate: destructive op without confirm is refused
  - planner: build_plan -> Actions argv is what apply would run (one path)
  - reader: AppIndex resolves names -> ids from canned hap output

Exit 0 = all pass, 1 = a failure (printed).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Callable

from scripts import hap
from scripts.editspec_loader import load_spec, validate_spec
from scripts.errors import ConfirmRequiredError, EditSpecError
from scripts.models import OpOutcome
from scripts.planner import build_plan
from scripts.reader import AppIndex

_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok  {name}")
    else:
        _failures.append(f"{name}: {detail}")
        print(f"  FAIL {name}: {detail}")


def expect_raises(name: str, exc_type, fn: Callable) -> None:
    try:
        fn()
    except exc_type:
        print(f"  ok  {name}")
    except Exception as e:  # noqa: BLE001
        _failures.append(f"{name}: wrong exception {type(e).__name__}: {e}")
        print(f"  FAIL {name}: expected {exc_type.__name__}, got "
              f"{type(e).__name__}: {e}")
    else:
        _failures.append(f"{name}: no exception raised")
        print(f"  FAIL {name}: expected {exc_type.__name__}, none raised")


# ── canned app index (no network) ───────────────────────────────────────
def _fake_index() -> AppIndex:
    detail = {
        "name": "Demo",
        "sections": [{
            "id": "sec1", "name": "默认",
            "items": [
                {"id": "ws1", "name": "订单", "type": 0},
                {"id": "ws2", "name": "客户", "type": 0},
            ],
        }],
    }
    return AppIndex("app1", "org1", detail)


@dataclass
class _FakeRes:
    data: Any


def _install_fake_hap(view_list: list[dict],
                      controls: list[dict] | None = None) -> Callable:
    """Patch hap.run to answer view-list / fields lookups from canned data."""
    original = hap.run

    def fake_run(args, **kw):
        if args[:3] == ["worksheet", "view", "list"]:
            return _FakeRes(view_list)
        if args[:2] == ["worksheet", "fields"]:
            return _FakeRes(controls or [])
        if args[:3] == ["app", "role", "list"]:
            return _FakeRes({"roles": [{"id": "r9", "name": "审批员"}]})
        if args[:2] == ["worksheet", "custom-actions"]:
            return _FakeRes([{"btnId": "b9", "name": "提交"}])
        if args[:2] == ["workflow", "list"]:
            return _FakeRes([{"id": "p9", "name": "审批流"}])
        if args[:2] == ["custom-page", "info"]:
            return _FakeRes({"version": 3, "components": [
                {"type": 2, "name": "说明", "value": "old"}]})
        if args[:3] == ["workflow", "node", "list"]:
            return _FakeRes({"startEventId": "start1", "flowNodeMap": {
                "start1": {"id": "start1", "name": "定时触发", "typeId": 0},
                "n2": {"id": "n2", "name": "通知", "typeId": 13}}})
        return _FakeRes({})

    hap.run = fake_run  # type: ignore[assignment]
    return original


# ── tests ───────────────────────────────────────────────────────────────
def test_validation() -> None:
    print("validation:")
    good = {"app": "app1", "ops": [
        {"type": "worksheet.create", "name": "新表", "section": "默认"},
        {"type": "view.update", "worksheet": "订单", "view": "看板",
         "name": "看板B", "edit_attrs": ["name"]},
        {"type": "worksheet.delete", "worksheet": "旧表", "confirm": True},
    ]}
    try:
        validate_spec(good)
        check("valid spec passes", True)
    except EditSpecError as e:
        check("valid spec passes", False, str(e.problems))

    expect_raises("missing required 'name' fails", EditSpecError,
                  lambda: validate_spec(
                      {"app": "a", "ops": [{"type": "worksheet.create"}]}))
    expect_raises("unknown op type fails", EditSpecError,
                  lambda: validate_spec(
                      {"app": "a", "ops": [{"type": "bogus.thing"}]}))
    expect_raises("delete without confirm fails schema", EditSpecError,
                  lambda: validate_spec(
                      {"app": "a", "ops": [
                          {"type": "worksheet.delete", "worksheet": "x"}]}))
    # field-only spec exercises module-local dispatch.
    try:
        validate_spec({"app": "a", "ops": [
            {"type": "field.add", "worksheet": "订单",
             "field": {"name": "金额", "type": "Number"}}]})
        check("field-only spec validates (module dispatch)", True)
    except EditSpecError as e:
        check("field-only spec validates (module dispatch)", False,
              str(e.problems))


def test_confirm_gate() -> None:
    print("confirm gate:")
    idx = _fake_index()
    expect_raises("destructive op without confirm refused", ConfirmRequiredError,
                  lambda: build_plan(
                      {"app": "app1", "ops": [
                          {"type": "worksheet.delete", "worksheet": "订单"}]},
                      idx))


def test_planner_argv() -> None:
    print("planner argv (plan == apply path):")
    idx = _fake_index()
    spec = {"app": "app1", "ops": [
        {"type": "worksheet.create", "name": "新表", "section": "默认"},
        {"type": "worksheet.delete", "worksheet": "客户", "confirm": True},
    ]}
    planned = build_plan(spec, idx)
    a0 = planned[0].actions[0].argv
    check("worksheet.create resolves section to id",
          a0 == ["worksheet", "create", "app1", "新表",
                 "--section-id", "sec1"], str(a0))
    a1 = planned[1].actions[0].argv
    check("worksheet.delete resolves name to id",
          a1 == ["worksheet", "delete", "ws2", "-a", "app1"], str(a1))


def test_view_resolution() -> None:
    print("view name resolution:")
    original = _install_fake_hap([{"viewId": "v9", "name": "看板"}])
    try:
        idx = _fake_index()
        spec = {"app": "app1", "ops": [
            {"type": "view.update", "worksheet": "订单", "view": "看板",
             "name": "看板B", "edit_attrs": ["name"]}]}
        planned = build_plan(spec, idx)
        argv = planned[0].actions[0].argv
        check("view.update resolves view name to id and sets edit-attrs",
              argv[:6] == ["worksheet", "view", "update", "ws1", "v9", "-a"]
              and "--edit-attrs" in argv, str(argv))
    finally:
        hap.run = original  # type: ignore[assignment]


def test_field_ops() -> None:
    print("field ops (lowering + read-modify-write):")
    import json as _json
    controls = [
        {"controlId": "c1", "controlName": "名称", "type": 2},
        {"controlId": "c2", "controlName": "金额", "type": 6},
        {"controlId": "rev", "controlName": "反向关联", "type": 29},
    ]
    original = _install_fake_hap([], controls)
    try:
        idx = _fake_index()
        # add: incremental, lowered control
        add = build_plan({"app": "app1", "ops": [
            {"type": "field.add", "worksheet": "订单",
             "field": {"name": "状态", "type": "SingleSelect",
                       "options": ["新", "完成"]}}]}, idx)
        argv = add[0].actions[0].argv
        check("field.add uses add-fields (incremental)",
              argv[:3] == ["worksheet", "add-fields", "ws1"], str(argv[:3]))
        ctrl = _json.loads(argv[argv.index("--controls") + 1])[0]
        check("field.add lowers type + options",
              ctrl["type"] == 9 and ctrl["controlName"] == "状态"
              and len(ctrl["options"]) == 2, str(ctrl))

        # delete: write-back of remaining controls (reverse control kept)
        idx.refresh = lambda: None  # avoid network on refresh in this unit
        dele = build_plan({"app": "app1", "ops": [
            {"type": "field.delete", "worksheet": "订单",
             "field": "金额", "confirm": True}]}, idx)
        argv = dele[0].actions[0].argv
        check("field.delete uses update-fields (full write-back)",
              argv[:3] == ["worksheet", "update-fields", "ws1"], str(argv[:3]))
        remaining = _json.loads(argv[argv.index("--controls") + 1])
        ids = [c["controlId"] for c in remaining]
        check("field.delete drops target, keeps reverse control",
              "c2" not in ids and "rev" in ids and "c1" in ids, str(ids))
    finally:
        hap.run = original  # type: ignore[assignment]


def test_p2_ops() -> None:
    print("role + custom-action ops:")
    original = _install_fake_hap([])
    try:
        idx = _fake_index()
        idx.refresh = lambda: None
        # role.create argv
        rc = build_plan({"app": "app1", "ops": [
            {"type": "role.create", "name": "审批员", "description": "审批"}]}, idx)
        argv = rc[0].actions[0].argv
        check("role.create sets type 0 + permission-scope",
              "--type" in argv and argv[argv.index("--type") + 1] == "0"
              and "--permission-scope" in argv, str(argv))
        # role.delete needs confirm
        expect_raises("role.delete without confirm refused", ConfirmRequiredError,
                      lambda: build_plan({"app": "app1", "ops": [
                          {"type": "role.delete", "role": "审批员"}]}, idx))
        # role.delete resolves name -> id
        rd = build_plan({"app": "app1", "ops": [
            {"type": "role.delete", "role": "审批员", "confirm": True}]}, idx)
        check("role.delete resolves name to id",
              rd[0].actions[0].argv == ["app", "role", "delete", "r9",
                                        "-a", "app1"],
              str(rd[0].actions[0].argv))
        # role.add_member builds member options
        ra = build_plan({"app": "app1", "ops": [
            {"type": "role.add_member", "role": "审批员",
             "members": {"user_ids": ["u1", "u2"]}}]}, idx)
        argv = ra[0].actions[0].argv
        check("role.add_member passes --user-ids",
              "--user-ids" in argv and argv[argv.index("--user-ids") + 1] == "u1,u2",
              str(argv))
        # custom-action.update uses --btn-id (in-place, decision #11)
        ca = build_plan({"app": "app1", "ops": [
            {"type": "custom-action.update", "worksheet": "订单",
             "action": "提交", "action_spec": {"type": 1}}]}, idx)
        argv = ca[0].actions[0].argv
        check("custom-action.update updates in place via --btn-id",
              "--btn-id" in argv and argv[argv.index("--btn-id") + 1] == "b9",
              str(argv))
    finally:
        hap.run = original  # type: ignore[assignment]


def test_p3_ops() -> None:
    print("chatbot + custom-page + workflow ops:")
    original = _install_fake_hap([])
    try:
        idx = _fake_index()
        idx.refresh = lambda: None
        cb = build_plan({"app": "app1", "ops": [
            {"type": "chatbot.create", "name": "助手", "prompt": "p"}]}, idx)
        argv = cb[0].actions[0].argv
        check("chatbot.create resolves section + org",
              argv[:5] == ["app", "chatbot", "create", "app1", "助手"]
              and "--org-id" in argv, str(argv))
        pg = build_plan({"app": "app1", "ops": [
            {"type": "custom-page.create", "name": "看板页"}]}, idx)
        argv = pg[0].actions[0].argv
        check("custom-page.create has section-id",
              argv[:4] == ["custom-page", "create", "app1", "看板页"]
              and "--section-id" in argv, str(argv))
        wf = build_plan({"app": "app1", "ops": [
            {"type": "workflow.create", "name": "审批流"}]}, idx)
        argv = wf[0].actions[0].argv
        check("workflow.create passes -c org -a app",
              "-c" in argv and "org1" in argv and "-a" in argv, str(argv))
        expect_raises("workflow.delete without confirm refused",
                      ConfirmRequiredError,
                      lambda: build_plan({"app": "app1", "ops": [
                          {"type": "workflow.delete", "workflow": "审批流"}]},
                          idx))
        wd = build_plan({"app": "app1", "ops": [
            {"type": "workflow.delete", "workflow": "审批流", "confirm": True}]},
            idx)
        check("workflow.delete resolves name to id",
              wd[0].actions[0].argv == ["workflow", "delete", "p9", "--yes"],
              str(wd[0].actions[0].argv))
    finally:
        hap.run = original  # type: ignore[assignment]


def test_component_ops() -> None:
    print("component ops (page read-modify-write):")
    import json as _json
    detail = {"name": "Demo", "sections": [{"id": "sec1", "name": "默认",
              "items": [{"id": "pg1", "name": "首页", "type": 1}]}]}
    idx = AppIndex("app1", "org1", detail)
    idx.refresh = lambda: None
    original = _install_fake_hap([])
    try:
        add = build_plan({"app": "app1", "ops": [
            {"type": "component.add", "page": "首页",
             "component": {"name": "公告", "type": "richText",
                           "value": "<p>hi</p>"}}]}, idx)
        argv = add[0].actions[0].argv
        check("component.add saves to pageId with owner-app-id",
              argv[:3] == ["custom-page", "save", "pg1"]
              and "--owner-app-id" in argv, str(argv[:3]))
        comps = _json.loads(argv[argv.index("--components") + 1])
        names = [c["name"] for c in comps]
        check("component.add appends to existing components",
              names == ["说明", "公告"] and comps[1]["type"] == 2, str(names))
        # delete: keeps the others
        dele = build_plan({"app": "app1", "ops": [
            {"type": "component.delete", "page": "首页",
             "component": "说明", "confirm": True}]}, idx)
        comps = _json.loads(dele[0].actions[0].argv[
            dele[0].actions[0].argv.index("--components") + 1])
        check("component.delete drops target, version preserved",
              comps == [] and "--version" in dele[0].actions[0].argv,
              str(comps))
    finally:
        hap.run = original  # type: ignore[assignment]


def test_node_ops() -> None:
    print("workflow node ops:")
    original = _install_fake_hap([])
    try:
        idx = _fake_index()
        idx.refresh = lambda: None
        add = build_plan({"app": "app1", "ops": [
            {"type": "node.add", "workflow": "审批流",
             "node": {"name": "审批", "node_type": 13}}]}, idx)
        argv = add[0].actions[0].argv
        check("node.add defaults --after to start node",
              "--after" in argv and argv[argv.index("--after") + 1] == "start1"
              and "--type" in argv, str(argv))
        rn = build_plan({"app": "app1", "ops": [
            {"type": "node.rename", "workflow": "审批流", "node": "通知",
             "name": "新通知"}]}, idx)
        check("node.rename resolves node name to id",
              rn[0].actions[0].argv == ["workflow", "node", "rename", "p9",
                                        "n2", "-n", "新通知"],
              str(rn[0].actions[0].argv))
        expect_raises("node.delete without confirm refused", ConfirmRequiredError,
                      lambda: build_plan({"app": "app1", "ops": [
                          {"type": "node.delete", "workflow": "审批流",
                           "node": "通知"}]}, idx))
        # node.update: in-place save; --type defaults to the live typeId.
        import json as _json
        up = build_plan({"app": "app1", "ops": [
            {"type": "node.update", "workflow": "审批流", "node": "通知",
             "config": {"accounts": [{"a": 1}]}}]}, idx)
        argv = up[0].actions[0].argv
        check("node.update saves config in place via 'node save'",
              argv[:5] == ["workflow", "node", "save", "p9", "n2"], str(argv))
        check("node.update defaults --type to live typeId (13)",
              "--type" in argv and argv[argv.index("--type") + 1] == "13",
              str(argv))
        cfg = _json.loads(argv[argv.index("-c") + 1])
        check("node.update passes the corrected config through",
              cfg == {"accounts": [{"a": 1}]}, str(cfg))
        # explicit node_type overrides the default
        up2 = build_plan({"app": "app1", "ops": [
            {"type": "node.update", "workflow": "审批流", "node": "通知",
             "node_type": 27, "config": {}, "name": "改名通知"}]}, idx)
        argv2 = up2[0].actions[0].argv
        check("node.update honours explicit node_type + name",
              argv2[argv2.index("--type") + 1] == "27"
              and "-n" in argv2 and argv2[argv2.index("-n") + 1] == "改名通知",
              str(argv2))
    finally:
        hap.run = original  # type: ignore[assignment]


def test_app_ops() -> None:
    print("application + section ops:")
    idx = _fake_index()
    idx.refresh = lambda: None
    au = build_plan({"app": "app1", "ops": [
        {"type": "app.update", "name": "新名", "nav_color": "#fff"}]}, idx)
    argv = au[0].actions[0].argv
    check("app.update targets app id with options",
          argv[:3] == ["app", "update", "app1"] and "-n" in argv
          and "--nav-color" in argv, str(argv))
    su = build_plan({"app": "app1", "ops": [
        {"type": "section.update", "section": "默认", "name": "主区"}]}, idx)
    check("section.update resolves section name to id",
          su[0].actions[0].argv == ["app", "edit-section", "app1", "sec1",
                                     "-n", "主区"], str(su[0].actions[0].argv))
    expect_raises("section.delete without confirm refused", ConfirmRequiredError,
                  lambda: build_plan({"app": "app1", "ops": [
                      {"type": "section.delete", "section": "默认"}]}, idx))


def main(argv: list[str] | None = None) -> int:
    test_validation()
    test_confirm_gate()
    test_planner_argv()
    test_view_resolution()
    test_field_ops()
    test_p2_ops()
    test_p3_ops()
    test_component_ops()
    test_node_ops()
    test_app_ops()
    print()
    if _failures:
        print(f"SELFTEST FAILED: {len(_failures)} problem(s)")
        return 1
    print("SELFTEST PASSED")
    return 0
