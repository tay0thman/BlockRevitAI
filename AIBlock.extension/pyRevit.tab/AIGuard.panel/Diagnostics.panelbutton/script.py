# -*- coding: utf-8 -*-
# Author: Tay Othman
"""AIBlock diagnostics.

Reports the runtime state of the AIBlock IUpdater and FailureDefinition
without requiring the user to read Revit's journal. Run this after a
pyRevit reload to confirm the guard is actually installed.

What it checks:
  1. Is AIBlockUpdater registered with Revit's UpdaterRegistry?
  2. Under which AddInId was it registered (should be pyRevit's)?
  3. Does the AIBlock FailureDefinition exist?
  4. Current arm / one-pass / pending-decision state.

Previously the updater registration silently failed because the
hardcoded AIBLOCK_ADDIN_GUID did not match the active pyRevit AddIn.
Revit logged DBG_WARN and dropped the registration, so AI transactions
ran unblocked. This button makes that failure visible at a glance.
"""
__title__ = "Diagnostics"
__doc__ = "Verify that the AIBlock IUpdater is live in this Revit session."
__author__ = "Tay Othman"
__context__ = "zero-doc"

from pyrevit import HOST_APP, script

from Autodesk.Revit.DB import (
    AddInId,
    FailureDefinitionId,
    UpdaterId,
    UpdaterRegistry,
)

from aiblock import (
    __version__ as aiblock_version,
    MODE_BLOCK_ALL,
    MODE_BLOCK_WRITES,
    MODE_USER_CONTROLLED,
    MODE_LABELS,
    MODE_DESCRIPTIONS,
    get_config_source,
    get_hostname,
    get_mode,
    get_session_id,
    is_guard_enabled,
    is_network_managed,
    load_config,
    should_block_ai_panel,
    should_block_ai_writes,
)
from aiblock.state import has_one_pass, has_pending
from aiblock.updater import (
    AIBLOCK_UPDATER_GUID,
    AIBLOCK_FAILURE_GUID,
    _resolve_active_addin_id,
)

output = script.get_output()
output.set_title("AIBlock Diagnostics")

# --- Add-in context -------------------------------------------------
uiapp = HOST_APP.uiapp
addin_id = _resolve_active_addin_id(uiapp)
try:
    addin_guid_str = str(addin_id.GetGUID())
except Exception:
    addin_guid_str = "<unresolved>"

# --- Updater registration check ------------------------------------
updater_id = UpdaterId(addin_id, AIBLOCK_UPDATER_GUID)
try:
    is_registered = UpdaterRegistry.IsUpdaterRegistered(updater_id)
except Exception as exc:
    is_registered = None
    registration_error = str(exc)
else:
    registration_error = None

# --- Config snapshot -----------------------------------------------
cfg = load_config()
mode = get_mode()
mode_label = MODE_LABELS.get(mode, mode)
mode_desc = MODE_DESCRIPTIONS.get(mode, "")

# Resolve what the user-level toggle effectively means under the
# current mode. guard_enabled is only honoured in MODE_USER_CONTROLLED;
# otherwise it's a dead knob that the BIM-enforced policy overrides.
guard_raw = bool(cfg.get("guard_enabled", True))
if mode == MODE_USER_CONTROLLED:
    guard_display = "{}  (active — per-session toggle)".format(
        "GUARDED" if guard_raw else "OPEN",
    )
    guard_ok = guard_raw
else:
    guard_display = "{}  (ignored — mode enforces policy)".format(
        "GUARDED" if guard_raw else "OPEN",
    )
    guard_ok = None

# Effective answers to the two predicates the enforcement layer uses.
# These are what the hook and the IUpdater actually consult, so surface
# them explicitly — it makes Mode 1 / 2 / 3 behaviour legible without
# tracing the code.
panel_blocked = should_block_ai_panel()
writes_blocked = should_block_ai_writes()

# --- Render ---------------------------------------------------------
def row(label, value, ok=None):
    if ok is True:
        marker = "[OK]     "
    elif ok is False:
        marker = "[MISS]   "
    else:
        marker = "         "
    output.print_md("`{0}{1:<28} {2}`".format(marker, label, value))

output.print_md("## AIBlock runtime status")
output.print_md("")

row("AIBlock version",        aiblock_version)
row("Host Revit version",     HOST_APP.version)
row("Hostname",               get_hostname())
# Session id is stamped on every audit log line and every trace log
# line this Revit process produces. Ask users to quote it in support
# threads — BIM Managers can grep the shared audit log with it.
row("Session id",             get_session_id())
row("Active AddIn GUID",      addin_guid_str,
    ok=(addin_guid_str.lower() == "b39107c3-a1d7-47f4-a5a1-532ddf6edb5d"))
row("Updater GUID",           str(AIBLOCK_UPDATER_GUID))

if is_registered is True:
    row("IUpdater registered", "YES", ok=True)
elif is_registered is False:
    row("IUpdater registered", "NO  <-- the guard is inert", ok=False)
else:
    row("IUpdater registered", "ERROR: {}".format(registration_error), ok=False)

row("Failure definition id",  str(AIBLOCK_FAILURE_GUID))

output.print_md("")
output.print_md("## BIM policy")
output.print_md("")
row("Policy mode",            "{} ({})".format(mode_label, mode), ok=True)
row("Panel-open blocked",     "YES" if panel_blocked else "NO",
    ok=(True if panel_blocked else None))
row("AI writes blocked",      "YES" if writes_blocked else "NO",
    ok=(True if writes_blocked else None))
row("User toggle (guard)",    guard_display, ok=guard_ok)
row("Config source",          get_config_source(),
    ok=(True if is_network_managed() else None))
row("Network-managed",        "YES" if is_network_managed() else "NO")

output.print_md("")
output.print_md("> {}".format(mode_desc))

output.print_md("")
output.print_md("## Runtime state")
output.print_md("")
row("One-pass granted",       has_one_pass())
row("Pending decisions",      has_pending())

output.print_md("")
if is_registered is True:
    if mode == MODE_BLOCK_ALL:
        output.print_md(
            "> Mode **Block all AI**: the command-before-exec hook "
            "cancels any click on the Autodesk Assistant toggle. "
            "Users cannot open the panel. The IUpdater still runs "
            "as a defence-in-depth safety net if an AI call reaches "
            "a transaction by another path."
        )
    elif mode == MODE_BLOCK_WRITES:
        output.print_md(
            "> Mode **Block AI writes**: the Autodesk Assistant panel "
            "opens normally. Queries and reports work. Any AI-originated "
            "transaction that mutates the model is routed through "
            "`AIBlockUpdater.Execute` and rolled back atomically via "
            "`PostFailure`. Manual edits are unaffected. There is no "
            "per-user override — only the BIM Manager can change the mode."
        )
    else:  # MODE_USER_CONTROLLED
        output.print_md(
            "> Mode **User-controlled**: the AI Guard button is the "
            "password-gated switch. When `User toggle (guard)` is ON, "
            "AI-originated transactions are rolled back. When OFF, "
            "the AI Assistant runs without interception. Manual edits "
            "are always unaffected."
        )
else:
    output.print_md(
        "> The updater is NOT live in this session. AI transactions "
        "will commit unblocked regardless of the policy mode. Check "
        "the Revit journal for `DBG_WARN: Trying to modify an updater "
        "that doesn't belong to the currently active AddIn` — that is "
        "the tell for an AddInId mismatch during registration."
    )
