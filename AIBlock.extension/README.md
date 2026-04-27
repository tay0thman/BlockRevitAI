# AIBlock

pyRevit extension that gives BIM Managers administrative control over
the Autodesk Assistant AI introduced in Revit 2027.

AIBlock sits between the Assistant and the model. Depending on the
mode the BIM Management Team picks, it blocks the Assistant panel
from opening at all, lets the panel open but silently rolls back any
AI-originated transaction that mutates the model, or leaves AI fully
open and exposes a password-gated toggle so users can opt into
protection per-session.

Current version: see `__version__` in `lib/aiblock/__init__.py`
(surfaced in Diagnostics and Settings → View Config).

---

## Requirements

- Autodesk Revit 2027 or later. Earlier Revit versions don't have the
  Autodesk Assistant panel, so the extension exits silently on load.
- pyRevit (any recent 4.8+ / 5.x build — tested against the C# Roslyn
  loader and the legacy IronPython loader).
- Windows. The config file locations and username resolution assume
  Windows environment variables (`APPDATA`, `TEMP`, `USERNAME`).

## Install

1. Copy the `AIBlock.extension` folder into your pyRevit extensions
   directory, or add its parent path in pyRevit → Settings →
   Custom Extensions Directories.
2. Reload pyRevit. You should see an **AI Guard** panel on the
   **pyRevit** tab with two ribbon buttons (AI Guard, Guard Settings)
   and a slanted-arrow slideout at the bottom right for Diagnostics.
3. Open **Guard Settings**, authenticate with the default password
   `AIBlock2026`, and rotate it to something firm-specific. The
   extension will nag on first use.

---

## Policy modes

The three enforcement modes are the heart of AIBlock. They're set by
the BIM Management Team from **Guard Settings → Change Mode** (or
pushed firm-wide via network config; see below).

| Mode | ID | Assistant panel | AI writes | User override |
|------|-----|---------------|-----------|---------------|
| Block all AI | `block_all` | Cannot open | Blocked | None |
| Block AI writes | `block_writes` | Opens (queries / reports only) | Rolled back silently | None |
| User-controlled | `user_controlled` | Opens | Rolled back ONLY when AI Guard button is GUARDED | Password-gated toggle |

The default on a fresh install is `block_writes` — the safer-by-default
choice. Teams can use the Assistant for queries and reports immediately
while any unreviewed model mutation is rolled back atomically.

In `block_all` and `block_writes` the per-user AI Guard button is
read-only. Clicking it shows a "contact your BIM Manager" dialog.

### Ribbon button labels

The **AI Guard** button reflects the active policy:

- `AI Guard / BLOCKED` — Mode 1 (block_all)
- `AI Guard / READ-ONLY` — Mode 2 (block_writes)
- `AI Guard / GUARDED` — Mode 3 with per-session guard ON (AI writes rolled back)
- `AI Guard / OPEN` — Mode 3 with per-session guard OFF (AI fully open)

---

## Configuration

Config priority (highest wins):

1. **Network config** — `AIBLOCK_NETWORK_CONFIG` env var pointing at
   a UNC path, e.g. `\\server\share\BIM\AIBlock\config.json`
2. **Local config** — `%APPDATA%\AIBlock\config.json`
3. **Hardcoded defaults** — see `_DEFAULT_CONFIG` in `lib/aiblock/__init__.py`

When a network config is set and reachable, it wins for every field
it defines. `authorized_users` is the exception — network + local
lists are merged so firm-wide users can coexist with per-machine
exceptions. If the network path is unreachable, local config is used
as a fallback (extension stays functional, just not centrally managed).

### Fields

| Field | Default | Notes |
|-------|---------|-------|
| `mode` | `"block_writes"` | One of `block_all`, `block_writes`, `user_controlled` |
| `password_hash` | SHA-256 of `AIBlock2026` | Rotate via Settings → Change Password |
| `authorized_users` | `[]` | Windows usernames that bypass the password prompt in Mode 3 |
| `guard_enabled` | `true` | Per-session toggle; meaningful ONLY in `user_controlled` |
| `log_path` | `""` | Shared audit log (UNC or local). Empty = disabled |
| `block_public_mcp` | `true` | Reserved for the Public MCP Server add-on; not currently wired |
| `verbose_trace` | `true` | Writes per-transaction trace to `%TEMP%\aiblock_trace.log`. Flip to `false` once field confidence is high |

