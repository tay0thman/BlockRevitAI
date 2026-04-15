# -*- coding: utf-8 -*-
# Author: Tay Othman
"""MCP tool transaction fingerprint patterns.

Extracted from Revit 2027 journal analysis (April 8, 2026).
The Autodesk Assistant converts camelCase MCP tool names to
Title Case transaction names: batchModifyParameter → "Batch Modify Parameter"

ONLY add entries here after confirming them in a Revit journal file
with the 'Add-in component: MCPToolExecution' tag. Do NOT guess —
Revit's own commands use identical Title Case transaction names.
"""

# -------------------------------------------------------------------
# Confirmed MCP tool names (from journal files)
# -------------------------------------------------------------------
# ONLY add entries verified via journal capture with MCPToolExecution tag.
# Revit internal commands use the same Title Case naming convention,
# so guessing causes false positives.
CONFIRMED_TOOLS = {
    "Batch Modify Parameter": "batchModifyParameter",
}

KNOWN_TRANSACTION_NAMES = set(CONFIRMED_TOOLS.keys())


def is_likely_mcp_transaction(tx_name):
    """Check if a transaction name matches a confirmed MCP tool.

    Returns (True, tool_name) if matched, (False, None) otherwise.
    Dictionary-only — no heuristics, no guessing.
    """
    if tx_name in KNOWN_TRANSACTION_NAMES:
        return True, CONFIRMED_TOOLS[tx_name]

    return False, None