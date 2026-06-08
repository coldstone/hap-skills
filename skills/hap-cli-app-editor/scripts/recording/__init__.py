"""Lightweight run recording for the editor (self-contained).

A :class:`Recorder` appends one JSON line per op outcome to a JSONL file
and echoes a short status line to stdout. Recording is optional — apply
works without one — but it gives an auditable trail of what changed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from scripts.models import OpOutcome


class Recorder:
    def __init__(self, jsonl_path: Optional[Path] = None, *, echo: bool = True):
        self.jsonl_path = jsonl_path
        self.echo = echo
        if jsonl_path:
            jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, outcome: OpOutcome) -> None:
        line = {
            "index": outcome.index,
            "type": outcome.op_type,
            "status": outcome.status,
            "detail": outcome.detail,
        }
        if self.jsonl_path:
            with self.jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        if self.echo:
            mark = "OK " if outcome.status == "ok" else "ERR"
            tail = f" — {outcome.detail}" if outcome.detail else ""
            print(f"  [{mark}] [{outcome.index}] {outcome.op_type}{tail}")
