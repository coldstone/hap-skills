"""Exception types for the editor framework.

Kept separate so handlers, the planner, and the CLI dispatch can all
catch the same hierarchy without importing each other.
"""
from __future__ import annotations


class EditorError(Exception):
    """Base class for every error this framework raises."""


class EditSpecError(EditorError):
    """The edit-spec is structurally invalid (schema or shape).

    Carries a list of human-readable problems, each prefixed with the
    JSON path where it occurred, so the user can fix the spec before any
    API call is made.
    """

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems) if problems else "invalid edit-spec")


class ResolveError(EditorError):
    """A logical name (worksheet/field/view/...) could not be resolved to
    an id against the live app structure."""


class ConfirmRequiredError(EditorError):
    """A destructive op was requested without ``confirm: true``.

    Destructive operations (delete / overwrite) refuse to run unless the
    op object explicitly opts in — a guard against accidental data loss.
    """


class HapCommandError(EditorError):
    """The ``hap`` binary exited non-zero or returned an API error."""

    def __init__(self, message: str, *, argv=None, returncode=None,
                 stderr: str = ""):
        self.argv = argv
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(message)


class NotLoggedInError(HapCommandError):
    """The ``hap`` session is not authenticated.

    The user must run ``hap auth login`` (and select an org) before any
    live read or write can happen.
    """
