# -*- coding: utf-8 -*-
# Author: Tay Othman
"""MCP tool transaction fingerprint patterns.

Extracted from Revit 2027 journal analysis (April 8, 2026).
The Autodesk Assistant converts camelCase MCP tool names to
Title Case transaction names: batchModifyParameter → "Batch Modify Parameter"

IMPORTANT: Only CONFIRMED_TOOLS and EXPECTED_TOOLS are checked.
There is no fuzzy heuristic — this avoids false positives from
Revit internal transactions like "Reload Latest", "Mirror Elements",
"Create Walls", etc. that also happen to be Title Case.

Update this file as new MCP tool names are discovered via journal analysis.
"""

# -------------------------------------------------------------------
# Confirmed MCP tool names (from journal_0021.txt)
# -------------------------------------------------------------------
# Format: "Transaction Name" → "mcpToolName"
# Add entries here ONLY after verifying via journal file capture.
CONFIRMED_TOOLS = {
    "Batch Modify Parameter": "batchModifyParameter",
}

# -------------------------------------------------------------------
# Expected MCP tool names (from Autodesk's six tool groups)
# These follow the camelCase → Title Case pattern.
# Move to CONFIRMED_TOOLS once verified via journal capture.
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
# Combined lookup — dictionary only, no heuristic
# -------------------------------------------------------------------
ALL_PATTERNS = {}
ALL_PATTERNS.update(CONFIRMED_TOOLS)
ALL_PATTERNS.update(EXPECTED_TOOLS)

KNOWN_TRANSACTION_NAMES = set(ALL_PATTERNS.keys())


def is_likely_mcp_transaction(tx_name):
    """Check if a transaction name matches a known MCP tool pattern.

    Returns (True, tool_name) if matched, (False, None) otherwise.

    Detection is dictionary-only — no regex heuristic.
    New MCP tool names must be added explicitly to CONFIRMED_TOOLS
    or EXPECTED_TOOLS after journal verification.
    """
    if tx_name in KNOWN_TRANSACTION_NAMES:
        return True, ALL_PATTERNS[tx_name]

    return False, None