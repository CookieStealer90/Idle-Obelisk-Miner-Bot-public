# features/founders.py - Independent Founders lootbox claimer
"""Detect and click Founders lootboxes on an independent schedule.

Uses the shared ingame action lock, but no Lootbug runtime state or settings.
Each detected Founders bundle is clicked once, then a fresh frame is checked
for another bundle. Claim chains are bounded; no popup handling is needed.
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
_activation_generation = 0
_detected_generation = None


def _check_interval() -> float:
    if _detected_generation == _activation_generation:
        return float(s.FOUNDERS_CHECK_INTERVAL_S_SLOW)
    return float(s.FOUNDERS_CHECK_INTERVAL_S_FIRST)


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


def _find_bundle(force_fresh=False):
    if force_fresh:
        img, _, _ = get_screen("founders_scr", max_age=0.0, force=True)
    else:
        img = _get_screen_for_scan()
    if img is None:
        _log("[FOUNDERS] no screenshot -> skipping cycle")
        return None
    return find_template(img, getattr(s, "FOUNDERS_TEMPLATE", "Founders/founders_bundle_tpl.png"),
                         roi=tuple(getattr(s, "FOUNDERS_DETECT_ROI", (110, 201, 753, 1021))),
                         threshold=float(s.FOUNDERS_MATCH_THRESHOLD))


def _run_scan_cycle(match=None, cancelled=lambda: False) -> bool:
    """Check for the founders lootbox and tap it if present. Returns True if clicked."""
    global _detected_generation
    generation = _activation_generation
    m = _find_bundle() if match is None else match
    if cancelled():
        return False
    if m is None:
        return False
    if not m["found"]:
        _log(f"[FOUNDERS] founders: not present (score={m['score']:.3f})",
             "FOUNDERS_LOG_LEVEL")
        if generation == _activation_generation and _detected_generation == generation:
            _detected_generation = None
            _log(f"[FOUNDERS] no bundle detected -> mode=FIRST "
                 f"(fast checks, interval={_check_interval():g}s)")
        return False

    # A scan started before reactivation must not switch the new session to slow mode.
    first_detection = _detected_generation != generation
    _detected_generation = generation
    if first_detection and generation == _activation_generation:
        _log(f"[FOUNDERS] first bundle detected -> mode=SLOW "
             f"(interval={_check_interval():g}s)")
    _log(f"[FOUNDERS] founders lootbox detected (score={m['score']:.3f}) -> clicking",
         "FOUNDERS_LOG_LEVEL")
    if generation == _activation_generation:
        state.founders_followup_pending = True
    if not _click(m["cx"], m["cy"], "founders-lootbox"):
        _log("[FOUNDERS] detected bundle tap failed -> short retry")
        return False
    state.founders_clicked_count += 1
    state.founders_last_click_ts = time.time()

    return True


def _run_claim_chain(manual=False, cancelled=lambda: False):
    """Caller owns the action lock; every sent tap gets a fresh follow-up scan."""
    state.founders_followup_pending = False
    generation = _activation_generation
    limit = int(getattr(s, "FOUNDERS_MAX_CLAIMS_PER_CYCLE", 3))
    match = _find_bundle(force_fresh=True) if manual else None
    if manual and match is None:
        return
    for claimed in range(limit):
        if ((not manual and not state.founders_enabled) or cancelled()
                or _stop_evt.is_set() or generation != _activation_generation):
            return
        if not _run_scan_cycle(match, cancelled=lambda: (
                cancelled() or _stop_evt.is_set() or generation != _activation_generation
                or (not manual and not state.founders_enabled))):
            return
        _log(f"[FOUNDERS] tap sent ({claimed + 1}/{limit}) -> checking fresh screen for another bundle")
        match = _find_bundle(force_fresh=True)
        if ((not manual and not state.founders_enabled) or cancelled()
                or generation != _activation_generation or _stop_evt.is_set()):
            return
        if match is None:
            state.founders_followup_pending = True
            _log("[FOUNDERS] follow-up screenshot unavailable -> short retry")
            return
        if not match["found"]:
            state.founders_followup_pending = False
            _log("[FOUNDERS] fresh recheck: no further bundle")
            return
    state.founders_followup_pending = True
    _log(f"[FOUNDERS] claim limit reached ({limit}); another bundle detected -> "
         "releasing action lock and scheduling short retry")


def recover_from_lootbug(cancelled=lambda: False):
    """Caller owns the action lock. Advance automation or run one bounded manual chain."""
    if cancelled() or _stop_evt.is_set():
        return
    if state.founders_enabled:
        state.founders_next_check_ts = 0.0
        _wake_evt.set()
        _log("[FOUNDERS] Lootbug recovery -> advancing enabled timer; checking now")
        return
    _log("[FOUNDERS] Lootbug recovery -> one manual claim chain (automation remains OFF)")
    try:
        _run_claim_chain(manual=True, cancelled=cancelled)
    finally:
        # A manual request must never leave automatic retries while disabled.
        if not state.founders_enabled:
            state.founders_followup_pending = False
            state.founders_next_check_ts = 0.0


def _try_run_with_lock() -> str:
    """Acquire the action lock and run a cycle.
    Returns: "ok" | "busy" | "no_game" | "pending"
    """
    if not is_game_running():
        _log("[FOUNDERS] game not running -> skipping tick")
        return "no_game"

    lock = getattr(state, "ingame_action_lock", None)
    if lock is None:
        # No lock available — just run.
        _run_claim_chain()
        return "pending" if state.founders_followup_pending else "ok"

    if not lock.acquire(blocking=False):
        _log("[FOUNDERS] another feature is busy -> postponing",
             "FOUNDERS_LOG_LEVEL_BUSY")
        return "busy"
    try:
        _run_claim_chain()
    finally:
        lock.release()
    return "pending" if state.founders_followup_pending else "ok"


def _worker():
    _log(f"[FOUNDERS] worker thread started (enabled={state.founders_enabled}, "
         f"mode=FIRST, FIRST={s.FOUNDERS_CHECK_INTERVAL_S_FIRST:g}s, "
         f"SLOW={s.FOUNDERS_CHECK_INTERVAL_S_SLOW:g}s)")
    _sleep_interruptible(3.0)
    while not _stop_evt.is_set():
        try:
            interval = _check_interval()
            busy_retry = float(getattr(s, "FOUNDERS_BUSY_RETRY_S", 15.0))

            if not getattr(state, "founders_enabled", False):
                state.founders_next_check_ts = 0.0
                # Use interruptible sleep so a toggle-ON wake doesn't get
                # buffered and trigger an extra cycle after the first run.
                _sleep_interruptible(min(5.0, interval))
                continue

            result = _try_run_with_lock()
            interval = _check_interval()
            if result in ("busy", "pending"):
                wait = min(busy_retry, interval)
            elif result == "no_game":
                wait = min(30.0, interval)
            else:
                wait = interval

            state.founders_next_check_ts = time.time() + wait if state.founders_enabled else 0.0
            if state.founders_enabled:
                mode = "SLOW" if _detected_generation == _activation_generation else "FIRST"
                _log(f"[FOUNDERS] next check in {wait:g}s (mode={mode}, reason={result})",
                     "FOUNDERS_LOG_LEVEL_BUSY" if result == "busy" else "FOUNDERS_LOG_LEVEL")
            _sleep_interruptible(wait)
        except Exception as e:
            _log(f"[FOUNDERS] worker error: {type(e).__name__}: {e}")
            time.sleep(5.0)


def _sleep_interruptible(seconds: float):
    if _wake_evt.wait(timeout=seconds):
        _wake_evt.clear()


def start():
    """Start the background worker (idempotent)."""
    global _thread, _thread_started, _detected_generation
    if _thread_started:
        return
    _thread_started = True
    _detected_generation = None
    state.founders_followup_pending = False
    _stop_evt.clear()
    _thread = threading.Thread(target=_worker, daemon=True, name="founders-worker")
    _thread.start()


def toggle() -> bool:
    """Toggle Founders independently and wake the worker when enabled."""
    global _activation_generation
    state.founders_enabled = not state.founders_enabled
    state.founders_next_check_ts = 0.0
    state.founders_followup_pending = False
    if state.founders_enabled:
        _activation_generation += 1
    _wake_evt.set()
    if state.founders_enabled:
        _log(f"[FOUNDERS] toggled -> ON (mode=FIRST, "
             f"interval={s.FOUNDERS_CHECK_INTERVAL_S_FIRST:g}s; checking now)")
    else:
        _log("[FOUNDERS] toggled -> OFF")
    return state.founders_enabled
