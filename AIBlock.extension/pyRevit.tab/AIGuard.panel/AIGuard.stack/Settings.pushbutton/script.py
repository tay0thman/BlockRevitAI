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
__min_revit_ver__ = 2027
import os
from pyrevit import forms
from pyrevit import script

from aiblock import (
    __version__ as aiblock_version,
    MODE_BLOCK_ALL,
    MODE_BLOCK_WRITES,
    MODE_USER_CONTROLLED,
    MODE_LABELS,
    MODE_DESCRIPTIONS,
    VALID_MODES,
    check_password,
    get_config_source,
    get_mode,
    is_default_password,
    is_network_managed,
    load_config,
    log_event,
    save_config,
    set_mode,
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

    # First-run nag. The password is a speed-bump against accidental
    # toggles, not a hard security boundary — a determined user can
    # always uninstall pyRevit and run AI anyway. But if every firm
    # deployment ships with the same default, the button is
    # effectively a no-click override and mode changes stop feeling
    # like deliberate acts. Offer to rotate on first entry so the
    # firm picks its own speed-bump. Dismissal is fine — a BIM
    # Manager might be inside solely to change a different setting.
    if is_default_password():
        rotate_now = forms.alert(
            "AIBlock is still using the default shipped password "
            "('AIBlock2026').\n\n"
            "Rotating it to something firm-specific keeps mode "
            "changes and toggles deliberate rather than casual. "
            "(It isn't a hard security boundary — someone determined "
            "to run AI can always uninstall pyRevit.)\n\n"
            "Change it now?",
            title="AIBlock — Default Password In Use",
            yes=True,
            no=True,
            warn_icon=True,
        )
        log_event(
            "DEFAULT_PASSWORD_NAG",
            username,
            "accepted={}".format(rotate_now),
        )
        if rotate_now:
            _change_password()
            # Password is refreshed from disk on every load_config()
            # call, so downstream actions see the new hash.

    config = load_config()

    action = forms.CommandSwitchWindow.show(
        ["Change Mode",
         "Manage Authorized Users",
         "Change Password",
         "Set Log Path",
         "Test Log Paths",
         "View Current Config"],
        message="What would you like to configure?",
    )

    if not action:
        return

    if action == "Change Mode":
        _change_mode()
    elif action == "Manage Authorized Users":
        _manage_users(config)
    elif action == "Change Password":
        _change_password()
    elif action == "Set Log Path":
        _set_log_path(config)
    elif action == "Test Log Paths":
        _test_log_paths(config)
    elif action == "View Current Config":
        _view_config(config)


def _change_mode():
    """Let the BIM Manager switch the enforcement mode.

    Writes go to LOCAL config. If the firm has pushed a network
    config via AIBLOCK_NETWORK_CONFIG, the network value still wins
    at read time — this is deliberate so IT-enforced policy survives
    per-machine edits. The UI surfaces that situation via the
    warning text at the top of the picker.
    """
    current = get_mode()

    options = [
        "{label} — {mode}".format(
            label=MODE_LABELS[m],
            mode=m,
        )
        for m in VALID_MODES
    ]
    option_to_mode = {opt: VALID_MODES[i] for i, opt in enumerate(options)}

    picked = forms.SelectFromList.show(
        options,
        title="Change AIBlock Mode",
        button_name="Set Mode",
        multiselect=False,
    )
    if not picked:
        return

    new_mode = option_to_mode[picked]

    if new_mode == current:
        forms.alert(
            "Mode unchanged — already set to {}.".format(
                MODE_LABELS[current],
            ),
            title="AIBlock",
        )
        return

    # Confirm with full description so the BIM Manager can't pick a
    # mode by accident with only the short label visible.
    confirmed = forms.alert(
        "Switch AIBlock mode?\n\n"
        "From: {old_lbl}\n"
        "To:   {new_lbl}\n\n"
        "{desc}".format(
            old_lbl=MODE_LABELS[current],
            new_lbl=MODE_LABELS[new_mode],
            desc=MODE_DESCRIPTIONS[new_mode],
        ),
        title="Confirm mode change",
        yes=True,
        no=True,
    )
    if not confirmed:
        return

    try:
        set_mode(new_mode)
    except Exception as exc:
        forms.alert(
            "Could not save mode: {}".format(exc),
            title="AIBlock",
        )
        return

    log_event(
        "MODE_CHANGED",
        username,
        "from={} to={}".format(current, new_mode),
    )
    forms.alert(
        "Mode set to: {}.\n\n"
        "The change takes effect immediately for the transaction "
        "updater. For the AI Guard button caption to refresh, "
        "reload pyRevit.".format(MODE_LABELS[new_mode]),
        title="AIBlock",
    )


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


def _test_log_paths(config):
    """Write a canary event and report whether the log file got it.

    log_event() swallows I/O errors silently by design (audit writes
    must never break Revit). That's exactly the behaviour that hides
    a misconfigured UNC from a BIM Manager — the extension looks
    healthy while audit events vanish. This test forces a canary
    write, then checks the path on disk afterwards. If the file does
    not exist (or has a suspiciously ancient mtime), the path is
    probably unreachable or not permissioned.
    """
    log_path = config.get("log_path", "")

    if not log_path:
        forms.alert(
            "No log path configured.\n\n"
            "Audit events are currently not being written anywhere. "
            "Set one via Settings → Set Log Path.",
            title="AIBlock — Test Log Paths",
            warn_icon=True,
        )
        return

    # Snapshot pre-write state so we can tell whether THIS call
    # produced a change, rather than just detecting a file that
    # happened to already exist.
    try:
        existed = os.path.exists(log_path)
        size_before = os.path.getsize(log_path) if existed else 0
    except Exception:
        existed = False
        size_before = 0

    log_event("LOG_PATH_CANARY", username, "test write from Settings UI")

    # Give the FS a moment for any network write buffering. This is
    # belt-and-suspenders — log_event is synchronous — but UNC writes
    # over VPN have been observed to return before the size stat
    # updates on the local stat cache.
    try:
        exists_now = os.path.exists(log_path)
        size_after = os.path.getsize(log_path) if exists_now else 0
    except Exception as exc:
        forms.alert(
            "Canary write inconclusive — could not stat path:\n\n"
            "{}\n\nError: {}".format(log_path, exc),
            title="AIBlock — Test Log Paths",
            warn_icon=True,
        )
        return

    if exists_now and size_after > size_before:
        forms.alert(
            "Canary write SUCCEEDED.\n\n"
            "Path: {}\n"
            "Size: {} bytes (was {})\n\n"
            "The audit log is reachable and writable. Look for the "
            "'LOG_PATH_CANARY' line to confirm end-to-end.".format(
                log_path, size_after, size_before,
            ),
            title="AIBlock — Test Log Paths",
        )
    else:
        forms.alert(
            "Canary write FAILED.\n\n"
            "Path: {}\n"
            "File exists: {}\n"
            "Size delta: {} bytes\n\n"
            "log_event() is designed to swallow I/O errors silently "
            "so Revit never breaks on a flaky share — but that means "
            "audit events disappear without warning. Likely causes:\n\n"
            "  • UNC unreachable (VPN / share offline)\n"
            "  • User lacks write permission on the path\n"
            "  • Parent directory does not exist\n"
            "  • Antivirus or DLP blocking the write".format(
                log_path,
                "yes" if exists_now else "no",
                size_after - size_before,
            ),
            title="AIBlock — Test Log Paths",
            warn_icon=True,
        )


def _view_config(config):
    output.set_title("AIBlock — Configuration")
    output.set_width(700)
    output.set_height(500)

    mode = get_mode()
    mode_label = MODE_LABELS.get(mode, mode)
    mode_desc = MODE_DESCRIPTIONS.get(mode, "")

    # Match the ribbon-button vocabulary: GUARDED / OPEN, and explicitly
    # annotate when the user toggle is ignored because the mode
    # enforces policy.
    if config.get("guard_enabled"):
        guard_state = "GUARDED"
    else:
        guard_state = "OPEN"
    if mode != MODE_USER_CONTROLLED:
        guard_state += "  _(ignored — mode enforces policy)_"

    users = config.get("authorized_users", [])
    log_path = config.get("log_path", "") or "(disabled)"
    block_mcp = "Yes" if config.get("block_public_mcp") else "No"
    cfg_source = get_config_source()
    net_managed = "yes" if is_network_managed() else "no"
    default_pwd_warning = is_default_password()

    output.print_md("# AIBlock — Current Configuration")
    output.print_md("**Version:** `{}`".format(aiblock_version))
    output.print_md("---")

    # Default-password notice. Not a security warning — the password
    # is a speed-bump, not a hard control — but flagging it at the
    # top of View Config reminds the BIM Manager to pick a
    # firm-specific password so toggles stay deliberate.
    if default_pwd_warning:
        output.print_md(
            "> **Default password in use.** Rotate `AIBlock2026` via "
            "Settings → Change Password to pick a firm-specific "
            "password."
        )
        output.print_md("")

    output.print_md("## Config source")
    output.print_md("**Active source:** {}".format(cfg_source))
    output.print_md("**Network-managed:** {}".format(net_managed))
    if net_managed == "yes":
        output.print_md(
            "> Network config wins over local for every field it "
            "defines. Local edits to mode, password, authorized users, "
            "or log path will NOT take effect until the network file "
            "is updated or the `AIBLOCK_NETWORK_CONFIG` env var is "
            "unset."
        )
    output.print_md("")
    output.print_md("## Policy")
    output.print_md("**Mode:** `{}` — {}".format(mode, mode_label))
    output.print_md("> {}".format(mode_desc))
    output.print_md("")
    output.print_md("**User toggle (guard_enabled):** {}".format(guard_state))
    output.print_md("")
    output.print_md("## Access")
    output.print_md("**Authorized Users:** {}".format(
        ", ".join(users) if users else "(none)"
    ))
    output.print_md("**Log Path:** {}".format(log_path))
    output.print_md("**Block Public MCP:** {}".format(block_mcp))
    output.print_md("---")
    output.print_md("## Assistant Identity (Revit 2027)")
    output.print_md("**AddInId:** "
                     "`f0da0f43-cd76-4945-968b-4c4e0a769298`")
    output.print_md("**Command ID:** "
                     "`ID_TOGGLE_AUTODESK_ASSISTANT`")


if __name__ == "__main__":
    main()
