# -*- coding: utf-8 -*-
# Author: Tay Othman
"""AIBlock dynamic-model-update guard.

This module defines:

  1. A FailureDefinition with Error severity. Posting this from inside
     a transaction triggers Revit's own rollback machinery — the
     transaction never commits and the undo stack is untouched.

  2. An IUpdater that fires during the commit phase of every
     transaction that mutates a document element. When guard_enabled is
     True AND the change originated from the Autodesk Assistant, the
     updater posts the failure so Revit rolls the transaction back
     atomically.

  3. A FailuresProcessing subscriber that silently resolves our
     specific failure so Revit's generic "Error 1 / OK / Cancel" modal
     never appears. The rollback still happens; only the branded
     AIBlock dialog (posted on the next idle tick) is visible to the
     user.

  4. Registration / unregistration helpers safe to call on pyRevit
     reload — duplicate registration is handled gracefully.

  5. An Idling subscriber that dequeues rollback records from
     aiblock.state and shows the Accept / Reject dialog on the main
     UI thread, outside any transaction.

Only IUpdater gives third-party code a hook that runs inside another
party's transaction. DocumentChanged fires post-commit, FailuresProcessing
only fires when a failure has already been posted. The updater-plus-
FailureMessage combination is the only API-native path to reliable,
atomic pre-commit interception.
"""
import os
import datetime
import threading

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from System import Guid, EventHandler
from System.Diagnostics import StackTrace
from Autodesk.Revit.DB import (
    AddInId,
    Element,
    ElementClassFilter,
    ElementIsElementTypeFilter,
    FailureDefinition,
    FailureDefinitionId,
    FailureProcessingResult,
    FailureSeverity,
    FailureMessage,
    IUpdater,
    LogicalOrFilter,
    UpdaterId,
    UpdaterRegistry,
    ChangePriority,
)
from Autodesk.Revit.DB.Events import FailuresProcessingEventArgs
from Autodesk.Revit.UI.Events import IdlingEventArgs
from Autodesk.Revit.UI import (
    TaskDialog,
    TaskDialogCommonButtons,
    TaskDialogResult,
)

from aiblock import (
    MODE_BLOCK_ALL,
    MODE_BLOCK_WRITES,
    MODE_USER_CONTROLLED,
    MODE_LABELS,
    get_mode,
    get_session_id,
    log_event,
    should_block_ai_writes,
)

# Cache the session id at import so _trace() doesn't do a function call
# per line in hot paths (Execute() runs inside Revit's transaction
# commit — we keep it tight).
_SESSION_ID_CACHED = get_session_id()
from aiblock.state import (
    consume_one_pass,
    enqueue_decision,
    drain_decisions,
    grant_one_pass,
    has_pending,
)


# -------------------------------------------------------------------
# Stable GUIDs. These MUST NOT change between releases — they identify
# the updater and failure definition across pyRevit reloads and Revit
# sessions. Generate-once, commit-forever.
#
# NOTE: AIBLOCK_ADDIN_GUID is retained for reference only and is NOT
# used to construct the UpdaterId. Revit 2020+ enforces that
# UpdaterId.GetAddInId() matches the *currently active* AddIn at the
# call site — and because AIBlock runs as a pyRevit extension, the
# active AddIn is always pyRevit's loader, not AIBlock. Using a custom
# GUID here produces "DBG_WARN: Trying to modify an updater that
# doesn't belong to the currently active AddIn" in the Revit journal
# and the registration is silently dropped. See register() below for
# the runtime resolution logic.
# -------------------------------------------------------------------
AIBLOCK_ADDIN_GUID = Guid("8f3b2a11-47c5-4f6a-9a1d-8f04c9b7e210")  # reserved, unused
AIBLOCK_UPDATER_GUID = Guid("d2a9c6f4-1f3b-4c58-8d7e-6a2b9f3e4d10")
AIBLOCK_FAILURE_GUID = Guid("a4f1e7b2-9d3c-4e80-8c1b-2a7d6f5e4b30")