### Pushing policy firm-wide via network config

Put a `config.json` on a share that every workstation can read, then
set `AIBLOCK_NETWORK_CONFIG` on every machine via GPO, SCCM, or
Intune:

```
setx AIBLOCK_NETWORK_CONFIG "\\fileserver\BIM\AIBlock\config.json" /M
```

Example centrally-pushed config:

```json
{
  "mode": "block_writes",
  "password_hash": "<sha256 of your firm password>",
  "authorized_users": ["jsmith", "mtaylor"],
  "log_path": "\\\\fileserver\\BIM\\AIBlock\\audit.jsonl",
  "verbose_trace": false
}
```

Any local changes the user (or their Settings button) writes will be
shadowed by the network values at read time. The local file is still
kept as a fallback in case the share is unreachable.

### Password

The password is a speed-bump against accidental toggles, not a hard
security boundary — someone determined to run AI can always uninstall
pyRevit. What the password buys is:

- Mode changes, password rotation, and log path edits are deliberate
  actions rather than accidental clicks.
- The audit log records who authenticated and when.

Rotate it on every install. The default `AIBlock2026` is public in
`lib/aiblock/__init__.py`, so if it's left alone the ribbon button
is effectively un-protected.

---

## Using AIBlock

### AI Guard button (ribbon)

- In Modes 1 and 2, the caption shows the locked policy. Clicking
  opens a "contact your BIM Manager" dialog.
- In Mode 3, clicking toggles `guard_enabled`. The first non-authorized
  user each session is prompted for the password.

### Guard Settings (ribbon)

Password-gated. Actions:

- **Change Mode** — swap between the three policy modes with a
  confirmation dialog showing the old and new label + description.
- **Manage Authorized Users** — add / remove Windows usernames that
  bypass the password prompt for the toggle (Mode 3 only).
- **Change Password** — rotate the stored SHA-256 hash.
- **Set Log Path** — point the audit log at a UNC or local path.
- **Test Log Paths** — write a canary event and verify the file
  actually grew. Catches misconfigured UNCs (which otherwise silently
  swallow audit writes, because `log_event()` is best-effort).
- **View Current Config** — renders the active configuration,
  including config source, network-managed flag, and a default-password
  notice.

### Diagnostics (panel slideout)

Slanted-arrow button at the bottom-right of the AI Guard panel. No
password required (read-only). Shows:

- AIBlock version + host Revit version.
- Active AddIn GUID and updater registration status.
- The three-mode policy state and the effective `should_block_ai_panel()` /
  `should_block_ai_writes()` predicates.
- Per-session user toggle and whether it's active or ignored.
- Config source and network-managed flag.
- Runtime state (one-pass grants, pending decisions).

Use this first whenever something looks off.

---

## Audit logs

Events AIBlock logs (when `log_path` is set):

| Event | Meaning |
|-------|---------|
| `MODE_CHANGED` | BIM Manager changed the policy mode |
| `TOGGLE_CHANGED` | User flipped the AI Guard button (Mode 3) |
| `TOGGLE_DENIED_BAD_PWD` | Failed password on toggle attempt |
| `TOGGLE_BLOCKED_BY_MODE` | Toggle attempted in Mode 1 or 2 (read-only state) |
| `ASSISTANT_ALLOWED` | Autodesk Assistant panel opened |
| `ASSISTANT_BLOCKED` | Autodesk Assistant panel cancelled |
| `AI_BLOCKED` | AI-originated transaction rolled back by updater |
| `AI_ALLOW_NEXT` | User granted a one-pass bypass (Mode 3 only) |
| `AI_PASSTHROUGH` | One-pass bypass was consumed on the next AI commit |
| `AI_UPDATER_BYPASS` | Post-commit safety net: AI transaction committed despite `should_block_ai_writes() == True`. Investigate |
| `AI_COMMITTED_ALLOWED` | Post-commit: AI transaction committed under a mode that allows it |
| `DEFAULT_PASSWORD_NAG` | Settings showed the default-password nag (accepted=True\|False) |
| `LOG_PATH_CANARY` | Written by Settings → Test Log Paths |

