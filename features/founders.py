# features/founders.py - Independent Founders lootbox claimer
"""Detect and click Founders lootboxes on an independent schedule.

Uses the shared ingame action lock, but no Lootbug runtime state or settings.
The Founders template is clicked once; no popup handling is needed.
"""
import threading
import time

import config.app_state as state
import config.settings as s
from core.file_logger import bot_log
from core.screen_cache import get_screen, get_cached_screen
from core.vision import find_template
from core.tapper import tap
from core.game_state import is_game_running


_thread = None
_thread_started = False
_stop_evt = threading.Event()
_wake_evt = threading.Event()   # set to make the worker run a cycle ASAP


def _log(msg: str, level_attr: str = "FOUNDERS_LOG_LEVEL"):
    level = getattr(s, level_attr, "FULL")
    bot_log(msg, level)


def _get_screen_for_scan():
    """Reuse the shared game screenshot if fresh, else pull our own."""
    shared_slot = "game_scr"
    own_slot = "founders_scr"
    max_age = float(getattr(s, "FOUNDERS_SCREEN_REUSE_AGE_S", 5.0))

    img, _, _ = get_cached_screen(shared_slot, max_age=max_age)
    if img is not None:
        return img
    img, _, _ = get_screen(own_slot, max_age=0.0, force=True)
    return img


def _click(cx: int, cy: int, what: str):
    j = int(getattr(s, "FOUNDERS_TAP_JITTER_PX", 4))
    _log(f"[FOUNDERS] tap {what} at ({cx},{cy}) jitter=+/-{j}px",
         "FOUNDERS_LOG_LEVEL_CLICK")
    ok = tap(cx, cy, jitter=j)
    if not ok:
        _log(f"[FOUNDERS] tap failed: {what} at ({cx},{cy})", "FOUNDERS_LOG_LEVEL_CLICK")
    return ok


def _run_scan_cycle() -> bool:
    """Check for the founders lootbox and tap it if present. Returns True if clicked."""
    img = _get_screen_for_scan()
    if img is None:
        _log("[FOUNDERS] no screenshot -> skipping cycle")
        return False
    thr = float(s.FOUNDERS_MATCH_THRESHOLD)
    roi = tuple(getattr(s, "FOUNDERS_DETECT_ROI", (110, 201, 753, 1021)))
    tpl = getattr(s, "FOUNDERS_TEMPLATE", "Founders/founders_bundle_tpl.png")
    m = find_template(img, tpl, roi=roi, threshold=thr)
    if not m["found"]:
        _log(f"[FOUNDERS] founders: not present (score={m['score']:.3f})",
             "FOUNDERS_LOG_LEVEL")
        return False

    _log(f"[FOUNDERS] founders lootbox detected (score={m['score']:.3f}) -> clicking",
         "FOUNDERS_LOG_LEVEL")
    if not _click(m["cx"], m["cy"], "founders-lootbox"):
        return False
    state.founders_clicked_count += 1
    state.founders_last_click_ts = time.time()

    return True


def _try_run_with_lock() -> str:
    """Acquire the action lock and run a cycle.
    Returns: "ok" | "busy" | "no_game"
    """
    if not is_game_running():
        _log("[FOUNDERS] game not running -> skipping tick")
        return "no_game"

    lock = getattr(state, "ingame_action_lock", None)
    if lock is None:
        # No lock available — just run.
        _run_scan_cycle()
        return "ok"

    if not lock.acquire(blocking=False):
        _log("[FOUNDERS] another feature is busy -> postponing",
             "FOUNDERS_LOG_LEVEL_BUSY")
        return "busy"
    try:
        _run_scan_cycle()
    finally:
        lock.release()
    return "ok"


def _worker():
    _log("[FOUNDERS] worker thread started")
    _sleep_interruptible(3.0)
    while not _stop_evt.is_set():
        try:
            interval = float(getattr(s, "FOUNDERS_CHECK_INTERVAL_S", 180.0))
            busy_retry = float(getattr(s, "FOUNDERS_BUSY_RETRY_S", 15.0))

            if not getattr(state, "founders_enabled", False):
                state.founders_next_check_ts = 0.0
                # Use interruptible sleep so a toggle-ON wake doesn't get
                # buffered and trigger an extra cycle after the first run.
                _sleep_interruptible(min(5.0, interval))
                continue

            result = _try_run_with_lock()
            if result == "busy":
                wait = min(busy_retry, interval)
            elif result == "no_game":
                wait = min(30.0, interval)
            else:
                wait = interval

            state.founders_next_check_ts = time.time() + wait
            _sleep_interruptible(wait)
        except Exception as e:
            _log(f"[FOUNDERS] worker error: {type(e).__name__}: {e}")
            time.sleep(5.0)


def _sleep_interruptible(seconds: float):
    if _wake_evt.wait(timeout=seconds):
        _wake_evt.clear()


def start():
    """Start the background worker (idempotent)."""
    global _thread, _thread_started
    if _thread_started:
        return
    _thread_started = True
    _stop_evt.clear()
    _thread = threading.Thread(target=_worker, daemon=True, name="founders-worker")
    _thread.start()


def toggle() -> bool:
    """Toggle Founders independently and wake the worker when enabled."""
    state.founders_enabled = not state.founders_enabled
    state.founders_next_check_ts = 0.0
    if state.founders_enabled:
        _wake_evt.set()
    _log(f"[FOUNDERS] toggled -> {'ON' if state.founders_enabled else 'OFF'}")
    return state.founders_enabled