# pyRevit's loader AddIn GUID (from PyRevitLoader.addin). Used only as
# a fallback when UIApplication.ActiveAddInId is unavailable.
_PYREVIT_ADDIN_GUID = Guid("b39107c3-a1d7-47f4-a5a1-532ddf6edb5d")


# Assembly-name substrings that identify an AI-driven call. If any of
# these appear on the managed stack during Execute(), the transaction
# was initiated by the Assistant pipeline.
AI_ASSEMBLY_MARKERS = (
    "Autodesk.Assistant",
    "ModelContextProtocol",
)


# Module-level singletons. Populated by register(); cleared by unregister().
_UPDATER_INSTANCE = None
_IDLING_HANDLER = None
_FAILURES_HANDLER = None


# -------------------------------------------------------------------
# Verbose trace log
# -------------------------------------------------------------------
# Writes to %TEMP%\aiblock_trace.log. Used to verify whether Execute()
# fires for AI transactions and, if so, what assemblies are on the
# managed stack at commit time.
#
# Two-layer gate:
#   1. _TRACE_HARD_KILL (source-level) — set to True to disable
#      tracing entirely regardless of config. Intended for a final
#      GA release once field confidence is high enough that we no
#      longer want the trace file being created at all.
#   2. verbose_trace (config) — the BIM Manager-facing knob. Cached
#      at module load so transaction-time writes don't thrash
#      load_config(). To change at runtime, edit config and reload
#      pyRevit (the module re-imports, cache resets).
#
# The cache starts as None and is resolved on first call. If config
# read fails for any reason, the cache defaults to True — we'd
# rather have a diagnostic trace than silent nothing during an
# incident.
_TRACE_HARD_KILL = False
_TRACE_PATH = os.path.join(
    os.environ.get("TEMP", os.environ.get("TMP", ".")),
    "aiblock_trace.log",
)
# Rolled file. On rotation, _TRACE_PATH → _TRACE_ROLL_PATH, new file
# starts fresh. Only two files ever exist, so local disk stays bounded
# at roughly 2 × _TRACE_MAX_BYTES even on very long sessions.
_TRACE_ROLL_PATH = _TRACE_PATH + ".1"
_TRACE_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB per file, 10 MiB total worst case
_trace_enabled_cached = None


def _is_trace_enabled():
    global _trace_enabled_cached
    if _TRACE_HARD_KILL:
        return False
    if _trace_enabled_cached is None:
        try:
            from aiblock import load_config as _lc
            _trace_enabled_cached = bool(
                _lc().get("verbose_trace", True)
            )
        except Exception:
            _trace_enabled_cached = True
    return _trace_enabled_cached


def _rotate_trace_if_big():
    """Cap local trace at two files × _TRACE_MAX_BYTES.

    Called before every append. When the active file crosses the
    threshold, rename it to aiblock_trace.log.1 (replacing the
    previous .1 if present) and let _trace() re-create a fresh
    active file on its next write.

    Races between threads are benign — if two threads both observe
    the oversize file and both try to rename, one succeeds and the
    other's rename raises, which we swallow. Worst case a couple of
    extra trace lines land in the rolled file. Good enough.

    Fails silent on anything — rotation must never block tracing
    which must never block Execute().
    """
    try:
        if not os.path.exists(_TRACE_PATH):
            return
        if os.path.getsize(_TRACE_PATH) < _TRACE_MAX_BYTES:
            return
        # Over threshold: drop the previous roll (os.rename on Windows
        # fails if the destination exists) and promote the current file.
        if os.path.exists(_TRACE_ROLL_PATH):
            try:
                os.remove(_TRACE_ROLL_PATH)
            except Exception:
                # Can't remove old roll (locked by a notepad window?).
                # Bail — better to let the live file keep growing than
                # to lose the rotation altogether. Next call will retry.
                return
        os.rename(_TRACE_PATH, _TRACE_ROLL_PATH)
    except Exception:
        pass


