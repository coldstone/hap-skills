"""``python -m scripts <validate|plan|apply|inspect|selftest> ...`` dispatch.

  validate <edit-spec.json>                 local schema check, no API calls
  inspect  <appId|name> [--org ID]          print live name->id structure
  plan     [appId] <edit-spec.json>         dry-run: show the hap calls
  apply    [appId] <edit-spec.json>         execute the edit-spec
  selftest                                  framework self-checks (local)
"""
from __future__ import annotations

import sys

_USAGE = __doc__


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(_USAGE)
        return 0 if argv else 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "validate":
        from scripts.validate import main as run
    elif cmd == "inspect":
        from scripts.inspect import main as run
    elif cmd == "plan":
        from scripts.plan import main as run
    elif cmd == "apply":
        from scripts.apply import main as run
    elif cmd == "selftest":
        from scripts.selftest import main as run
    else:
        print(f"unknown command: {cmd}\n{_USAGE}", file=sys.stderr)
        return 1
    return run(rest)


if __name__ == "__main__":
    raise SystemExit(main())
