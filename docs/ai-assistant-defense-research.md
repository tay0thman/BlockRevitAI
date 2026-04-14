# Defending the Model: Detecting & Controlling Autodesk Assistant Activity in Revit 2027

## Research Document
**Date:** April 8, 2026

---

## 1. The Problem

Revit 2027 ships with the **Autodesk Assistant** — a built-in LLM connected directly to the Revit API via MCP (Model Context Protocol). It can query elements, read/write parameters, create objects, modify properties, and execute multi-step operations from plain-language prompts.

**The risk to design and BIM managers is real:**

- Any user can issue natural-language commands that result in bulk model edits without going through standard QA gates.
- There is no built-in admin/permission layer to restrict which assistant operations are allowed per user role.
- In a workshared environment, unreviewed AI-driven edits can propagate to the central model via Sync.

---

## 2. How the Assistant Operates (API-Level)

1. The Assistant is a first-class panel inside Revit 2027 (View → User Interface → Autodesk Assistant).
2. It connects to Revit's API directly via MCP tool groups: model queries, sheet management, room management, schedules, exports, and element operations.
3. Every model modification creates a `Transaction` that appears in the Undo menu.
4. The Assistant runs on MCP architecture. Autodesk also publishes a Public MCP Server add-on for external AI tools.

---

## 3. Detection Strategies

### Strategy A: pyRevit `doc-changed` Hook
Fires after `DocumentChanged`. Inspects `GetTransactionNames()` against known MCP patterns. Read-only — logging and alerting only.

### Strategy B: `IUpdater` / Dynamic Model Update
Fires inside the active transaction. Can stamp parameters or throw to roll back. Cannot access transaction name.

### Strategy C: `command-before-exec` Hook
Intercepts the `ID_TOGGLE_AUTODESK_ASSISTANT` button click. Can cancel before the panel opens. Zero overhead.

---

## 4. Recommended Architecture

```
┌─────────────────────────────────────────────────────┐
│  command-before-exec[ID_TOGGLE_AUTODESK_ASSISTANT]   │
│  Block panel access with password/user auth gate     │
└──────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  doc-changed.py (bridge)                             │
│  One dict lookup per transaction → exit or proceed   │
└──────────────────────┬──────────────────────────────┘
                       │ MCP transaction detected
┌──────────────────────▼──────────────────────────────┐
│  ai-fired.py                                         │
│  Confirmation dialog: Accept or Reject (auto-undo)   │
└─────────────────────────────────────────────────────┘
```

---

## 5. Confirmed Fingerprints (from Journal Analysis)

| Field | Value |
|-------|-------|
| AddInId | `f0da0f43-cd76-4945-968b-4c4e0a769298` |
| Journal Tag | `MCPToolExecution` |
| Transaction Naming | camelCase → Title Case |
| Confirmed Tool | `batchModifyParameter` → `"Batch Modify Parameter"` |
| Execution Model | `IExternalEventHandler` on idle loop |
| .NET Runtime | 10.0.5 |

---

## 6. Alternative: Remove the `.addin` Manifest

For firms that want a complete lockout without any code, rename or delete:

```
C:\Program Files\Autodesk\Revit 2027\AddIns\Assistant\Autodesk.Assistant.Application.addin
```

This prevents the Assistant from loading entirely. A PowerShell script during Revit deployment handles it.

---

## 7. Policy Recommendations

- Do not upgrade production projects to Revit 2027 until AI guard tooling is tested.
- Do not install the Public MCP Server add-on on production workstations without IT review.
- Educate staff that the Assistant's edits are real transactions that sync to central.
- Every Assistant operation is undoable (Ctrl+Z), but once synced, undo is no longer simple.