Log format is **JSONL** — one JSON object per line, UTF-8, UTC
timestamps. Each line carries the full session envelope so lines are
self-describing and you never need to join against a separate
"session metadata" stream to make sense of one:

```json
{"ts":"2026-04-22T14:03:27.118Z","event":"AI_BLOCKED","user":"jsmith","host":"WS-ARCH-042","revit_version":"2027","aiblock_version":"1.0.0-rc1","session_id":"a1b2c3d4","mode":"block_writes","details":"doc=Tower.rvt markers=Autodesk.Assistant"}
```

| Field | Notes |
|-------|-------|
| `ts` | UTC ISO 8601 with trailing `Z`. Always UTC — cross-office deployments collapse to one sortable timeline. |
| `event` | Event type (see table above) |
| `user` | Short Windows username (domain prefix stripped by callers) |
| `host` | Machine hostname, resolved at Revit startup |
| `revit_version` | Revit major version (e.g. `2027`) |
| `aiblock_version` | Extension build — bump indicates a behavioural change |
| `session_id` | 8-hex per-Revit-session id. Lines with the same id came from the same process and can be joined to the local `%TEMP%\aiblock_trace.log` |
| `mode` | Enforcement mode at the time of the event |
| `details` | Free-form string or nested JSON object — caller's payload |

The recommended file extension is `.jsonl`, e.g.
`\\fileserver\BIM\AIBlock\audit.jsonl`. `.log` also works. `.csv` is
accepted (lines will append) but you'll end up mixing old CSV with
new JSON; rename to `.jsonl` during the rc1 → GA transition.