def _trace(tag, detail=""):
    if not _is_trace_enabled():
        return
    try:
        _rotate_trace_if_big()
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        # sid= is the aiblock session_id — same 8-hex value stamped
        # on every audit-log JSONL line. Makes it trivial for a BIM
        # Manager to ask "show me the trace for this audit event" and
        # grep the local file.
        line = "{} sid={} tid={} {}: {}\n".format(
            stamp,
            _SESSION_ID_CACHED,
            threading.current_thread().ident,
            tag,
            detail,
        )
        with open(_TRACE_PATH, "a") as f:
            f.write(line)
    except Exception:
        # Tracing must never block Revit or Execute.
        pass


def _dump_stack_assemblies(limit=25):
    """Return a compact summary of the top `limit` managed stack
    frames — assembly name + method name — for origin diagnosis."""
    try:
        trace = StackTrace(False)
    except Exception as exc:
        return "<StackTrace unavailable: {}>".format(exc)

    rows = []
    count = min(limit, trace.FrameCount)
    for i in range(count):
        try:
            frame = trace.GetFrame(i)
            if frame is None:
                continue
            method = frame.GetMethod()
            if method is None:
                continue
            decl = method.DeclaringType
            asm_name = "<?>"
            type_name = "<?>"
            if decl is not None:
                type_name = decl.FullName or "<?>"
                try:
                    asm = decl.Assembly
                    if asm is not None:
                        asm_name = asm.GetName().Name or "<?>"
                except Exception:
                    pass
            rows.append("{}!{}.{}".format(asm_name, type_name, method.Name))
        except Exception:
            continue
    return " | ".join(rows) if rows else "<empty stack>"


# -------------------------------------------------------------------
# FailureDefinition
# -------------------------------------------------------------------
# Revit requires FailureDefinition.CreateFailureDefinition to run during
# ApplicationInitialized. Calling it twice with the same GUID raises —
# pyRevit reload has to swallow that.
#
# Severity is Warning, NOT Error. Reasoning: Revit 2027 shows a
# non-suppressible "Error - cannot be ignored" modal for every unresolved
# Error-severity failure, even when a FailuresProcessing subscriber
# returns ProceedWithRollBack. Warnings CAN be dismissed from the
# accessor (via DeleteWarning), and our explicit SetProcessingResult(
# ProceedWithRollBack) still forces an atomic rollback regardless of
# severity. The net behaviour is identical to Error — the transaction
# never commits — but with no native dialog.
#
# If the severity is ever flipped back to Error, you must restart Revit
# (not just reload pyRevit): FailureDefinition registrations are
# session-scoped and cannot be replaced with a different severity
# under the same GUID.
def _ensure_failure_definition():
    fail_id = FailureDefinitionId(AIBLOCK_FAILURE_GUID)
    try:
        FailureDefinition.CreateFailureDefinition(
            fail_id,
            FailureSeverity.Warning,
            "AIBlock blocked an AI-driven model change.",
        )
    except Exception:
        # Already registered in this Revit session. Safe to ignore —
        # the id stays valid. NOTE: if the prior registration used a
        # different severity, Revit will keep the prior severity until
        # process restart.
        pass
    return fail_id


# -------------------------------------------------------------------
# AI-origin detection via managed stack walk
# -------------------------------------------------------------------
def _is_ai_origin():
    """True when the current managed call stack includes an assembly
    owned by the Autodesk Assistant pipeline. The Assistant invokes
    the API through its own IExternalEventHandler, so its assembly is
    on the stack for every transaction it commits. Manual edits and
    pyRevit-driven edits never touch those assemblies."""
    try:
        trace = StackTrace(False)
    except Exception:
        return False

    for i in range(trace.FrameCount):
        frame = trace.GetFrame(i)
        if frame is None:
            continue
        method = frame.GetMethod()
        if method is None:
            continue
        decl = method.DeclaringType
        if decl is None:
            continue
        asm = decl.Assembly
        if asm is None:
            continue
        try:
            name = asm.GetName().Name or ""
        except Exception:
            continue
        for marker in AI_ASSEMBLY_MARKERS:
            if marker in name:
                return True
    return False


