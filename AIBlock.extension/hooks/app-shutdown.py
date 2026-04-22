# -*- coding: utf-8 -*-
# Author: Tay Othman
"""AIBlock: clean shutdown hook.

Fires on Autodesk.Revit.ApplicationServices.ControlledApplication's
ApplicationClosing event. Mirrors startup.py — where startup.py
calls aiblock.updater.register(uiapp), this removes the IUpdater
registration, the Idling handler, and the FailuresProcessing
subscriber so Revit closes without a dangling AddIn-owned updater
or event subscription pointing at this session's assemblies.

Without this hook, pyRevit reload still cleaned the registration
(register() unregisters any stale instance before rebinding), but
a plain Revit close left the IUpdater listed in Revit's registry
until Revit's own teardown ran. The difference rarely matters for
users but shows up as noisy journal entries in long-lived sessions
and as leaked event handlers if an extension reload ever failed
mid-way.

Fails silent on Revit < 2027 and swallows any teardown exception —
shutdown must never surface a dialog to the user.
"""
from pyrevit import HOST_APP
if HOST_APP.version < 2027:
    import sys
    sys.exit()

try:
    from aiblock.updater import unregister as _unregister_guard
    _unregister_guard(HOST_APP.uiapp)
except Exception as _exc:
    try:
        from pyrevit import script
        script.get_logger().warning(
            "AIBlock updater unregister failed: {}".format(_exc)
        )
    except Exception:
        pass
