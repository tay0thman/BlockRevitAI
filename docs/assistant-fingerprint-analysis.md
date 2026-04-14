# Autodesk Assistant Fingerprint — Journal Analysis

## Extracted from: journal_0021.txt + journal_0021_worker1.log
**Date:** April 8, 2026

---

## 1. Assistant Add-In Identity (CONFIRMED)

```
AddInId (GUID):    f0da0f43-cd76-4945-968b-4c4e0a769298
AddInName:         AIAssistant UI extension
Class:             Autodesk.Assistant.Application.Main
VendorId:          ADSK
Assembly:          Autodesk.Assistant.Application.dll (v27.0.10.13)
Context:           AUTODESKASSISTANT
```

### Supporting Assemblies

| Assembly | Version | Purpose |
|----------|---------|---------|
| `Autodesk.Assistant.Application.dll` | 27.0.10.0 | Main application |
| `Autodesk.Assistant.ServerRegistry.dll` | 27.0.10.0 | MCP server registration |
| `Autodesk.Assistant.Tools.dll` | 27.0.10.0 | MCP tool implementations |
| `ModelContextProtocol.dll` | 0.5.0 | MCP protocol layer |
| `ModelContextProtocol.Core.dll` | 0.5.0 | MCP core library |
| `Microsoft.Extensions.AI.Abstractions.dll` | 10.0.0 | .NET 10 AI abstractions |

### Registered Events
- `ThemeChanged`
- `DockableFrameVisibilityChanged`
- `ViewActivated`

---

## 2. Panel Identity

```
Command ID:     ID_TOGGLE_AUTODESK_ASSISTANT
Pane GUID:      3e852507-4f81-4234-b0d8-15c61ca8a261
Pane Title:     Autodesk Assistant
Component:      Rvt.AIAssistant
Event Types:    PaneOpened, PaneClosed, TimeOfPaneBeingOpened
```

---

## 3. MCP Tool Execution Pattern

Every MCP tool invocation produces this journal block:

```
'C <timestamp>;   0:< Starting MCP tool: '<toolName>'
... [transaction data if model-modifying] ...
'C <timestamp>;   0:< MCP tool: '<toolName>' finished successfully. Execution time: <N> milliseconds.
'Add-in component: MCPToolExecution
'Rvt.Attr.AddInId: f0da0f43-cd76-4945-968b-4c4e0a769298
'Rvt.Attr.AddInName: AIAssistant UI extension
'Rvt.Attr.CommandVendorId: ADSK
'Rvt.Attr.ExecutionTimeMs: <N>
'Rvt.Attr.Success: True
'Rvt.Attr.ToolName: <toolName>
```

**Key identifier: `'Add-in component: MCPToolExecution'`**

### Observed MCP Tool Calls

#### `queryModel` (READ-ONLY — no transaction)
```
Execution Time: 18 ms
Transaction:    NONE
```

#### `batchModifyParameter` (MODEL-MODIFYING)
```
Execution Time: 42 ms
Transaction:    "Batch Modify Parameter"
```

---

## 4. Transaction Name Pattern

| MCP Tool Name (camelCase) | Transaction Name (Title Case) |
|---------------------------|-------------------------------|
| `batchModifyParameter` | `"Batch Modify Parameter"` |

**Pattern:** camelCase → Title Case with spaces.

---

## 5. Timing Analysis

```
09:04:18.153  — Last user interaction
09:04:31.526  — queryModel starts (13s gap — AI processing)
09:04:31.543  — queryModel ends (18ms)
09:04:36.228  — batchModifyParameter starts (4.7s — AI planning)
09:04:36.268  — Transaction committed (40ms)
09:04:36.269  — batchModifyParameter ends (42ms total)
09:04:44.997  — Next user interaction
```

The Assistant operates via `IExternalEventHandler` on the idle loop.

---

## 6. .NET Runtime

```
dotNetInstalledVersionString: 10.0.5
```