# -------------------------------------------------------------------
# IUpdater implementation
# -------------------------------------------------------------------
class AIBlockUpdater(IUpdater):
    """Fires during transaction commit. When armed and AI-originated,
    posts a failure that forces Revit to roll the transaction back
    atomically."""

    def __init__(self, addin_id, failure_id):
        self._updater_id = UpdaterId(addin_id, AIBLOCK_UPDATER_GUID)
        self._failure_id = failure_id

    # --- IUpdater members -----------------------------------------
    def Execute(self, data):
        # --- Unconditional entry trace --------------------------------
        # Written BEFORE any gate so we can tell from the trace file
        # whether Execute even fires for AI transactions. Without this
        # we can't distinguish "Revit never dispatched to us" from
        # "we were dispatched and chose to pass through".
        try:
            doc = data.GetDocument()
            doc_title = doc.Title if doc is not None else "<no-doc>"
            added_n = data.GetAddedElementIds().Count
            modified_n = data.GetModifiedElementIds().Count
            deleted_n = data.GetDeletedElementIds().Count
        except Exception as exc:
            _trace(
                "EXECUTE_ENTER_ERR",
                "could not read ChangedElementsData: {}".format(exc),
            )
            return

        _trace(
            "EXECUTE_ENTER",
            "doc={} added={} modified={} deleted={}".format(
                doc_title, added_n, modified_n, deleted_n,
            ),
        )

        # Fast path: policy says let AI writes through → pass.
        # `should_block_ai_writes()` folds in the current mode:
        #   MODE_BLOCK_ALL, MODE_BLOCK_WRITES  → always True (block)
        #   MODE_USER_CONTROLLED               → reflects per-session toggle
        # The previous gate checked the raw guard_enabled flag, which
        # silently ignored the BIM-enforced modes.
        if not should_block_ai_writes():
            _trace("EXIT_POLICY_ALLOWS", "doc={}".format(doc_title))
            return

        if doc is None or doc.IsFamilyDocument:
            _trace(
                "EXIT_NO_DOC_OR_FAMILY",
                "doc={} is_family={}".format(
                    doc_title, getattr(doc, "IsFamilyDocument", "?"),
                ),
            )
            return

        # Only block AI-originated transactions. Manual edits while
        # the guard is enabled still commit normally.
        ai = _is_ai_origin()
        if not ai:
            # This is the critical diagnostic: if AI transactions
            # repeatedly land here, either the stack walk is failing
            # or Autodesk's MCP pipeline does not leave its assemblies
            # on the managed stack at commit time. Dump the top frames
            # so we can tune AI_ASSEMBLY_MARKERS.
            _trace(
                "EXIT_NOT_AI_ORIGIN",
                "doc={} stack={}".format(
                    doc_title, _dump_stack_assemblies(limit=25),
                ),
            )
            return

        _trace("AI_ORIGIN_DETECTED", "doc={}".format(doc_title))

        # One-shot approval is a MODE_USER_CONTROLLED-only escape hatch.
        # In MODE_BLOCK_ALL / MODE_BLOCK_WRITES the BIM Management Team
        # has decided there is no per-user override, so we do NOT honour
        # a pending one-pass grant — that would be a trivial way to
        # defeat the policy (click Allow Next once in Mode 3, then have
        # the BIM Manager swap to Mode 2, and a stale grant would let
        # the next AI commit through). We consume the flag anyway to
        # clear any leftover state from a prior session.
        current_mode = get_mode()
        if current_mode == MODE_USER_CONTROLLED:
            if consume_one_pass():
                _trace("EXIT_ONE_PASS", "doc={}".format(doc_title))
                log_event(
                    "AI_PASSTHROUGH",
                    os.environ.get("USERNAME", "unknown"),
                    "doc={}".format(doc_title),
                )
                return
        else:
            # Drain any stale grant silently so it can't apply later.
            if consume_one_pass():
                _trace(
                    "ONE_PASS_DISCARDED_BY_MODE",
                    "mode={} doc={}".format(current_mode, doc_title),
                )

        # Collect what the transaction tried to do so the dialog can
        # describe it accurately. Element lookups are still valid
        # here — rollback happens at commit, not at Execute().
        added = list(data.GetAddedElementIds())
        modified = list(data.GetModifiedElementIds())
        deleted = list(data.GetDeletedElementIds())

        categories = set()
        for eid in list(added) + list(modified):
            elem = doc.GetElement(eid)
            if elem is not None and elem.Category is not None:
                categories.add(elem.Category.Name)

        record = {
            "doc_title": doc.Title,
            "added": len(added),
            "modified": len(modified),
            "deleted": len(deleted),
            "categories": sorted(categories),
            "timestamp": datetime.datetime.now().isoformat(),
        }
        enqueue_decision(record)

        # The critical line. PostFailure with Error severity causes
        # Revit's failure processor to roll the whole transaction
        # back at commit time — atomic, no undo-stack interaction.
        try:
            doc.PostFailure(FailureMessage(self._failure_id))
            _trace(
                "POST_FAILURE_OK",
                "doc={} cats={}".format(doc_title, ",".join(sorted(categories))),
            )
        except Exception as exc:
            _trace(
                "POST_FAILURE_FAIL",
                "doc={} err={}".format(doc_title, exc),
            )
            raise

    def GetUpdaterId(self):
        return self._updater_id

    def GetUpdaterName(self):
        return "AIBlock Guard"

    def GetAdditionalInformation(self):
        # Shown in Revit's "Manage Updaters" dialog. Reflects the
        # three-mode policy the updater actually enforces (set by the
        # BIM Management Team) rather than the old MCP-intercept
        # description, so a BIM Manager inspecting Revit's updater
        # registry sees language that matches the Settings UI.
        return (
            "Enforces BIM Management Team AI policy "
            "(block_all / block_writes / user_controlled). "
            "Rolls back AI-originated transactions atomically."
        )

    def GetChangePriority(self):
        # Priority only affects execution order relative to other
        # updaters; it does not influence whether the rollback fires.
        # Annotations is a long-standing, benign bucket.
        return ChangePriority.Annotations


