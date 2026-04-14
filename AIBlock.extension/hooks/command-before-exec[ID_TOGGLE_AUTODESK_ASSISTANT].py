# -*- coding: utf-8 -*-
# Author: Tay Othman
"""AIBlock: Block Autodesk Assistant unless authorized.

This hook fires ONLY when a user clicks the Autodesk Assistant
toggle button (ID_TOGGLE_AUTODESK_ASSISTANT). Zero performance overhead.

Behavior:
  - If the guard is disabled → allow
  - If the current user is on the authorized list → allow + log
  - Otherwise → prompt for password
    - Correct password → allow + log
    - Wrong password or cancel → block (args.Cancel = True)
"""
import os
from pyrevit import EXEC_PARAMS
from pyrevit import forms

from aiblock import (
    is_guard_enabled,
    is_user_authorized,
    check_password,
    log_event,
)

args = EXEC_PARAMS.event_args
username = os.environ.get("USERNAME", "unknown")


def _allow(reason):
    log_event("ASSISTANT_ALLOWED", username, reason)


def _block(reason):
    args.Cancel = True
    log_event("ASSISTANT_BLOCKED", username, reason)


# -------------------------------------------------------------------
# Guard logic
# -------------------------------------------------------------------

if not is_guard_enabled():
    _allow("guard_disabled")

elif is_user_authorized(username):
    _allow("authorized_user")

else:
    forms.alert(
        "The Autodesk Assistant is restricted on this project.\n\n"
        "AI-driven model changes can modify parameters, create\n"
        "elements, and alter sheets without standard QA review.\n\n"
        "If you need to use the Assistant, enter the override\n"
        "password below. All access is logged.",
        title="AIBlock",
        warn_icon=True,
    )

    pwd = forms.ask_for_string(
        prompt="Enter override password:",
        title="AIBlock — Authorization",
        password=True,
    )

    if pwd and check_password(pwd):
        _allow("password_override")
    else:
        _block("denied_or_cancelled")
        forms.alert(
            "Access denied. The Autodesk Assistant has been blocked.\n\n"
            "Contact your BIM Manager if you need access.",
            title="AIBlock",
            exitscript=True,
        )
