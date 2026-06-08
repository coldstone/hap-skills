"""Shared dataclasses, kept dependency-free to avoid import cycles."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Action:
    """One concrete ``hap`` invocation the apply step will run.

    ``description`` is the human line shown in the plan; ``argv`` is the
    exact argument vector passed to the ``hap`` binary (no shell).
    """

    description: str
    argv: list[str]


@dataclass
class PlannedOp:
    """An op together with the actions it expands into."""

    index: int
    op: dict[str, Any]
    actions: "list[Action]" = field(default_factory=list)


@dataclass
class OpOutcome:
    """Result of applying one op."""

    index: int
    op_type: str
    status: str          # "ok" | "error"
    detail: str = ""
    responses: "list[Any]" = field(default_factory=list)