# -------------------------------------------------------------------
# Idling handler — shows the dialog outside any transaction
# -------------------------------------------------------------------
def _on_idling(sender, args):
    """Drains the pending-decision queue. For each rolled-back AI
    transaction, shows a modal dialog on the main thread."""
    if not has_pending():
        return

    records = drain_decisions()
    username = os.environ.get("USERNAME", "unknown")

    for rec in records:
        _show_decision_dialog(rec, username)


def _show_decision_dialog(rec, username):
    """Show the branded rollback dialog.

    The buttons depend on the current enforcement mode:

      MODE_USER_CONTROLLED
        The user has agency — show Yes ("Allow next") / No ("Keep blocked")
        exactly as before. A Yes grants a one-pass bypass so the user
        can re-issue the prompt and have that single transaction
        commit.

      MODE_BLOCK_ALL / MODE_BLOCK_WRITES
        The BIM Management Team has made the policy decision. There is
        no per-user override — the dialog is informational only. Show
        a single OK button and direct the user to request a mode change
        from their BIM Manager instead. Offering "Allow next" here
        would be a trivial way to defeat the enforced policy.
    """
    changes = []
    if rec["added"]:
        changes.append("  + {} element(s) would have been added".format(rec["added"]))
    if rec["modified"]:
        changes.append("  ~ {} element(s) would have been modified".format(rec["modified"]))
    if rec["deleted"]:
        changes.append("  - {} element(s) would have been deleted".format(rec["deleted"]))
    if not changes:
        changes.append("  (no element changes captured)")

    cats = ", ".join(rec["categories"]) if rec["categories"] else "(none)"
    mode = get_mode()
    mode_label = MODE_LABELS.get(mode, mode)

    dialog = TaskDialog("AIBlock")
    dialog.TitleAutoPrefix = False
    dialog.MainInstruction = "AI transaction was blocked"

    if mode == MODE_USER_CONTROLLED:
        dialog.MainContent = (
            "Project:  {doc}\n"
            "\n"
            "Blocked changes:\n"
            "{ch}\n"
            "\n"
            "Categories:  {cats}\n"
            "\n"
            "The transaction was rolled back atomically — nothing was "
            "written to the model and the undo stack is untouched.\n"
            "\n"
            "Click 'Allow next' to authorise the next AI transaction only. "
            "Re-issue your prompt to the Assistant after dismissing this "
            "dialog.\n"
            "Click 'Keep blocked' to leave the rollback in place."
        ).format(doc=rec["doc_title"], ch="\n".join(changes), cats=cats)
        dialog.CommonButtons = (
            TaskDialogCommonButtons.Yes | TaskDialogCommonButtons.No
        )
        dialog.DefaultButton = TaskDialogResult.No
        dialog.FooterText = "Yes = Allow next  |  No = Keep blocked"
    else:
        # BIM-enforced mode. No override offered.
        dialog.MainContent = (
            "Project:  {doc}\n"
            "\n"
            "Blocked changes:\n"
            "{ch}\n"
            "\n"
            "Categories:  {cats}\n"
            "\n"
            "Policy mode:  {mode}\n"
            "\n"
            "The transaction was rolled back atomically — nothing was "
            "written to the model and the undo stack is untouched.\n"
            "\n"
            "This mode is set by your BIM Management Team and cannot be "
            "overridden on a per-transaction basis. If you need AI to "
            "modify the model, ask your BIM Manager to change the AIBlock "
            "mode for this project."
        ).format(
            doc=rec["doc_title"],
            ch="\n".join(changes),
            cats=cats,
            mode=mode_label,
        )
        dialog.CommonButtons = TaskDialogCommonButtons.Ok
        dialog.DefaultButton = TaskDialogResult.Ok
        dialog.FooterText = "Contact your BIM Manager to change modes."

    result = dialog.Show()

    detail = "added={} modified={} deleted={} cats={} mode={}".format(
        rec["added"], rec["modified"], rec["deleted"], cats, mode
    )

    if mode == MODE_USER_CONTROLLED and result == TaskDialogResult.Yes:
        grant_one_pass()
        log_event("AI_ALLOW_NEXT", username, detail)
    else:
        log_event("AI_BLOCKED", username, detail)


