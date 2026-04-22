# -*- coding: utf-8 -*-
# Author: Tay Othman
"""AIBlock configuration and shared utilities.

Centralized config for the AI Assistant guard system.
Stores password hash, authorized user list, and guard state.

Config priority (highest to lowest):
  1. Network config  → set via AIBLOCK_NETWORK_CONFIG env var (UNC path)
  2. Local config    → %APPDATA%\\AIBlock\\config.json
  3. Defaults        → hardcoded below

When a network config exists and is reachable, it wins for all
fields it defines. IT pushes one file, every machine picks it up.
If the network path is unreachable, local config is used as fallback.
"""
import os
import hashlib
import json
import socket
import uuid

# -------------------------------------------------------------------
# Version
# -------------------------------------------------------------------
# Surfaced in Diagnostics, Settings → View Config, and the shared
# audit log so an incident can always be pinned to a specific build.
# Bump on any behavioural change to the enforcement path, the hook
# contract, or the config schema. Cosmetic UI-only changes can reuse
# the prior version.
__version__ = "1.0.0-rc1"


# -------------------------------------------------------------------
# Per-session identifiers
# -------------------------------------------------------------------
# Stamped on every audit log line and every trace log line so that
# the shared network audit log can be joined back to a specific
# machine's local %TEMP%\\aiblock_trace.log when diagnosing an
# incident.
#
# Session id rotates on every pyRevit reload — each reload creates
# a fresh module-level dict. That's intentional: a reload also
# re-registers the IUpdater, so treating it as a new session keeps
# the audit trail honest.
#
# Revit version is resolved lazily to avoid making aiblock/__init__
# depend on pyRevit's import order (updater.py and the hooks may
# import aiblock before pyRevit has fully bootstrapped in edge
# cases). First log_event() call resolves and caches it.
_HOSTNAME = socket.gethostname() or "unknown"
_SESSION_ID = uuid.uuid4().hex[:8]
_revit_version_cached = None


def get_session_id():
    """8-hex-char per-session identifier for audit-to-trace correlation."""
    return _SESSION_ID


def get_hostname():
    """Machine hostname as stamped on audit lines."""
    return _HOSTNAME


def get_revit_version():
    """Revit major version string (e.g. '2027'). Lazy + cached."""
    global _revit_version_cached
    if _revit_version_cached is None:
        try:
            from pyrevit import HOST_APP
            _revit_version_cached = str(HOST_APP.version)
        except Exception:
            _revit_version_cached = "unknown"
    return _revit_version_cached


# -------------------------------------------------------------------
# Assistant identity (extracted from Revit 2027 journal analysis)
# -------------------------------------------------------------------
ASSISTANT_ADDIN_ID = "f0da0f43-cd76-4945-968b-4c4e0a769298"
ASSISTANT_PANE_GUID = "3e852507-4f81-4234-b0d8-15c61ca8a261"
ASSISTANT_COMMAND_ID = "ID_TOGGLE_AUTODESK_ASSISTANT"


# -------------------------------------------------------------------
# Enforcement modes
# -------------------------------------------------------------------
# The mode is the single source of truth for BIM Management Team
# policy. It is set in config (network wins over local) and read by
# every enforcement surface — the panel-open hook, the transaction
# updater, and the UI buttons. Values are strings rather than
# enums/ints so they survive JSON round-trips cleanly and are legible
# to anyone who opens config.json in Notepad.
#
#   MODE_BLOCK_ALL       — Assistant panel cannot open. Even if it
#                          somehow opens, writes are blocked too.
#                          No per-user override of any kind.
#   MODE_BLOCK_WRITES    — Assistant panel opens normally. Queries
#                          (queryModel etc.) run. Every AI-originated
#                          transaction is rolled back silently. No
#                          per-user override.
#   MODE_USER_CONTROLLED — AI Guard button (password-gated) toggles
#                          between "writes blocked" and "fully open".
#                          This is the "trust but allow opt-out"
#                          posture and preserves the legacy behaviour
#                          of the pre-mode code path.
# -------------------------------------------------------------------
MODE_BLOCK_ALL = "block_all"
MODE_BLOCK_WRITES = "block_writes"
MODE_USER_CONTROLLED = "user_controlled"

