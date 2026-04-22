# -*- coding: utf-8 -*-
# Author: Tay Othman
"""AIBlock extension startup.

pyRevit runs this file once per session (and again after every
Reload) inside Revit's ApplicationInitialized window. That is the
only place where FailureDefinition.CreateFailureDefinition is
legal, so registration of the rollback-failure definition and the
IUpdater happens here.

Fails fast and silent on Revit < 2027 — the Assistant only ships
on 2027+ and the updater targets that surface.
"""
from pyrevit import HOST_APP

if HOST_APP.version < 2027:
    import sys
    sys.exit()

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
