# features/lootbug.py - Auto-click in-game Lootbug
"""
Periodically checks whether a Lootbug is on screen and taps it.

Flow:
    1. Wait LOOTBUG_CHECK_INTERVAL_S +/- LOOTBUG_INTERVAL_VARIANCE_PCT between scans.
    2. Skip the tick if the game isn't running.
    3. Try to acquire the global ingame_action_lock (non-blocking). If another
       feature is currently performing taps/scrolls, postpone — retry after
       LOOTBUG_BUSY_RETRY_S.
    4. Reuse temp/game_scr.png if younger than LOOTBUG_SCREEN_REUSE_AGE_S.
       Otherwise pull a fresh frame into temp/lootbug_scr.png.
    5. Match LOOTBUG_TEMPLATE inside LOOTBUG_DETECT_ROI. No hit -> done.
    6. Tap the matched lootbug (jitter), wait LOOTBUG_POST_CLICK_DELAY_S,
       then find lootbug_buy_bonus.png inside LOOTBUG_BONUS_BUY_ROI and
       verify dismissal after each tap. Retry up to BUY_MAX_ATTEMPTS,
       yielding early when Founders is due. Never click Close.

The worker runs in its own daemon thread, gated by `state.lootbug_enabled`
(toggleable via WebUI).
"""
import glob
import os
import random
import threading
import time

import config.app_state as state
import config.settings as s
from config.settings import BASE_DIR

from core.file_logger import bot_log
from core.screen_cache import get_screen, get_cached_screen
from core.vision import find_template
from core.tapper import tap
from core.game_state import is_game_running


_thread = None
_thread_started = False
_stop_evt = threading.Event()
_wake_evt = threading.Event()   # set to make the worker run a cycle ASAP


def _log(msg: str, level_attr: str = "LOOTBUG_LOG_LEVEL"):
    level = getattr(s, level_attr, "FULL")
    bot_log(msg, level)


def _get_screen_for_scan():
    """Reuse the shared game screenshot if fresh, else pull our own."""
    shared_slot = getattr(s, "LOOTBUG_SHARED_SCREEN_SLOT", "game_scr")
    own_slot = getattr(s, "LOOTBUG_OWN_SCREEN_SLOT", "lootbug_scr")
    max_age = float(getattr(s, "LOOTBUG_SCREEN_REUSE_AGE_S", 5.0))

    img, _, _ = get_cached_screen(shared_slot, max_age=max_age)
    if img is not None:
        return img
    img, _, _ = get_screen(own_slot, max_age=0.0, force=True)
    return img


def _fresh_own_screen():
    own_slot = getattr(s, "LOOTBUG_OWN_SCREEN_SLOT", "lootbug_scr")
    img, _, _ = get_screen(own_slot, max_age=0.0, force=True)
    return img


def _resolve_templates(pattern_attr: str = "LOOTBUG_TEMPLATE_GLOB",
                       single_attr: str = "LOOTBUG_TEMPLATE") -> list:
    """Expand a glob attr into a list of rel-paths under images/.
    Falls back to a single-file attr if no glob configured."""
    img_dir = os.path.join(str(BASE_DIR), "images")
    pattern = getattr(s, pattern_attr, None)
    if pattern:
        abs_pattern = os.path.join(img_dir, pattern.replace("/", os.sep))
        matches = sorted(glob.glob(abs_pattern))
        rels = [os.path.relpath(p, img_dir).replace(os.sep, "/") for p in matches]
        if rels:
            return rels
        _log(f"[LOOTBUG] glob '{pattern}' matched no files under images/")
    single = getattr(s, single_attr, None)
    return [single] if single else []


def _find_any_template(img, roi, thr,
                       pattern_attr: str = "LOOTBUG_TEMPLATE_GLOB",
                       single_attr: str = "LOOTBUG_TEMPLATE") -> dict:
    """Try each template; return first hit (or last miss with best score)."""
    templates = _resolve_templates(pattern_attr, single_attr)
    if not templates:
        return {"found": False, "score": 0.0, "template": None}

    best = {"found": False, "score": -1.0, "template": None}
    for tpl in templates:
        m = find_template(img, tpl, roi=roi, threshold=thr)
        if m["found"]:
            m["template"] = tpl
            return m
        if m["score"] > best["score"]:
            best = dict(m)
            best["template"] = tpl
    return best


def _click(cx: int, cy: int, what: str):
    j = int(getattr(s, "LOOTBUG_TAP_JITTER_PX", 4))
    _log(f"[LOOTBUG] tap {what} at ({cx},{cy}) jitter=+/-{j}px",
         "LOOTBUG_LOG_LEVEL_CLICK")
    ok = tap(cx, cy, jitter=j)
    if not ok:
        _log(f"[LOOTBUG] tap failed: {what} at ({cx},{cy})", "LOOTBUG_LOG_LEVEL_CLICK")
    return ok