VALID_MODES = (MODE_BLOCK_ALL, MODE_BLOCK_WRITES, MODE_USER_CONTROLLED)

MODE_LABELS = {
    MODE_BLOCK_ALL: "Block all AI",
    MODE_BLOCK_WRITES: "Block AI writes (allow queries)",
    MODE_USER_CONTROLLED: "User-controlled (password toggle)",
}

MODE_DESCRIPTIONS = {
    MODE_BLOCK_ALL: (
        "The Autodesk Assistant cannot be opened. No queries, no "
        "writes. Requires the BIM Management Team password to change."
    ),
    MODE_BLOCK_WRITES: (
        "The Assistant can be opened for read-only use (queries and "
        "reports). Any AI attempt to modify the model is rolled back "
        "silently. Requires the BIM Management Team password to change."
    ),
    MODE_USER_CONTROLLED: (
        "AI is enabled by default. Users with the override password "
        "can flip the AI Guard button to block writes for their "
        "current session."
    ),
}

# -------------------------------------------------------------------
# Config file locations
# -------------------------------------------------------------------
# Network config — IT sets this env var via GPO/SCCM/Intune
# Example: \\server\share\BIM\AIBlock\config.json
_NETWORK_CONFIG_PATH = os.environ.get("AIBLOCK_NETWORK_CONFIG", "")

# Local config — per-user fallback
_LOCAL_CONFIG_DIR = os.path.join(
    os.environ.get("APPDATA", ""),
    "AIBlock"
)
_LOCAL_CONFIG_PATH = os.path.join(_LOCAL_CONFIG_DIR, "config.json")

# -------------------------------------------------------------------
# Default config
# -------------------------------------------------------------------
# The default password ships on every install and MUST be rotated by the
# BIM Manager before the extension is trusted with firm policy. The
# Settings UI nags on entry when this hash is still active so nobody
# deploys with "AIBlock2026" in the wild by accident.
_DEFAULT_PASSWORD = "AIBlock2026"
_DEFAULT_PASSWORD_HASH = hashlib.sha256(
    _DEFAULT_PASSWORD.encode("utf-8")
).hexdigest()

_DEFAULT_CONFIG = {
    # SHA-256 hash of the override password.
    # Rotate via Settings → Change Password or via network config.
    "password_hash": _DEFAULT_PASSWORD_HASH,

    # Windows usernames that bypass the guard entirely
    # (domain prefix stripped — just the short username)
    "authorized_users": [],

    # BIM Management Team policy. See MODE_* constants above.
    # block_writes is the safer-by-default choice: lets teams use the
    # Assistant for queries immediately while preventing any
    # unreviewed model mutations from landing.
    "mode": MODE_BLOCK_WRITES,

    # Legacy per-session toggle, meaningful ONLY in MODE_USER_CONTROLLED.
    # In the other modes this flag is ignored by the enforcement layer.
    "guard_enabled": True,

    # Log override attempts to a shared network path
    "log_path": "",

    # Also block the Public MCP Server add-on if installed
    "block_public_mcp": True,

    # Verbose trace log at %TEMP%\AIBlock\trace.log. One line per
    # transaction through the IUpdater + a few startup markers.
    # Useful for diagnosing whether interception fires and what's on
    # the managed stack. Defaults to True for pre-release so field
    # reports include the trace; flip to False once the interception
    # path is proven stable at the firm.
    "verbose_trace": True,
}


def _ensure_local_config_dir():
    """Create local config directory if it doesn't exist."""
    if not os.path.exists(_LOCAL_CONFIG_DIR):
        os.makedirs(_LOCAL_CONFIG_DIR)


