"""The single subprocess wrapper around the installed ``hap`` binary.

Every live call the editor makes goes through :func:`run`. It always
runs ``<HAP_BIN> --json <args...>`` (``--json`` first, as the CLI
requires), captures stdout/stderr, parses the JSON payload, and surfaces
auth / command failures as typed exceptions.

Shelling out to the installed binary (rather than importing hap_cli) is
deliberate: it keeps this skill independently distributable and exercises
the real command + transport path a user hits.
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Optional

from scripts import config
from scripts.errors import HapCommandError, NotLoggedInError

logger = logging.getLogger("hap_app_editor.hap")


@dataclass
class HapResult:
    """Outcome of one ``hap`` invocation."""

    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    data: Any           # parsed JSON (dict/list/scalar) or {"_raw": str}
    duration_ms: int


def _parse_stdout(stdout: str) -> Any:
    text = stdout.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text}


def _is_not_logged_in(data: Any) -> bool:
    return isinstance(data, dict) and data.get("not_logged_in") is True


def _api_error(data: Any) -> str:
    """Return an error message if the response is an API-level failure.

    The CLI exits 0 even when the HAP API rejects a request, so we must
    inspect the envelope: V3 uses ``{success, error_code, error_msg}``
    (error_code 1 = ok); main-site uses ``{state, exception}`` (state 1 =
    ok). Returns "" when the response indicates success.
    """
    if not isinstance(data, dict):
        return ""
    if data.get("success") is False:
        return str(data.get("error_msg") or data.get("error") or "API error")
    ec = data.get("error_code")
    if ec is not None and ec != 1 and data.get("success") is not True:
        return str(data.get("error_msg") or data.get("error")
                   or f"error_code {ec}")
    st = data.get("state")
    if st is not None and st != 1 and "data" not in data:
        return str(data.get("exception") or f"state {st}")
    if isinstance(data.get("error"), str) and data["error"]:
        return data["error"]
    return ""


# Markers of a transient network failure worth retrying (TLS resets and
# connection drops to the HAP host are intermittent, not real errors).
_TRANSIENT_MARKERS = (
    "SSLError", "SSLEOFError", "UNEXPECTED_EOF", "Max retries",
    "Connection aborted", "ConnectionError", "timed out", "RemoteDisconnected",
)
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_S = 1.5


def _looks_transient(stdout: str, stderr: str) -> bool:
    blob = f"{stdout}\n{stderr}"
    return any(m in blob for m in _TRANSIENT_MARKERS)


def run(
    args: list[str],
    *,
    timeout: Optional[int] = None,
    check: bool = True,
) -> HapResult:
    """Run ``hap --json <args>`` and return a :class:`HapResult`.

    Transient network failures (TLS resets, connection drops) are retried
    a few times with a short backoff. Raises :class:`NotLoggedInError` if
    the CLI reports no session, and :class:`HapCommandError` on a
    non-zero exit when ``check`` is true.
    """
    argv = [config.HAP_BIN, "--json", *args]
    logger.info("HAP %s", " ".join(argv))
    start = time.monotonic()
    proc = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout if timeout is not None else config.HAP_TIMEOUT,
        )
        if proc.returncode == 0 or not _looks_transient(proc.stdout, proc.stderr):
            break
        if attempt < _MAX_ATTEMPTS:
            logger.warning("HAP %s transient failure (attempt %d/%d), retrying",
                           " ".join(args), attempt, _MAX_ATTEMPTS)
            time.sleep(_RETRY_BACKOFF_S * attempt)
    duration_ms = int((time.monotonic() - start) * 1000)
    data = _parse_stdout(proc.stdout)
    snippet = (proc.stdout or proc.stderr or "").strip().replace("\n", " ")[:200]
    logger.info("HAP %s -> %s %s", " ".join(args), proc.returncode, snippet)

    if _is_not_logged_in(data):
        raise NotLoggedInError(
            "Not logged in. Run 'hap auth login' and select an org first.",
            argv=argv, returncode=proc.returncode, stderr=proc.stderr,
        )
    if check and proc.returncode != 0:
        raise HapCommandError(
            f"hap {' '.join(args)} failed (exit {proc.returncode}): "
            f"{proc.stderr.strip() or snippet}",
            argv=argv, returncode=proc.returncode, stderr=proc.stderr,
        )
    if check:
        api_err = _api_error(data)
        if api_err:
            raise HapCommandError(
                f"hap {' '.join(args)} rejected by API: {api_err}",
                argv=argv, returncode=proc.returncode, stderr=proc.stderr,
            )
    return HapResult(argv, proc.returncode, proc.stdout, proc.stderr,
                     data, duration_ms)


def whoami() -> dict[str, Any]:
    """Return the current session identity (id, current_org_id, ...)."""
    res = run(["auth", "whoami"])
    return res.data if isinstance(res.data, dict) else {}


def unwrap(data: Any) -> Any:
    """Return the meaningful payload from a CLI response.

    The CLI emits either the bare value or an envelope; callers usually
    want ``data['data']`` when present (the main-site ``{state,data}``
    shape passed through), else the value itself.
    """
    if isinstance(data, dict) and "data" in data and set(data.keys()) <= {
        "data", "state", "exception", "success", "error_code", "code",
    }:
        return data["data"]
    return data
