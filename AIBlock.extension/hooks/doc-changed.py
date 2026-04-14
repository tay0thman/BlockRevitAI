# -*- coding: utf-8 -*-
# Author: Tay Othman
"""AIBlock: doc-changed bridge for ai-fired hook.

This hook subscribes to DocumentChanged. For 99.9% of events
(manual user edits), it does a single dict lookup and returns.
Only when an MCP tool transaction is detected does it build
context and execute ai-fired.py.

Performance: One set-membership check per committed transaction.
"""
from pyrevit import HOST_APP
if HOST_APP.version < 2027:
    import sys
    sys.exit()
import os
from pyrevit import EXEC_PARAMS

from aiblock import is_guard_enabled
from aiblock.mcp_patterns import is_likely_mcp_transaction

# -------------------------------------------------------------------
# Bail immediately if guard is off
# -------------------------------------------------------------------
if not is_guard_enabled():
    import sys
    sys.exit()

# -------------------------------------------------------------------
# Get event args
# -------------------------------------------------------------------
args = EXEC_PARAMS.event_args  # DocumentChangedEventArgs
if args is None:
    import sys
    sys.exit()

doc = args.GetDocument()
if doc is None or doc.IsFamilyDocument:
    import sys
    sys.exit()

# -------------------------------------------------------------------
# Check transaction names — fast path: one lookup per name
# -------------------------------------------------------------------
tx_names = list(args.GetTransactionNames())
detected_tools = []

for tx_name in tx_names:
    is_mcp, tool_name = is_likely_mcp_transaction(tx_name)
    if is_mcp:
        detected_tools.append((tx_name, tool_name))

# Not an AI transaction → return immediately
if not detected_tools:
    import sys
    sys.exit()

# -------------------------------------------------------------------
# AI transaction detected — build context for ai-fired.py
# -------------------------------------------------------------------
added_ids = list(args.GetAddedElementIds())
modified_ids = list(args.GetModifiedElementIds())
deleted_ids = list(args.GetDeletedElementIds())

# Resolve categories for added and modified elements
categories_affected = set()
elements_summary = []

for eid in added_ids:
    elem = doc.GetElement(eid)
    if elem and elem.Category:
        cat_name = elem.Category.Name
        categories_affected.add(cat_name)
        elements_summary.append({
            "id": eid,
            "action": "ADDED",
            "category": cat_name,
            "name": getattr(elem, "Name", ""),
        })

for eid in modified_ids:
    elem = doc.GetElement(eid)
    if elem and elem.Category:
        cat_name = elem.Category.Name
        categories_affected.add(cat_name)
        elements_summary.append({
            "id": eid,
            "action": "MODIFIED",
            "category": cat_name,
            "name": getattr(elem, "Name", ""),
        })

for eid in deleted_ids:
    elements_summary.append({
        "id": eid,
        "action": "DELETED",
        "category": "(unknown — deleted)",
        "name": "",
    })

# -------------------------------------------------------------------
# Build the AI_EVENT context dict
# -------------------------------------------------------------------
import datetime

AI_EVENT = {
    "transaction_names": [t[0] for t in detected_tools],
    "tool_names": [t[1] for t in detected_tools],
    "added_ids": added_ids,
    "modified_ids": modified_ids,
    "deleted_ids": deleted_ids,
    "added_count": len(added_ids),
    "modified_count": len(modified_ids),
    "deleted_count": len(deleted_ids),
    "categories_affected": sorted(categories_affected),
    "elements_summary": elements_summary,
    "document": doc,
    "document_title": doc.Title,
    "timestamp": datetime.datetime.now().isoformat(),
}

# -------------------------------------------------------------------
# Execute ai-fired.py from the same hooks directory
# -------------------------------------------------------------------
_hooks_dir = os.path.dirname(__file__)
_ai_fired_path = os.path.join(_hooks_dir, "ai-fired.py")

if os.path.exists(_ai_fired_path):
    _namespace = {
        "AI_EVENT": AI_EVENT,
        "__file__": _ai_fired_path,
        "__name__": "__main__",
    }
    with open(_ai_fired_path, "r") as _f:
        exec(compile(_f.read(), _ai_fired_path, "exec"), _namespace)