def _founders_due() -> bool:
    if not getattr(state, "founders_enabled", False):
        return False
    if getattr(state, "founders_followup_pending", False):
        return True
    deadline = float(getattr(state, "founders_next_check_ts", 0.0))
    lookahead = float(getattr(s, "LOOTBUG_FOUNDERS_LOOKAHEAD_S", 5.0))
    return deadline <= time.time() + lookahead


def _buy_when_visible(thr: float) -> bool:
    """Bound Buy retries while retaining the caller's action lock."""
    limit = int(getattr(s, "LOOTBUG_BUY_MAX_ATTEMPTS", 5))
    for attempt in range(1, limit + 1):
        waited_after_tap = False
        if not state.lootbug_enabled or _stop_evt.is_set():
            return False
        if _founders_due():
            _log("[LOOTBUG] Founders check due -> aborting Buy search and releasing action lock",
                 "LOOTBUG_LOG_LEVEL_BONUS")
            return False
        _log(f"[LOOTBUG] buy attempt {attempt}/{limit}", "LOOTBUG_LOG_LEVEL_BONUS")
        popup_img = _fresh_own_screen()
        if popup_img is not None:
            bm = find_template(popup_img, s.LOOTBUG_BONUS_BUY_TEMPLATE,
                               roi=tuple(s.LOOTBUG_BONUS_BUY_ROI), threshold=thr)
            if bm["found"]:
                jitter = int(s.LOOTBUG_BONUS_TAP_JITTER_PX)
                _log(f"[LOOTBUG] buy box detected (score={bm['score']:.3f}) "
                     f"-> tap near target center ({bm['cx']},{bm['cy']}); "
                     f"position jitter +/-{jitter}px per axis applied by tapper",
                     "LOOTBUG_LOG_LEVEL_BONUS")
                if not state.lootbug_enabled or _stop_evt.is_set():
                    return False
                if tap(bm["cx"], bm["cy"], jitter=jitter):
                    # ADB success does not mean the game accepted the purchase.
                    delay = max(0.1, float(s.LOOTBUG_BUY_RETRY_S))
                    state.lootbug_next_check_ts = time.time() + delay
                    _sleep_interruptible(delay)
                    waited_after_tap = True
                    if not state.lootbug_enabled or _stop_evt.is_set():
                        return False
                    check_img = _fresh_own_screen()
                    if check_img is not None:
                        check = find_template(check_img, s.LOOTBUG_BONUS_BUY_TEMPLATE,
                                              roi=tuple(s.LOOTBUG_BONUS_BUY_ROI), threshold=thr)
                        if not check["found"]:
                            state.lootbug_bonus_count = getattr(state, "lootbug_bonus_count", 0) + 1
                            _log("[LOOTBUG] Buy box absent after tap; reward not independently verified",
                                 "LOOTBUG_LOG_LEVEL_BONUS")
                            return True
                        _log("[LOOTBUG] Buy box still visible after tap -> retrying",
                             "LOOTBUG_LOG_LEVEL_BONUS")
                    else:
                        _log("[LOOTBUG] no verification screenshot -> retrying without counting",
                             "LOOTBUG_LOG_LEVEL_BONUS")
                else:
                    _log("[LOOTBUG] buy tap failed -> retrying", "LOOTBUG_LOG_LEVEL_BONUS")
            else:
                _log(f"[LOOTBUG] buy box obscured/not found (score={bm['score']:.3f}) -> retrying",
                     "LOOTBUG_LOG_LEVEL_BONUS")
        else:
            _log("[LOOTBUG] no buy screenshot -> retrying", "LOOTBUG_LOG_LEVEL_BONUS")
        if attempt == limit:
            _log(f"[LOOTBUG] Buy search exhausted after {limit} attempts -> "
                 "giving up this cycle and releasing action lock (no Close tap)",
                 "LOOTBUG_LOG_LEVEL_BONUS")
            return False
        if not waited_after_tap:
            delay = max(0.1, float(s.LOOTBUG_BUY_RETRY_S))
            state.lootbug_next_check_ts = time.time() + delay
            _sleep_interruptible(delay)
    return False