# -------------------------------------------------------------------
# FailuresProcessing — suppress Revit's native "Error 1" modal
# -------------------------------------------------------------------
# When AIBlockUpdater.Execute posts our FailureDefinition, Revit's
# failure processor raises FailuresProcessing BEFORE it would show the
# generic "Error (must be addressed in order to continue)" task dialog.
# We inspect the accessor for AIBLOCK_FAILURE_GUID and, if present,
# call SetProcessingResult(ProceedWithRollBack). That tells Revit to
# roll the transaction back atomically without surfacing its own modal.
#
# Net effect: the only UI the BIM manager sees is the branded AIBlock
# "AI transaction was blocked / Allow next / Keep blocked" dialog shown
# by the Idling handler on the next idle tick. The native dialog is
# fully elided.
#
# Safety: we only elide if our specific failure is in the accessor. If
# the transaction posted other failures (e.g. geometric errors from
# whatever the AI tried to do), we fall through and let Revit handle
# them normally. Error-severity failures always force rollback, so
# ProceedWithRollBack is correct even when other errors coexist.
def _on_failures_processing(sender, args):
    try:
        accessor = args.GetFailuresAccessor()
        if accessor is None:
            return

        ours = False
        deleted_ok = False
        for msg in accessor.GetFailureMessages():
            try:
                fid = msg.GetFailureDefinitionId()
                if fid is not None and fid.Guid == AIBLOCK_FAILURE_GUID:
                    ours = True
                    # DeleteWarning removes our failure from the accessor
                    # before Revit's default-UI stage runs. This is what
                    # actually suppresses the modal — ProceedWithRollBack
                    # alone doesn't, because Revit still shows "Error -
                    # cannot be ignored" for any unresolved Error in the
                    # accessor. Our definition is registered with
                    # FailureSeverity.Warning, so DeleteWarning works.
                    try:
                        accessor.DeleteWarning(msg)
                        deleted_ok = True
                    except Exception as del_exc:
                        # Most likely cause: the FailureDefinition was
                        # registered as Error in a prior session and
                        # Revit hasn't been restarted since we switched
                        # to Warning. DeleteWarning refuses Errors.
                        _trace(
                            "DELETE_WARNING_FAIL",
                            "err={} — restart Revit if severity changed".format(
                                del_exc
                            ),
                        )
                    break
            except Exception:
                continue

        if ours:
            # Belt-and-suspenders: explicit rollback in case the
            # transaction might otherwise commit with only a warning.
            args.SetProcessingResult(
                FailureProcessingResult.ProceedWithRollBack
            )
            _trace(
                "FAILURES_SUPPRESSED",
                "rolled back silently deleted={}".format(deleted_ok),
            )
    except Exception as exc:
        _trace("FAILURES_PROCESSING_ERR", "err={}".format(exc))


