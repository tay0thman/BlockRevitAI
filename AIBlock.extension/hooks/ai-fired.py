# -*- coding: utf-8 -*-
# Author: Tay Othman
"""AIBlock: ai-fired hook.

This script fires ONLY when the Autodesk Assistant (or any MCP tool)
commits a model-modifying transaction. It receives an AI_EVENT dict
with the full transaction summary and shows a confirmation dialog.

  Accept → changes stay, event is logged
  Reject → changes are undone via PostCommand(Undo), event is logged

Available context (injected by doc-changed.py):
  AI_EVENT = {
      "transaction_names":    ["Batch Modify Parameter"],
      "tool_names":           ["batchModifyParameter"],
      "added_ids":            [ElementId, ...],
      "modified_ids":         [ElementId, ...],
      "deleted_ids":          [ElementId, ...],
      "added_count":          int,
      "modified_count":       int,
      "deleted_count":        int,
      "categories_affected":  ["Walls", "Doors"],
      "elements_summary":     [{id, action, category, name}, ...],
      "document":             DB.Document,
      "document_title":       str,
      "timestamp":            str (ISO format),
  }
"""
import os

import clr
clr.AddReference("System")

from Autodesk.Revit.UI import (
    TaskDialog,
    TaskDialogCommonButtons,
    TaskDialogResult,
    RevitCommandId,
    PostableCommand,
)

from aiblock import log_event

# -------------------------------------------------------------------
# Read context
# -------------------------------------------------------------------
event = AI_EVENT  # noqa: F821 — injected by doc-changed.py
username = os.environ.get("USERNAME", "unknown")

# -------------------------------------------------------------------
# Build summary text
# -------------------------------------------------------------------
tool_names = ", ".join(event["tool_names"])
tx_names = ", ".join(event["transaction_names"])

change_lines = []
if event["added_count"] > 0:
    change_lines.append("  + {} element(s) added".format(event["added_count"]))
if event["modified_count"] > 0:
    change_lines.append(
        "  ~ {} element(s) modified".format(event["modified_count"])
    )
if event["deleted_count"] > 0:
    change_lines.append(
        "  - {} element(s) deleted".format(event["deleted_count"])
    )

if not change_lines:
    change_lines.append("  (no element changes detected)")

changes_text = "\n".join(change_lines)

categories = ", ".join(event["categories_affected"]) if event[
    "categories_affected"
] else "(none detected)"

# Detailed element list (for expandable section)
detail_lines = []
for entry in event["elements_summary"][:50]:
    line = "  [{}] {} — {}".format(
        entry["action"],
        entry["category"],
        entry["name"] or "(unnamed)",
    )
    detail_lines.append(line)

if len(event["elements_summary"]) > 50:
    detail_lines.append(
        "  ... and {} more elements".format(
            len(event["elements_summary"]) - 50
        )
    )

detail_text = "\n".join(detail_lines) if detail_lines else "(no details)"

# -------------------------------------------------------------------
# Show confirmation dialog
# -------------------------------------------------------------------
dialog = TaskDialog("AIBlock")
dialog.TitleAutoPrefix = False

dialog.MainInstruction = "Autodesk Assistant modified the model"

dialog.MainContent = (
    "MCP Tool:  {tool}\n"
    "Transaction:  {tx}\n"
    "Project:  {doc}\n"
    "\n"
    "Changes:\n"
    "{changes}\n"
    "\n"
    "Categories affected:  {cats}\n"
    "\n"
    "Click 'Accept' to keep the changes.\n"
    "Click 'Reject' to undo them immediately."
).format(
    tool=tool_names,
    tx=tx_names,
    doc=event["document_title"],
    changes=changes_text,
    cats=categories,
)

dialog.ExpandedContent = (
    "Element Details:\n"
    "{details}"
).format(details=detail_text)

dialog.CommonButtons = (
    TaskDialogCommonButtons.Yes | TaskDialogCommonButtons.No
)
dialog.DefaultButton = TaskDialogResult.No

dialog.FooterText = "Yes = Accept changes  |  No = Reject and Undo"

result = dialog.Show()

# -------------------------------------------------------------------
# Handle decision
# -------------------------------------------------------------------
if result == TaskDialogResult.Yes:
    log_event(
        "AI_ACCEPTED",
        username,
        "tool={} tx={} added={} modified={} deleted={} cats={}".format(
            tool_names,
            tx_names,
            event["added_count"],
            event["modified_count"],
            event["deleted_count"],
            categories,
        ),
    )

else:
    log_event(
        "AI_REJECTED",
        username,
        "tool={} tx={} added={} modified={} deleted={} cats={}".format(
            tool_names,
            tx_names,
            event["added_count"],
            event["modified_count"],
            event["deleted_count"],
            categories,
        ),
    )

    try:
        from pyrevit import HOST_APP
        uiapp = HOST_APP.uiapp
        undo_cmd = RevitCommandId.LookupPostableCommand(
            PostableCommand.Undo
        )
        uiapp.PostCommand(undo_cmd)
    except Exception:
        fallback = TaskDialog("AIBlock")
        fallback.TitleAutoPrefix = False
        fallback.MainInstruction = "Auto-undo failed"
        fallback.MainContent = (
            "Please press Ctrl+Z to undo the AI Assistant changes.\n\n"
            "The transaction '{}' should be at the top of your Undo stack."
        ).format(tx_names)
        fallback.CommonButtons = TaskDialogCommonButtons.Ok
        fallback.Show()
