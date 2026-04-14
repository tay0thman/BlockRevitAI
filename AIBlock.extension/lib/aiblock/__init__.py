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

# -------------------------------------------------------------------
# Assistant identity (extracted from Revit 2027 journal analysis)
# -------------------------------------------------------------------
ASSISTANT_ADDIN_ID = "f0da0f43-cd76-4945-968b-4c4e0a769298"
ASSISTANT_PANE_GUID = "3e852507-4f81-4234-b0d8-15c61ca8a261"
ASSISTANT_COMMAND_ID = "ID_TOGGLE_AUTODESK_ASSISTANT"

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
_DEFAULT_CONFIG = {
    # SHA-256 hash of the override password
    # Default: "AIBlock2026" → update via Settings button or network config
    "password_hash": hashlib.sha256(
        "AIBlock2026".encode("utf-8")
    ).hexdigest(),

    # Windows usernames that bypass the guard entirely
    # (domain prefix stripped — just the short username)
    "authorized_users": [],

    # Whether the guard is active
    "guard_enabled": True,

    # Log override attempts to a shared network path
    "log_path": "",

    # Also block the Public MCP Server add-on if installed
    "block_public_mcp": True,
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
    except (IOError, OSError, ValueError, json.JSONDecodeError):
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
    """Return True if the guard is currently active."""
    config = load_config()
    return config.get("guard_enabled", True)


def log_event(event_type, username, details=""):
    """Append a line to the shared log file if configured."""
    config = load_config()
    log_path = config.get("log_path", "")
    if not log_path:
        return
    try:
        import datetime
        line = "{},{},{},{}\n".format(
            datetime.datetime.now().isoformat(),
            username,
            event_type,
            details
        )
        log_dir = os.path.dirname(log_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        with open(log_path, "a") as f:
            f.write(line)
    except (IOError, OSError):
        pass  # fail silently — logging should never block Revit