# -------------------------------------------------------------------
# Active AddIn resolution
# -------------------------------------------------------------------
def _resolve_active_addin_id(uiapp):
    """Return the AddInId Revit considers active at this call site.

    UpdaterRegistry.RegisterUpdater fails silently (DBG_WARN in
    journal, no registration) if UpdaterId.GetAddInId() doesn't match
    the AddIn currently driving the call. For pyRevit extensions that
    AddIn is always pyRevit's loader — never a GUID invented by the
    extension author.

    Prefers UIApplication.ActiveAddInId so we follow whatever pyRevit
    loader is actually in use (IronPython vs CPython vs Roslyn). Falls
    back to the documented PyRevitLoader GUID if the runtime property
    is unavailable (which can happen outside a Revit-initiated
    callback).
    """
    try:
        active = uiapp.ActiveAddInId
        if active is not None:
            return active
    except Exception:
        pass
    return AddInId(_PYREVIT_ADDIN_GUID)


# -------------------------------------------------------------------
# Registration
# -------------------------------------------------------------------
def register(uiapp):
    """Idempotent. Called from startup.py once per Revit session and
    again after every pyRevit reload."""
    global _UPDATER_INSTANCE, _IDLING_HANDLER, _FAILURES_HANDLER

    username = os.environ.get("USERNAME", "unknown")
    fail_id = _ensure_failure_definition()
    addin_id = _resolve_active_addin_id(uiapp)

    try:
        addin_guid_str = str(addin_id.GetGUID())
    except Exception:
        addin_guid_str = "<unresolved>"

    # If a stale updater from a previous reload is still registered,
    # drop it first so the new instance owns the triggers.
    try:
        stale_id = UpdaterId(addin_id, AIBLOCK_UPDATER_GUID)
        if UpdaterRegistry.IsUpdaterRegistered(stale_id):
            UpdaterRegistry.UnregisterUpdater(stale_id)
    except Exception:
        pass

    updater = AIBlockUpdater(addin_id, fail_id)
    try:
        UpdaterRegistry.RegisterUpdater(updater)
    except Exception as exc:
        log_event(
            "UPDATER_REGISTER_FAIL",
            username,
            "addin={} err={}".format(addin_guid_str, exc),
        )
        raise

    # The trigger filter must match EVERY element the AI might touch.
    # A LogicalOrFilter over ElementIsElementTypeFilter(True) and
    # ElementIsElementTypeFilter(False) covers both type-level and
    # instance-level elements — i.e. the entire element universe —
    # and is accepted by every Revit 2020+ build. Element (the abstract
    # base class) is refused as a filter by some Revit 2027 builds, so
    # the previous ElementClassFilter(Element) path was discarded.
    everything_filter = LogicalOrFilter(
        ElementIsElementTypeFilter(True),
        ElementIsElementTypeFilter(False),
    )
    try:
        UpdaterRegistry.AddTrigger(
            updater.GetUpdaterId(),
            everything_filter,
            Element.GetChangeTypeAny(),
        )
        _trace(
            "TRIGGER_ADDED",
            "addin={} updater={}".format(addin_guid_str, AIBLOCK_UPDATER_GUID),
        )
    except Exception as exc:
        _trace(
            "TRIGGER_FAIL",
            "addin={} err={}".format(addin_guid_str, exc),
        )
        log_event(
            "UPDATER_TRIGGER_FAIL",
            username,
            "addin={} err={}".format(addin_guid_str, exc),
        )
        # Attempt unregister so we don't leave a half-configured
        # updater behind for the next reload.
        try:
            UpdaterRegistry.UnregisterUpdater(updater.GetUpdaterId())
        except Exception:
            pass
        raise

    _UPDATER_INSTANCE = updater

    # Verify the registration actually took. On mismatched AddInId
    # Revit emits DBG_WARN and silently drops the updater — in that
    # case IsUpdaterRegistered returns False even though no exception
    # was raised.
    registered = False
    try:
        registered = UpdaterRegistry.IsUpdaterRegistered(updater.GetUpdaterId())
    except Exception:
        pass

    log_event(
        "UPDATER_REGISTERED" if registered else "UPDATER_REGISTER_DROPPED",
        username,
        "addin={} updater={}".format(addin_guid_str, str(AIBLOCK_UPDATER_GUID)),
    )
    _trace(
        "UPDATER_REGISTERED" if registered else "UPDATER_REGISTER_DROPPED",
        "addin={} updater={}".format(addin_guid_str, AIBLOCK_UPDATER_GUID),
    )

    # Replace any previous Idling handler before attaching the new one.
    if _IDLING_HANDLER is not None:
        try:
            uiapp.Idling -= _IDLING_HANDLER
        except Exception:
            pass

    handler = EventHandler[IdlingEventArgs](_on_idling)
    uiapp.Idling += handler
    _IDLING_HANDLER = handler

    # Replace any previous FailuresProcessing handler. The event lives
    # on ControlledApplication (uiapp.Application), NOT on UIApplication
    # — attaching to UIApplication would be a silent no-op.
    app = uiapp.Application
    if _FAILURES_HANDLER is not None:
        try:
            app.FailuresProcessing -= _FAILURES_HANDLER
        except Exception:
            pass

    failures_handler = EventHandler[FailuresProcessingEventArgs](
        _on_failures_processing
    )
    try:
        app.FailuresProcessing += failures_handler
        _FAILURES_HANDLER = failures_handler
        _trace("FAILURES_HANDLER_ATTACHED", "")
    except Exception as exc:
        _trace("FAILURES_HANDLER_ATTACH_FAIL", "err={}".format(exc))


def unregister(uiapp):
    """Called by pyRevit's shutdown hook (if any) — best-effort."""
    global _UPDATER_INSTANCE, _IDLING_HANDLER, _FAILURES_HANDLER

    if _IDLING_HANDLER is not None:
        try:
            uiapp.Idling -= _IDLING_HANDLER
        except Exception:
            pass
        _IDLING_HANDLER = None

    if _FAILURES_HANDLER is not None:
        try:
            uiapp.Application.FailuresProcessing -= _FAILURES_HANDLER
        except Exception:
            pass
        _FAILURES_HANDLER = None

    if _UPDATER_INSTANCE is not None:
        try:
            UpdaterRegistry.UnregisterUpdater(_UPDATER_INSTANCE.GetUpdaterId())
        except Exception:
            pass
        _UPDATER_INSTANCE = None
