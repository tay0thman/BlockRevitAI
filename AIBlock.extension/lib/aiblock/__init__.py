# -*- coding: utf-8 -*-
# Author: Tay Othman
"""AIBlock configuration and shared utilities.

Centralized config for the AI Assistant guard system.
Stores password hash, authorized user list, and guard state.
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
# Config file location
# -------------------------------------------------------------------
_CONFIG_DIR = os.path.join(
    os.environ.get("APPDATA", ""),
    "AIBlock"
)
_CONFIG_PATH = os.path.join(_CONFIG_DIR, "config.json")

# -------------------------------------------------------------------
# Default config
# -------------------------------------------------------------------
_DEFAULT_CONFIG = {
    # SHA-256 hash of the override password
    # Default: "AIBlock2026" → update via Settings button
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


def _ensure_config_dir():
    """Create config directory if it doesn't exist."""
    if not os.path.exists(_CONFIG_DIR):
        os.makedirs(_CONFIG_DIR)


def load_config():
    """Load config from disk, or return defaults if missing."""
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r") as f:
                stored = json.load(f)
            # Merge with defaults so new keys are always present
            merged = dict(_DEFAULT_CONFIG)
            merged.update(stored)
            return merged
        except (json.JSONDecodeError, IOError):
            pass
    return dict(_DEFAULT_CONFIG)


def save_config(config):
    """Persist config to disk."""
    _ensure_config_dir()
    with open(_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def check_password(plain_text):
    """Return True if the plain-text password matches the stored hash."""
    config = load_config()
    candidate = hashlib.sha256(plain_text.encode("utf-8")).hexdigest()
    return candidate == config["password_hash"]


def set_password(new_plain_text):
    """Update the stored password hash."""
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
