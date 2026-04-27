# -*- coding: utf-8 -*-
# Author: Tay Othman
"""AIBlock extension startup.

pyRevit runs this file once per session (and again after every
Reload) inside Revit's ApplicationInitialized window. That is the
only place where FailureDefinition.CreateFailureDefinition is
legal, so registration of the rollback-failure definition and the
IUpdater happens here.

No-ops on Revit < 2027 — the Assistant only ships on 2027+ and the
updater targets that surface.

Version-gate notes:
- HOST_APP.version forwards Application.VersionNumber, which the
  Revit API returns as a STRING like "2026". A bare comparison to
  the int 2027 silently misbehaves on Python 2 (str sorts above
  int by type-name) and TypeErrors on Python 3. Always cast first.
- Earlier revisions of this file used `sys.exit()` to bail. That's
  legal for a startup script but raises SystemExit, which some
  pyRevit log paths surface as "script terminated early" noise. The
  if-block pattern below produces a clean module-loaded-and-done
  trace instead, with no SystemExit and no exception in any logger.
"""
from pyrevit import HOST_APP


def _revit_is_2027_plus():
    try:
        return int(HOST_APP.version) >= 2027
    except (TypeError, ValueError):
        return False


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
else:
    # Optional breadcrumb — explicit "I saw the wrong Revit version
    # and bailed" line in the pyRevit log so future debugging doesn't
    # have to guess. Best-effort: stays silent if the logger is not
    # available yet during startup.
    try:
        from pyrevit import script
        script.get_logger().debug(
            "AIBlock startup: skipped on Revit {} (requires 2027+)"
            .format(HOST_APP.version)
        )
    except Exception:
        pass
