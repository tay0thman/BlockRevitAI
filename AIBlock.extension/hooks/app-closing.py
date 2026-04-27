# -*- coding: utf-8 -*-
# Author: Tay Othman
"""AIBlock: clean shutdown hook.

Filename matters: pyRevit maps the hook script's stem to a Revit
event name. `app-closing` corresponds to UIApplication's
ApplicationClosing event — see pyRevit's hook event registry. Any
other stem is rejected by the C# RegisterHook call with a wrapped
TargetInvocationException, which surfaces as
    "Failed registering hook script ... | Exception has been thrown
     by the target of an invocation."
Don't rename without updating the corresponding Revit event mapping.

Mirrors startup.py — where startup.py calls
aiblock.updater.register(uiapp), this removes the IUpdater
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

No-ops on Revit < 2027 and swallows any teardown exception —
shutdown must never surface a dialog to the user.

Note: do NOT call sys.exit() in a hook body. Hook scripts are
invoked through pyRevit's runtime which treats SystemExit as a
failed-invocation error in some load paths. Use plain control flow
to early-return instead.
"""
from pyrevit import HOST_APP


def _revit_is_2027_plus():
    """Robust against HOST_APP.version returning either str or int.

    pyRevit's _HostApplication.version forwards
    Application.VersionNumber, which the Revit API returns as a
    string like "2026". Some pyRevit builds normalise to int; we
    don't want to depend on which.
    """
    try:
        return int(HOST_APP.version) >= 2027
    except (TypeError, ValueError):
        return False


if _revit_is_2027_plus():
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
