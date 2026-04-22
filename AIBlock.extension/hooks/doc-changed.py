# -*- coding: utf-8 -*-
# Author: Tay Othman
"""AIBlock: doc-changed anomaly logger.

Primary defence is the IUpdater registered by startup.py, which rolls
back AI transactions atomically via FailureMessage. This hook is a
pure safety net — it fires post-commit, identifies known MCP
transaction names by dictionary, and writes an audit entry when one
actually committed.

Under the three-mode policy the event tag depends on whether the
commit was expected given current policy:

  AI_UPDATER_BYPASS     — should_block_ai_writes() == True, yet the
                          transaction still committed. The updater
                          either didn't fire, didn't recognise the AI
                          assembly, or a new MCP tool slipped past
                          AI_ASSEMBLY_MARKERS. Investigate.

  AI_COMMITTED_ALLOWED  — should_block_ai_writes() == False. AI is
                          allowed to write in the current mode, so
                          this is a normal commit. Logged for audit
                          attribution, not as an alert.

Performance: one set-membership check per committed transaction.
"""
from pyrevit import HOST_APP
if HOST_APP.version < 2027:
    import sys
    sys.exit()

import os
from pyrevit import EXEC_PARAMS

from aiblock import get_mode, log_event, should_block_ai_writes
from aiblock.mcp_patterns import is_likely_mcp_transaction

args = EXEC_PARAMS.event_args
if args is None:
    import sys
    sys.exit()

doc = args.GetDocument()
if doc is None or doc.IsFamilyDocument:
    import sys
    sys.exit()

tx_names = list(args.GetTransactionNames())
leaked_tools = []
for tx_name in tx_names:
    matched, tool_name = is_likely_mcp_transaction(tx_name)
    if matched:
        leaked_tools.append((tx_name, tool_name))

if not leaked_tools:
    import sys
    sys.exit()

username = os.environ.get("USERNAME", "unknown")
added = len(list(args.GetAddedElementIds()))
modified = len(list(args.GetModifiedElementIds()))
deleted = len(list(args.GetDeletedElementIds()))

# Distinguish "this should have been blocked" from "this was allowed
# by policy". Same underlying signal, very different operational
# meaning: the first is a bug report, the second is audit-trail.
event_tag = (
    "AI_UPDATER_BYPASS"
    if should_block_ai_writes()
    else "AI_COMMITTED_ALLOWED"
)

log_event(
    event_tag,
    username,
    "mode={} tx={} tools={} added={} modified={} deleted={}".format(
        get_mode(),
        "|".join(t[0] for t in leaked_tools),
        "|".join(t[1] for t in leaked_tools),
        added,
        modified,
        deleted,
    ),
)
