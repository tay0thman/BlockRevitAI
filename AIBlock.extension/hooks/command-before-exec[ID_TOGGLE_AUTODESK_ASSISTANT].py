# -*- coding: utf-8 -*-
# Author: Tay Othman
"""AIBlock: gate the Autodesk Assistant panel per policy mode.

This hook fires only when a user clicks the Autodesk Assistant toggle
button (ID_TOGGLE_AUTODESK_ASSISTANT). Behaviour depends on the
enforcement mode set by the BIM Management Team.

  MODE_BLOCK_ALL
    Panel never opens. No password override. Show an explanatory
    alert and cancel the command.

  MODE_BLOCK_WRITES
    Panel opens unconditionally. Users can query the model, generate
    reports, and read data. The IUpdater (aiblock.updater) will roll
    back any write transaction the Assistant attempts, silently.

  MODE_USER_CONTROLLED
    Legacy behaviour. If the per-session AI Guard toggle is off, the
    panel opens freely. Otherwise the user must be on the authorized
    list or enter the override password.
"""
from pyrevit import HOST_APP
if HOST_APP.version < 2027:
    import sys
    sys.exit()

import os
from pyrevit import EXEC_PARAMS
from pyrevit import forms

from aiblock import (
    MODE_BLOCK_ALL,
    MODE_BLOCK_WRITES,
    MODE_USER_CONTROLLED,
    check_password,
    get_mode,
    is_guard_enabled,
    is_user_authorized,
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
# Mode dispatch
# -------------------------------------------------------------------
mode = get_mode()

if mode == MODE_BLOCK_ALL:
    # Hard stop. The BIM team has locked AI off; there is no
    # per-user escape hatch. Message is intentionally explicit about
    # contacting the BIM Manager so users know where to escalate.
    _block("mode=block_all")
    forms.alert(
        "The Autodesk Assistant is disabled on this project.\n\n"
        "Your BIM Management Team has restricted all AI features.\n"
        "There is no per-user override for this mode.\n\n"
        "If you need AI access, contact your BIM Manager to request "
        "a mode change.",
        title="AIBlock — AI Disabled",
        warn_icon=True,
    )

elif mode == MODE_BLOCK_WRITES:
    # Panel is allowed to open. The transaction-layer updater handles
    # the write-blocking; there is nothing for this hook to enforce.
    # A one-time info dialog would be annoying on every click, so just
    # log the open event — the user can see the mode in the AI Guard
    # button caption and the Diagnostics output.
    _allow("mode=block_writes")

elif mode == MODE_USER_CONTROLLED:
    # Legacy behaviour preserved verbatim for this mode.
    if not is_guard_enabled():
        _allow("mode=user_controlled guard=off")

    elif is_user_authorized(username):
        _allow("mode=user_controlled authorized_user")

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
            _allow("mode=user_controlled password_override")
        else:
            _block("mode=user_controlled denied_or_cancelled")
            forms.alert(
                "Access denied. The Autodesk Assistant has been blocked.\n\n"
                "Contact your BIM Manager if you need access.",
                title="AIBlock",
                exitscript=True,
            )

else:
    # Should be unreachable — get_mode() normalises unknown values to
    # MODE_BLOCK_WRITES — but if a future mode is added and this
    # dispatcher isn't updated, fail closed rather than open.
    _block("mode=unknown:{}".format(mode))
    forms.alert(
        "AIBlock is misconfigured (unknown mode: {}).\n\n"
        "Access blocked as a safety fallback. Contact your BIM Manager.".format(
            mode,
        ),
        title="AIBlock",
        warn_icon=True,
    )