**Grep examples** (`jq` or PowerShell's `ConvertFrom-Json` work too):

```powershell
# All bypasses this week
Get-Content audit.jsonl | Where-Object { $_ -match '"AI_UPDATER_BYPASS"' }

# Timeline for one incident, by session id
Select-String 'a1b2c3d4' audit.jsonl
```

The verbose trace file at `%TEMP%\aiblock_trace.log` is separate —
it's a developer-facing per-transaction trace, not an audit log.
It's plain text (one line per event) and **rotates at 5 MiB**: the
active file is renamed to `aiblock_trace.log.1` and a fresh file
starts. Only two files ever exist, so local disk stays bounded at
roughly 10 MiB worst case regardless of session length. Every trace
line is stamped with the same `sid=` session id that appears in the
JSONL audit record, so you can pivot from one to the other with a
single `Select-String`.

---

## Troubleshooting

### The updater doesn't seem to fire

Open **Diagnostics**. If `IUpdater registered` is `NO`, the updater
registration was silently dropped by Revit — usually because the
AddInId on the UpdaterId didn't match the AddIn currently driving
the call. pyRevit extensions must use pyRevit's own loader AddInId,
which `updater.py` resolves dynamically via
`UIApplication.ActiveAddInId`. If the fallback GUID is wrong, the
registration drops.

Check the Revit journal for:
```
DBG_WARN: Trying to modify an updater that doesn't belong to the currently active AddIn
```

### Native "Error - cannot be ignored" dialog appears

The FailureDefinition must be registered with `FailureSeverity.Warning`
(not Error), because Revit 2027 shows a non-suppressible modal for
unresolved Errors. If a prior session registered the definition with
Error severity, **you must fully restart Revit** — not just reload
pyRevit. FailureDefinition registrations are session-scoped and
cannot be replaced with a different severity under the same GUID.

### Audit log isn't being written

Run **Settings → Test Log Paths**. It writes a canary event and
checks whether the file grew. If the canary fails, likely causes:

- UNC unreachable (VPN / share offline)
- User lacks write permission
- Parent directory does not exist
- Antivirus / DLP blocking the write

`log_event()` swallows all I/O errors by design so a flaky share
never breaks Revit — that's exactly the behaviour that hides the
failure without this check.

### Trace file is huge

The active trace file is capped at 5 MiB and self-rotates to
`aiblock_trace.log.1` (replacing any previous `.1`). Only two files
exist, total ~10 MiB worst case. If that's still too much local
churn, set `verbose_trace: false` in config and reload pyRevit. For
a GA release, also flip `_TRACE_HARD_KILL = True` in
`lib/aiblock/updater.py` to compile the trace out entirely.

### Ribbon caption didn't update after mode change

The `__selfinit__` hook that paints the button runs once per pyRevit
load. Changing the mode only updates config — reload pyRevit to see
the new caption.

---

## Architecture in 60 seconds

1. **Hook: command-before-exec[ID_TOGGLE_AUTODESK_ASSISTANT].py** —
   fires when a user clicks the Autodesk Assistant toggle. Cancels
   the click in Mode 1. Gates it behind the password in Mode 3 for
   non-authorized users. Passes through in Mode 2 (the panel is
   allowed to open; writes are caught downstream).
2. **IUpdater: lib/aiblock/updater.py** — registered at
   ApplicationInitialized via `startup.py`. Fires during every
   transaction commit. When the managed stack carries an
   `Autodesk.Assistant` or `ModelContextProtocol` assembly marker
   AND `should_block_ai_writes()` returns True, the updater posts
   a Warning-severity FailureMessage. Revit's failure processor
   then runs the FailuresProcessing subscriber (also in updater.py),
   which deletes the warning and returns `ProceedWithRollBack`.
   The transaction is rolled back atomically; the undo stack is
   untouched.
3. **Idling subscriber** — on the next idle tick, the Idling handler
   drains any pending decision records and shows a branded AIBlock
   dialog. In Mode 3 the dialog offers "Allow next" (grants a
   one-pass bypass). In Modes 1 and 2 the dialog is informational
   only — there is no per-user override.
4. **Shutdown hook: hooks/app-closing.py** — unregisters the updater,
   the Idling subscriber, and the FailuresProcessing subscriber on
   Revit close so state is clean for the next session.

---

## Known limitations

- The AI-origin detection walks the managed stack for assembly
  markers. If Autodesk renames its Assistant assembly or ships a new
  MCP tool with a different assembly name, detection will miss the
  origin and the updater will pass the transaction through. The
  safety-net hook in `hooks/doc-changed.py` logs
  `AI_UPDATER_BYPASS` in this case — check it after any Revit
  update.
- Config reads on every trace call are cached at module load. Runtime
  config changes (via Settings) don't take effect on existing module
  instances; reload pyRevit.
- The audit log is append-only JSONL. AIBlock does **not** rotate it —
  rotation at the share level (weekly/monthly) is your IT team's call.
  The local verbose trace at `%TEMP%\aiblock_trace.log` **does**
  self-rotate at 5 MiB.
- Password hashing is unsalted SHA-256. This is intentional — the
  password is a speed-bump, not a security control — but don't
  reuse a real password as your AIBlock password.

---

## File layout

```
AIBlock.extension/
├── README.md                          (this file)
├── extension.json                     (pyRevit metadata)
├── startup.py                         (register updater at load)
├── hooks/
│   ├── app-closing.py                 (clean teardown on Revit close)
│   ├── command-before-exec[ID_TOGGLE_AUTODESK_ASSISTANT].py
│   └── doc-changed.py                 (post-commit safety-net logger)
├── lib/aiblock/
│   ├── __init__.py                    (config + mode helpers)
│   ├── state.py                       (one-pass + pending queues)
│   ├── updater.py                     (IUpdater + FailuresProcessing)
│   └── mcp_patterns.py                (transaction-name dictionary)
└── pyRevit.tab/AIGuard.panel/
    ├── bundle.yaml                    (panel layout)
    ├── AIGuard.stack/
    │   ├── Settings.pushbutton/       (BIM Manager UI)
    │   └── ToggleGuard.smartbutton/   (AI Guard ribbon button)
    └── Diagnostics.panelbutton/       (panel slideout)
```

---

## Support

Internal to Boulder Associates. Tay Othman owns the extension.
