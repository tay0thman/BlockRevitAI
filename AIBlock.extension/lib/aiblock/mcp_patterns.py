# -*- coding: utf-8 -*-
# Author: Tay Othman
"""MCP tool transaction fingerprint patterns.

Extracted from Revit 2027 journal analysis (April 8, 2026).
The Autodesk Assistant converts camelCase MCP tool names to
Title Case transaction names: batchModifyParameter → "Batch Modify Parameter"

Update this file as new MCP tool names are discovered via journal analysis.
"""

# -------------------------------------------------------------------
# Confirmed MCP tool names (from journal_0021.txt)
# -------------------------------------------------------------------
CONFIRMED_TOOLS = {
    "Batch Modify Parameter": "batchModifyParameter",
}

# -------------------------------------------------------------------
# Expected MCP tool names (from Autodesk's six tool groups)
# These follow the camelCase → Title Case pattern.
# Add to CONFIRMED_TOOLS once verified via journal capture.
# -------------------------------------------------------------------
EXPECTED_TOOLS = {
    # Sheet Management
    "Create Sheet": "createSheet",
    "Add View To Sheet": "addViewToSheet",
    "Remove View From Sheet": "removeViewFromSheet",
    # Room Management
    "Modify Room": "modifyRoom",
    "Create Room": "createRoom",
    # Schedules
    "Create Schedule": "createSchedule",
    "Modify Schedule": "modifySchedule",
    # Element Operations
    "Create Element": "createElement",
    "Delete Element": "deleteElement",
    "Modify Element": "modifyElement",
    "Move Element": "moveElement",
    "Copy Element": "copyElement",
    # Exports (likely read-only, but include for completeness)
    "Export View": "exportView",
    "Export PDF": "exportPDF",
    # Graphic Overrides
    "Set Graphic Override": "setGraphicOverride",
    "Apply View Filter": "applyViewFilter",
}

# -------------------------------------------------------------------
# Combined lookup
# -------------------------------------------------------------------
ALL_PATTERNS = {}
ALL_PATTERNS.update(CONFIRMED_TOOLS)
ALL_PATTERNS.update(EXPECTED_TOOLS)

KNOWN_TRANSACTION_NAMES = set(ALL_PATTERNS.keys())

# -------------------------------------------------------------------
# Fallback heuristic for unknown MCP tools
# -------------------------------------------------------------------
import re

_TITLE_CASE_PATTERN = re.compile(r"^[A-Z][a-z]+( [A-Z][a-z]+)*$")


def is_likely_mcp_transaction(tx_name):
    """Check if a transaction name matches MCP tool patterns.

    Returns (True, tool_name) if matched, (False, None) otherwise.
    """
    # Fast path — known pattern
    if tx_name in KNOWN_TRANSACTION_NAMES:
        return True, ALL_PATTERNS[tx_name]

    # Slow path — heuristic for unknown MCP tools
    if _TITLE_CASE_PATTERN.match(tx_name):
        word_count = len(tx_name.split())
        if 2 <= word_count <= 5:
            words = tx_name.split()
            probable_tool = words[0].lower() + "".join(
                w.capitalize() for w in words[1:]
            )
            return True, probable_tool

    return False, None
