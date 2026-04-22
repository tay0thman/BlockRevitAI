# -*- coding: utf-8 -*-
# Author: Tay Othman
"""Toggle the per-session AI Guard, when the mode permits it.

In MODE_USER_CONTROLLED this button is the password-gated switch that
flips `guard_enabled` between ON (writes blocked) and OFF (pass-through).

In MODE_BLOCK_ALL and MODE_BLOCK_WRITES this button is locked — the
policy is enforced by the BIM Management Team and individual users
cannot override it here. Clicking shows an informational dialog and
directs the user to Settings (password-gated) or their BIM Manager.

Shift+Click opens Guard Settings.
"""
__title__ = "AI Guard"
__author__ = "Tay Othman"
__doc__ = """Toggle the Autodesk Assistant guard (Mode 3 only).

When ON:  AI-originated model changes are rolled back silently.
When OFF: AI runs without protection.

Locked read-only when the BIM Management Team has set the project
to 'Block all AI' or 'Block AI writes'.

Shift+Click to open settings.
"""

import os
from pyrevit import EXEC_PARAMS
from pyrevit import forms
from pyrevit import script

from aiblock import (
    MODE_BLOCK_ALL,
    MODE_BLOCK_WRITES,
    MODE_USER_CONTROLLED,
    MODE_LABELS,
    check_password,
    get_mode,
    is_bim_locked,
    is_guard_enabled,
    is_user_authorized,
    load_config,
    log_event,
    save_config,
)

logger = script.get_logger()
username = os.environ.get("USERNAME", "unknown")


def __selfinit__(script_cmp, ui_button_cmp, __rvt__):
    """Update button caption to reflect the effective policy.

    The caption is the fastest way for a user to see what's actually
    enforced right now without running Diagnostics. Four distinct
    labels, one per state, so nothing is ambiguous at a glance:

      BLOCKED    — Mode 1: no AI at all, hook cancels panel open
      READ-ONLY  — Mode 2: queries allowed, AI writes rolled back
      GUARDED    — Mode 3, guard ON: AI writes rolled back
      OPEN       — Mode 3, guard OFF: AI runs with no protection

    The previous ON/OFF pair was ambiguous — "AI Guard OFF" could be
    read as "AI is off" or "guard is off" depending on the reader.
    GUARDED/OPEN describe the AI state directly and scan cleanly next
    to the BIM-enforced labels.
    """
    try:
        mode = get_mode()
        if mode == MODE_BLOCK_ALL:
            ui_button_cmp.set_title("AI Guard\nBLOCKED")
        elif mode == MODE_BLOCK_WRITES:
            ui_button_cmp.set_title("AI Guard\nREAD-ONLY")
        elif mode == MODE_USER_CONTROLLED:
            on = is_guard_enabled()
            ui_button_cmp.set_title(
                "AI Guard\n{}".format("GUARDED" if on else "OPEN")
            )
        else:
            ui_button_cmp.set_title("AI Guard\n?")
    except Exception:
        # Caption update must never break pyRevit load; swallow any
        # config read failures.
        pass


def _show_locked_dialog():
    """Explain why the toggle is read-only in BIM-enforced modes."""
    mode = get_mode()
    forms.alert(
        "AI Guard is under BIM Management Team control.\n\n"
        "Current project mode: {label}\n\n"
        "This mode cannot be toggled from the AI Guard button. To "
        "change the project's policy, open Guard Settings and enter "
        "the BIM Manager password, or contact your BIM Manager.".format(
            label=MODE_LABELS.get(mode, mode),
        ),
        title="AIBlock — Locked",
        warn_icon=True,
    )
    log_event("TOGGLE_BLOCKED_BY_MODE", username, "mode={}".format(mode))


def main():
    if is_bim_locked():
        _show_locked_dialog()
        return

    # MODE_USER_CONTROLLED path — password-gated toggle of guard_enabled.
    config = load_config()
    current_state = config.get("guard_enabled", True)

    if not is_user_authorized(username):
        pwd = forms.ask_for_string(
            prompt="BIM Manager password required to change guard state:",
            title="AIBlock",
            password=True,
        )
        if not pwd or not check_password(pwd):
            forms.alert(
                "Incorrect password. Guard state unchanged.",
                title="AIBlock",
            )
            log_event("TOGGLE_DENIED_BAD_PWD", username, "")
            return

    config["guard_enabled"] = not current_state
    save_config(config)

    # Match the vocabulary shown on the ribbon button (GUARDED / OPEN)
    # so the confirmation reads consistently with what the user just
    # saw before clicking.
    new_state = "GUARDED" if config["guard_enabled"] else "OPEN"
    log_event(
        "TOGGLE_CHANGED",
        username,
        "guard_enabled={}".format(config["guard_enabled"]),
    )
    forms.alert(
        "AI Guard is now {}.\n\n{}".format(
            new_state,
            "AI-originated model changes will be rolled back "
            "silently."
            if config["guard_enabled"]
            else "AI transactions will pass through without "
            "interception."
        ),
        title="AIBlock",
    )


if __name__ == "__main__":
    main()
