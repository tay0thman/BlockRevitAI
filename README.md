# BlockRevitAI

A pyRevit extension that gives BIM Managers control over the **Autodesk Assistant** (built-in AI) in Revit 2027.

Revit 2027 ships with an LLM connected directly to the Revit API via MCP (Model Context Protocol). It can create elements, delete elements, modify parameters in bulk, manage sheets, and alter rooms — all from a plain-language prompt. **There is no built-in admin layer to restrict which operations are allowed per user role.**

BlockRevitAI intercepts AI-driven model changes and lets your team decide what stays and what gets undone.

> ⚠️ **Experimental** — This is a community research project, not an official product. Use at your own risk.

## What It Does

### 🔒 Panel Blocker (`command-before-exec`)
Blocks the Autodesk Assistant panel from opening unless the user provides a BIM Manager password or is on an authorized user list. Zero performance overhead — fires only on button click.

### 🔍 AI Transaction Monitor (`ai-fired` hook)
When the Assistant commits a model-modifying transaction, a confirmation dialog appears summarizing exactly what changed: element counts, categories affected, and the MCP tool that triggered it. The user can **Accept** or **Reject** (auto-undo).

This hook fires *only* on confirmed AI transactions — not on manual edits. Detection is based on MCP tool transaction name fingerprinting extracted from Revit 2027 journal file analysis.

### ⚡ How Detection Works

The Autodesk Assistant operates via `IExternalEventHandler` and creates standard Revit transactions. Every MCP tool invocation is logged in the journal with a structured block:

```
'Add-in component: MCPToolExecution
'Rvt.Attr.AddInId: f0da0f43-cd76-4945-968b-4c4e0a769298
'Rvt.Attr.AddInName: AIAssistant UI extension
'Rvt.Attr.ToolName: batchModifyParameter
```

The Assistant converts camelCase MCP tool names to Title Case transaction names (e.g., `batchModifyParameter` → `"Batch Modify Parameter"`). BlockRevitAI matches against these patterns in a single dictionary lookup per committed transaction.

## Assistant Identity (Revit 2027)

| Attribute | Value |
|-----------|-------|
| **AddInId (GUID)** | `f0da0f43-cd76-4945-968b-4c4e0a769298` |
| **AddInName** | AIAssistant UI extension |
| **Command ID** | `ID_TOGGLE_AUTODESK_ASSISTANT` |
| **Pane GUID** | `3e852507-4f81-4234-b0d8-15c61ca8a261` |
| **Assembly** | `Autodesk.Assistant.Application.dll` |
| **MCP Protocol** | `ModelContextProtocol.dll` v0.5.0 |
| **.NET Runtime** | 10.0.5 |

## Installation

1. Download or clone this repo
2. Copy the `AIBlock.extension` folder into your pyRevit extensions directory
3. Reload pyRevit (`pyRevit → Reload`)
4. The **AIBlock** tab appears in the Revit ribbon

```
# Typical pyRevit extensions path:
%APPDATA%\pyRevit\Extensions\
```

## Extension Structure

```
AIBlock.extension/
  hooks/
    doc-changed.py                                          # Bridge: thin filter, exits immediately for non-AI transactions
    ai-fired.py                                             # Confirmation dialog with Accept/Reject (auto-undo)
    command-before-exec[ID_TOGGLE_AUTODESK_ASSISTANT].py    # Panel blocker with password gate
  lib/
    aiblock/
      __init__.py               # Config, auth, password hashing, logging
      mcp_patterns.py           # MCP transaction fingerprint dictionary
  AIBlock.tab/
    AIGuard.panel/
      ToggleGuard.smartbutton/  # Enable/disable the guard (dynamic title)
      Settings.pushbutton/      # Manage authorized users, password, log path
```

## Configuration

Settings are stored at `%APPDATA%\AIBlock\config.json`.

Use the **Settings** button in the ribbon, or edit the JSON directly:

```json
{
  "password_hash": "sha256-hash-of-password",
  "authorized_users": ["jsmith", "mjones"],
  "guard_enabled": true,
  "log_path": "X:\\BIM\\Logs\\ai_guard_log.csv",
  "block_public_mcp": true
}
```

Default override password: `AIBlock2026` (change immediately via Settings).

## Adding New MCP Tool Patterns

As Autodesk expands the Assistant's capabilities, new MCP tool names will appear. To capture them:

1. Use the Assistant to perform the new operation
2. Open the Revit journal file (`%LOCALAPPDATA%\Autodesk\Revit\Autodesk Revit 2027\Journals\`)
3. Search for `MCPToolExecution` — the `Rvt.Attr.ToolName` field contains the tool name
4. Add the Title Case transaction name to `CONFIRMED_TOOLS` in `lib/aiblock/mcp_patterns.py`

## Known Limitations

- **pyRevit .NET 10 compatibility**: pyRevit hooks may have issues on Revit 2027's .NET 10 runtime. Test before deploying to production. If hooks don't fire, the fallback is removing the Assistant's `.addin` manifest at `C:\Program Files\Autodesk\Revit 2027\AddIns\Assistant\Autodesk.Assistant.Application.addin`.
- **Post-commit undo**: The `ai-fired` hook shows the confirmation dialog *after* the transaction commits. On reject, it posts an Undo command. The transaction briefly exists before being undone. In workshared models, do not sync between the AI edit and the undo.
- **Public MCP Server**: The optional Public MCP Server add-on (for external AI tools like Claude Desktop) uses a separate `.addin` and command ID. It is not blocked by default.

## Contributing

This is an open-source tool for the AEC community. If you capture new MCP tool names, transaction patterns, or find compatibility fixes for pyRevit on .NET 10, please open a PR.

## License

MIT License — see [LICENSE](LICENSE).

## Credits

Created by [Tay Othman](https://github.com/tay0thman).

Journal analysis methodology and MCP fingerprinting based on empirical Revit 2027 journal file inspection — no reverse engineering or decompilation involved.
