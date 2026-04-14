# -*- coding: utf-8 -*-
# Author: Tay Othman
"""Configure AIBlock settings.

Allows BIM Managers to:
  - View/edit the authorized user list
  - Change the override password
  - Set the shared log file path
  - Toggle Public MCP Server blocking
"""
__title__ = "Guard\nSettings"
__author__ = "Tay Othman"
__doc__ = """Configure the AI Assistant guard.

Requires BIM Manager password.
- Manage authorized users
- Change override password
- Set network log path
"""

import os
from pyrevit import forms
from pyrevit import script

from aiblock import (
    load_config,
    save_config,
    check_password,
    set_password,
)

output = script.get_output()
username = os.environ.get("USERNAME", "unknown")


def main():
    pwd = forms.ask_for_string(
        prompt="Enter current BIM Manager password:",
        title="AIBlock — Settings",
        password=True,
    )
    if not pwd or not check_password(pwd):
        forms.alert("Incorrect password.", title="AIBlock")
        return

    config = load_config()

    action = forms.CommandSwitchWindow.show(
        ["Manage Authorized Users",
         "Change Password",
         "Set Log Path",
         "View Current Config"],
        message="What would you like to configure?",
    )

    if not action:
        return

    if action == "Manage Authorized Users":
        _manage_users(config)
    elif action == "Change Password":
        _change_password()
    elif action == "Set Log Path":
        _set_log_path(config)
    elif action == "View Current Config":
        _view_config(config)


def _manage_users(config):
    users = config.get("authorized_users", [])

    action = forms.CommandSwitchWindow.show(
        ["Add User", "Remove User", "View List"],
        message="Authorized users: {}".format(
            ", ".join(users) if users else "(none)"
        ),
    )

    if action == "Add User":
        new_user = forms.ask_for_string(
            prompt="Enter Windows username to authorize\n"
                   "(domain prefix not needed):",
            title="Add Authorized User",
        )
        if new_user:
            new_user = new_user.strip()
            if new_user.lower() not in [u.lower() for u in users]:
                users.append(new_user)
                config["authorized_users"] = users
                save_config(config)
                forms.alert(
                    "'{}' added to authorized users.".format(new_user),
                    title="AIBlock",
                )
            else:
                forms.alert(
                    "'{}' is already authorized.".format(new_user),
                    title="AIBlock",
                )

    elif action == "Remove User":
        if not users:
            forms.alert("No authorized users to remove.",
                        title="AIBlock")
            return
        to_remove = forms.SelectFromList.show(
            users,
            title="Remove Authorized User",
            button_name="Remove",
            multiselect=True,
        )
        if to_remove:
            for u in to_remove:
                users.remove(u)
            config["authorized_users"] = users
            save_config(config)
            forms.alert(
                "Removed: {}".format(", ".join(to_remove)),
                title="AIBlock",
            )

    elif action == "View List":
        if users:
            forms.alert(
                "Authorized users:\n\n{}".format("\n".join(users)),
                title="AIBlock",
            )
        else:
            forms.alert(
                "No authorized users configured.\n"
                "All users must enter the password.",
                title="AIBlock",
            )


def _change_password():
    new_pwd = forms.ask_for_string(
        prompt="Enter new override password:",
        title="Change Password",
        password=True,
    )
    if not new_pwd:
        return

    confirm = forms.ask_for_string(
        prompt="Confirm new password:",
        title="Change Password",
        password=True,
    )
    if new_pwd != confirm:
        forms.alert("Passwords do not match.", title="AIBlock")
        return

    set_password(new_pwd)
    forms.alert("Password updated.", title="AIBlock")


def _set_log_path(config):
    current = config.get("log_path", "")
    new_path = forms.ask_for_string(
        prompt="Enter network log file path\n"
               "(leave blank to disable logging):\n\n"
               "Example: X:\\BIM\\Logs\\ai_guard_log.csv",
        title="Set Log Path",
        default=current,
    )
    if new_path is not None:
        config["log_path"] = new_path.strip()
        save_config(config)
        if config["log_path"]:
            forms.alert(
                "Log path set to:\n{}".format(config["log_path"]),
                title="AIBlock",
            )
        else:
            forms.alert("Logging disabled.", title="AIBlock")


def _view_config(config):
    output.set_title("AIBlock — Configuration")
    output.set_width(600)
    output.set_height(400)

    guard_state = "ENABLED" if config.get("guard_enabled") else "DISABLED"
    users = config.get("authorized_users", [])
    log_path = config.get("log_path", "") or "(disabled)"
    block_mcp = "Yes" if config.get("block_public_mcp") else "No"

    output.print_md("# AIBlock — Current Configuration")
    output.print_md("---")
    output.print_md("**Guard State:** {}".format(guard_state))
    output.print_md("**Authorized Users:** {}".format(
        ", ".join(users) if users else "(none)"
    ))
    output.print_md("**Log Path:** {}".format(log_path))
    output.print_md("**Block Public MCP:** {}".format(block_mcp))
    output.print_md("---")
    output.print_md("**Assistant AddInId:** "
                     "`f0da0f43-cd76-4945-968b-4c4e0a769298`")
    output.print_md("**Blocked Command:** "
                     "`ID_TOGGLE_AUTODESK_ASSISTANT`")


if __name__ == "__main__":
    main()