def _read_json(path):
    """Read a JSON file, return dict or None on failure."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (IOError, OSError, ValueError):
        return None


def load_config():
    """Load config with network → local → default priority.

    Network config (if reachable) overrides all fields it defines.
    Local config is the fallback when network is unavailable.
    Defaults fill in any missing keys.
    """
    # Start with defaults
    merged = dict(_DEFAULT_CONFIG)

    # Layer 1: local config
    local = _read_json(_LOCAL_CONFIG_PATH)
    if local:
        merged.update(local)

    # Layer 2: network config (wins over local for all fields it defines)
    if _NETWORK_CONFIG_PATH:
        network = _read_json(_NETWORK_CONFIG_PATH)
        if network:
            # Merge authorized_users — combine network + local lists
            local_users = set(
                u.lower() for u in merged.get("authorized_users", [])
            )
            network_users = set(
                u.lower() for u in network.get("authorized_users", [])
            )
            combined_users = sorted(local_users | network_users)

            # Network wins for everything else
            merged.update(network)

            # Restore combined user list
            merged["authorized_users"] = combined_users

    return merged


def save_config(config):
    """Persist config to local disk.

    Note: This only writes to the LOCAL config file.
    Network config is managed by IT — never written by the extension.
    """
    _ensure_local_config_dir()
    with open(_LOCAL_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def is_network_managed():
    """Return True if a network config path is set and reachable."""
    if not _NETWORK_CONFIG_PATH:
        return False
    return os.path.exists(_NETWORK_CONFIG_PATH)


def get_config_source():
    """Return which config source is active — for display in Settings."""
    if _NETWORK_CONFIG_PATH and os.path.exists(_NETWORK_CONFIG_PATH):
        return "Network: {}".format(_NETWORK_CONFIG_PATH)
    elif os.path.exists(_LOCAL_CONFIG_PATH):
        return "Local: {}".format(_LOCAL_CONFIG_PATH)
    else:
        return "Defaults (no config file found)"


def check_password(plain_text):
    """Return True if the plain-text password matches the stored hash."""
    config = load_config()
    candidate = hashlib.sha256(plain_text.encode("utf-8")).hexdigest()
    return candidate == config["password_hash"]


def is_default_password():
    """Return True if the stored hash still matches the shipped default.

    Used by the Settings UI to nudge a BIM Manager to pick a
    firm-specific password on first use. This is a deployment-hygiene
    check, not a security one — the password is a speed-bump against
    casual toggles, not a hard boundary (a determined user can always
    uninstall pyRevit). A network-managed deployment can pre-rotate
    the hash in the UNC config, in which case this returns False even
    on a fresh install.
    """
    config = load_config()
    return config.get("password_hash") == _DEFAULT_PASSWORD_HASH


def set_password(new_plain_text):
    """Update the stored password hash (local config only)."""
    config = load_config()
    config["password_hash"] = hashlib.sha256(
        new_plain_text.encode("utf-8")
    ).hexdigest()
    save_config(config)


def is_user_authorized(username=None):
    """Check if the current Windows user is on the bypass list."""
    if username is None:
        username = os.environ.get("USERNAME", "").lower()
    else:
        username = username.lower()
    config = load_config()
    authorized = [u.lower() for u in config.get("authorized_users", [])]
    return username in authorized


def is_guard_enabled():
    """Return True if the per-session user toggle is on.

    This is the raw config flag. It is ONLY meaningful in
    MODE_USER_CONTROLLED — the other modes ignore it and enforce
    their policy unconditionally. Call sites making policy decisions
    should prefer `should_block_ai_writes()` / `should_block_ai_panel()`
    instead of reading this flag directly.
    """
    config = load_config()
    return config.get("guard_enabled", True)


def get_mode():
    """Return the currently active enforcement mode.

    Falls back to MODE_BLOCK_WRITES if the config value is missing
    or unrecognised — the safer default for a fail-closed policy.
    """
    config = load_config()
    mode = config.get("mode", MODE_BLOCK_WRITES)
    if mode not in VALID_MODES:
        return MODE_BLOCK_WRITES
    return mode


def set_mode(new_mode):
    """Persist a mode change to LOCAL config.

    Network config always wins at read time, so a BIM team that pushes
    a mode via AIBLOCK_NETWORK_CONFIG will override anything a user
    (or the Settings UI) writes locally. This lets IT lock the policy
    firm-wide without racing against per-machine edits.
    """
    if new_mode not in VALID_MODES:
        raise ValueError(
            "Invalid mode: {!r}. Must be one of {}".format(
                new_mode, VALID_MODES,
            )
        )
    config = load_config()
    config["mode"] = new_mode
    save_config(config)


def should_block_ai_panel():
    """True when the Autodesk Assistant panel must NOT be opened.

    Only MODE_BLOCK_ALL reaches this — the other two modes let the
    panel open and rely on the transaction-layer updater (or the
    user's per-session toggle) to enforce writes policy.
    """
    return get_mode() == MODE_BLOCK_ALL


def should_block_ai_writes():
    """True when AI-originated transactions must be rolled back.

    This is the single predicate the IUpdater consults. In both
    MODE_BLOCK_ALL and MODE_BLOCK_WRITES the answer is a hard yes —
    writes are blocked irrespective of the user's guard_enabled flag.
    In MODE_USER_CONTROLLED the answer reflects the per-session toggle.
    """
    mode = get_mode()
    if mode in (MODE_BLOCK_ALL, MODE_BLOCK_WRITES):
        return True
    return is_guard_enabled()


def is_bim_locked():
    """True when the mode is BIM-enforced and users cannot flip it
    via the AI Guard toggle button.

    UI surfaces use this to decide whether to show the toggle as
    interactive or as a read-only status pill with a "contact your
    BIM Manager" message.
    """
    return get_mode() in (MODE_BLOCK_ALL, MODE_BLOCK_WRITES)


def log_event(event_type, username, details=""):
    """Append a structured audit record to the shared log file.

    Format is JSONL — one JSON object per line, UTF-8, ensure_ascii
    on so non-ASCII usernames stay grep-safe. One line carries the
    full envelope so auditors never have to join against a separate
    "session metadata" stream:

        ts              UTC ISO 8601 with trailing Z
        event           caller-supplied event type
        user            Windows username (domain prefix already stripped
                        by callers)
        host            machine hostname (resolved once at import)
        revit_version   Revit major version, e.g. "2027"
        aiblock_version extension build, e.g. "1.0.0-rc1"
        session_id      8-hex-char per-Revit-session id — correlates
                        with lines in %TEMP%\\aiblock_trace.log
        mode            current enforcement mode at log time
        details         caller payload: string (legacy) or dict
                        (structured) — passed through as-is

    No-ops if log_path is empty. Fails silent on every I/O error —
    audit logging MUST NOT block a Revit transaction or surface a
    dialog. A dropped write is preferable to a dropped project.

    Note on timezone: ts is always UTC. Cross-office deployments
    collapse to a single sortable timeline. Human readers can
    convert with any tool (the firm's IT Tuesday-morning-standup
    spreadsheet, Splunk, `jq`, Python, a watch).
    """
    try:
        config = load_config()
    except Exception:
        return
    log_path = config.get("log_path", "")
    if not log_path:
        return
    try:
        import datetime as _dt
        record = {
            "ts": _dt.datetime.utcnow().strftime(
                "%Y-%m-%dT%H:%M:%S.%f"
            ) + "Z",
            "event": event_type,
            "user": username,
            "host": _HOSTNAME,
            "revit_version": get_revit_version(),
            "aiblock_version": __version__,
            "session_id": _SESSION_ID,
            "mode": config.get("mode", ""),
            "details": details,
        }
        line = json.dumps(record) + "\n"
        log_dir = os.path.dirname(log_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        with open(log_path, "a") as f:
            f.write(line)
    except (IOError, OSError, ValueError, TypeError):
        # TypeError covers the case where a caller passes a non-JSON-
        # serializable object in details — still shouldn't crash.
        pass