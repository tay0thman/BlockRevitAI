# -*- coding: utf-8 -*-
# Author: Tay Othman
"""Toggle the AI Assistant guard on or off.

Shift+Click:
Opens the guard settings panel.
"""
__title__ = "AI Guard"
__author__ = "Tay Othman"
__doc__ = """Toggle the Autodesk Assistant guard.

When ON:  Users must enter a password or be on the
          authorized list to open the Assistant panel.
When OFF: The Assistant is accessible to everyone.

Shift+Click to open settings.
"""

import os
from pyrevit import EXEC_PARAMS
from pyrevit import forms
from pyrevit import script

from aiblock import (
    load_config,
    save_config,
    check_password,
    is_user_authorized,
    is_guard_enabled,
)

logger = script.get_logger()
username = os.environ.get("USERNAME", "unknown")


def __selfinit__(script_cmp, ui_button_cmp, __rvt__):
    """Update button title based on guard state."""
    try:
        on = is_guard_enabled()
        if on:
            ui_button_cmp.set_title("AI Guard\nON")
        else:
            ui_button_cmp.set_title("AI Guard\nOFF")
    except Exception:
        pass


def main():
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
            return

    config["guard_enabled"] = not current_state
    save_config(config)

    new_state = "ENABLED" if config["guard_enabled"] else "DISABLED"
    forms.alert(
        "AI Assistant guard is now {}.\n\n"
        "{}".format(
            new_state,
            "Users will be prompted for a password to open the Assistant."
            if config["guard_enabled"]
            else "The Assistant is now accessible to all users."
        ),
        title="AIBlock",
    )


if __name__ == "__main__":
    main()
