# -*- coding: utf-8 -*-
# Author: Tay Othman
"""AIBlock runtime state.

Holds the one-shot pass grant consumed by the IUpdater, and a queue
of pending decisions for the Idling-driven confirmation dialog.

All access is serialised through a single lock. The updater runs on
Revit's UI thread during transaction commit; pyRevit buttons and
hooks may run on other threads. Keep operations short.

The legacy arm()/disarm()/is_armed() API was removed in the three-mode
refactor — the IUpdater consults aiblock.should_block_ai_writes()
directly now, so the "armed" concept no longer lives in process-local
state. Config is the single source of truth.
"""
import threading
from collections import deque

_lock = threading.Lock()

_one_pass = False
_pending = deque()


def grant_one_pass():
    """Allow exactly one upcoming transaction to bypass the rollback.

    Only meaningful in MODE_USER_CONTROLLED — the updater gates the
    consume side behind get_mode() == MODE_USER_CONTROLLED so a stale
    grant from a prior Mode-3 session can't leak after the BIM
    Management Team swaps to Mode 1 or 2.
    """
    global _one_pass
    with _lock:
        _one_pass = True


def consume_one_pass():
    """Atomically return and clear the one-pass flag.

    Called by the updater. Returns True if a pass was granted, False
    otherwise.
    """
    global _one_pass
    with _lock:
        if _one_pass:
            _one_pass = False
            return True
        return False


def has_one_pass():
    """Read the one-pass flag without consuming it (for Diagnostics)."""
    with _lock:
        return _one_pass


def enqueue_decision(record):
    """Record a rolled-back AI transaction for the Idling handler to
    surface as a confirmation dialog."""
    with _lock:
        _pending.append(record)


def drain_decisions():
    """Pop every pending decision. Called from the Idling handler."""
    with _lock:
        items = list(_pending)
        _pending.clear()
        return items


def has_pending():
    """Read pending-queue depth without draining it (for Diagnostics)."""
    with _lock:
        return len(_pending) > 0
