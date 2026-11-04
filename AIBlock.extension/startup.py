# -*- coding: utf-8 -*-
# Author: Tay Othman
"""AIBlock extension startup.

pyRevit runs this file once per session (and again after every
Reload) inside Revit's ApplicationInitialized window. That is the
only place where FailureDefinition.CreateFailureDefinition is
legal, so registration of the rollback-failure definition and the
IUpdater happens here.

No-ops on Revit < 2027 — the Assistant only ships on 2027+ and the
updater targets that surface. There is deliberately no sys.exit()
early-out: registration sits inside a positive version check so the
module always runs to the end and nothing surfaces on older hosts. Version compare is wrapped in int()
because HOST_APP.version forwards Application.VersionNumber, which
the Revit API returns as a string like "2026"; comparing a string
to the int 2027 silently misbehaves on Python 2 and TypeErrors on
Python 3.
"""
from pyrevit import HOST_APP


def _revit_is_2027_plus():
    """True only on Revit 2027+. Never raises."""
    try:
        return int(HOST_APP.version) >= 2027
    except (TypeError, ValueError):
        return False


# Positive conditional instead of sys.exit(): pyRevit can treat a
# SystemExit raised from startup.py as a failed load in some paths,
# which surfaces an error on older hosts. On < 2027 this block is
# simply skipped and the module runs to the end silently.
if _revit_is_2027_plus():
    try:
        from aiblock.updater import register as _register_guard
        _register_guard(HOST_APP.uiapp)
    except Exception as _exc:
        # Startup must never crash pyRevit. Log to pyRevit's output if
        # available; otherwise stay silent.
        try:
            from pyrevit import script
            script.get_logger().error(
                "AIBlock updater registration failed: {}".format(_exc)
            )
        except Exception:
            pass