def _run_scan_cycle() -> bool:
    """Open a Lootbug or resume an existing Buy dialog and verify Buy taps.
    Return True for a Lootbug tap or observed Buy dismissal."""
    img = _get_screen_for_scan()
    if img is None:
        _log("[LOOTBUG] no screenshot -> skipping cycle")
        return False

    thr = float(getattr(s, "LOOTBUG_MATCH_THRESHOLD", 0.8))
    roi = tuple(getattr(s, "LOOTBUG_DETECT_ROI", (253, 650, 463, 952)))

    # --- Regular lootbug ---
    lootbug_clicked = False
    m = _find_any_template(img, roi, thr)
    if not m["found"]:
        # Recover an open dialog, including one left behind by a Founders yield.
        # This cached match is only a hint; Buy always uses a fresh capture.
        buy = find_template(img, s.LOOTBUG_BONUS_BUY_TEMPLATE,
                            roi=tuple(s.LOOTBUG_BONUS_BUY_ROI), threshold=thr)
        if buy["found"]:
            _log("[LOOTBUG] existing Buy box detected -> resuming bounded Buy search",
                 "LOOTBUG_LOG_LEVEL_BONUS")
            _sleep_interruptible(float(s.LOOTBUG_POST_CLICK_DELAY_S))
            return _buy_when_visible(thr)
        _log(f"[LOOTBUG] no lootbug present (best_score={m['score']:.3f} thr={thr} tpl={m.get('template')})",
             "LOOTBUG_LOG_LEVEL_DETECT")
    else:
        _log(f"[LOOTBUG] lootbug detected via {m.get('template')} (score={m['score']:.3f}) -> clicking",
             "LOOTBUG_LOG_LEVEL_DETECT")
        if not _click(m["cx"], m["cy"], "lootbug"):
            return False

        state.lootbug_clicked_count = getattr(state, "lootbug_clicked_count", 0) + 1
        state.lootbug_last_click_ts = time.time()
        lootbug_clicked = True

        # Keep the action lock only for this bounded Buy search.
        _sleep_interruptible(float(s.LOOTBUG_POST_CLICK_DELAY_S))
        _buy_when_visible(thr)

    return lootbug_clicked


def _try_run_with_lock() -> str:
    """Acquire the action lock and run a cycle.
    Returns: "ok" | "busy" | "no_game" | "founders_due"
    """
    if _founders_due():
        _log("[LOOTBUG] Founders check due soon/pending -> waiting without action lock",
             "LOOTBUG_LOG_LEVEL_BUSY")
        return "founders_due"
    if not is_game_running():
        _log("[LOOTBUG] game not running -> skipping tick")
        return "no_game"

    lock = getattr(state, "ingame_action_lock", None)
    if lock is None:
        # No lock available — just run.
        _run_scan_cycle()
        return "founders_due" if _founders_due() else "ok"

    if not lock.acquire(blocking=False):
        _log("[LOOTBUG] another feature is busy -> postponing",
             "LOOTBUG_LOG_LEVEL_BUSY")
        return "busy"
    try:
        if _founders_due():
            return "founders_due"
        _run_scan_cycle()
    finally:
        lock.release()
    return "founders_due" if _founders_due() else "ok"


def _next_scan_delay(interval: float) -> float:
    """Sample once per regular cycle; the worker publishes this same delay."""
    variance = min(100.0, max(0.0, float(s.LOOTBUG_INTERVAL_VARIANCE_PCT)))
    factor = 1.0 + random.uniform(-variance, variance) / 100.0 if variance else 1.0
    return max(0.1, interval * factor)


def _worker():
    _log("[LOOTBUG] worker thread started")
    _sleep_interruptible(3.0)
    while not _stop_evt.is_set():
        try:
            interval = float(getattr(s, "LOOTBUG_CHECK_INTERVAL_S", 180.0))
            busy_retry = float(getattr(s, "LOOTBUG_BUSY_RETRY_S", 15.0))

            if not getattr(state, "lootbug_enabled", False):
                state.lootbug_next_check_ts = 0.0
                # Use interruptible sleep so a toggle-ON wake doesn't get
                # buffered and trigger an extra cycle after the first run.
                _sleep_interruptible(min(5.0, interval))
                continue

            result = _try_run_with_lock()
            if not state.lootbug_enabled:
                state.lootbug_next_check_ts = 0.0
                continue
            if result == "founders_due":
                wait = min(1.0, interval)
            elif result == "busy":
                wait = min(busy_retry, interval)
            elif result == "no_game":
                wait = min(30.0, interval)
            else:
                wait = _next_scan_delay(interval)

            state.lootbug_next_check_ts = time.time() + wait
            _sleep_interruptible(wait)
        except Exception as e:
            _log(f"[LOOTBUG] worker error: {type(e).__name__}: {e}")
            state.lootbug_next_check_ts = time.time() + 5.0 if state.lootbug_enabled else 0.0
            _sleep_interruptible(5.0)


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
    _thread = threading.Thread(target=_worker, daemon=True, name="lootbug-worker")
    _thread.start()


def toggle() -> bool:
    """Toggle Lootbug on/off; also interrupt any pending buy retry."""
    state.lootbug_enabled = not state.lootbug_enabled
    state.lootbug_next_check_ts = 0.0
    _wake_evt.set()
    _log(f"[LOOTBUG] toggled -> {'ON' if state.lootbug_enabled else 'OFF'}")
    return state.lootbug_enabled
