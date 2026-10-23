# features/lootbug.py - Auto-click in-game Lootbug
"""
Periodically checks whether a Lootbug is on screen and taps it.

Flow:
    1. Wait LOOTBUG_CHECK_INTERVAL_S between scans.
    2. Skip the tick if the game isn't running.
    3. Try to acquire the global ingame_action_lock (non-blocking). If another
       feature is currently performing taps/scrolls, postpone — retry after
       LOOTBUG_BUSY_RETRY_S without resetting the main interval.
    4. Reuse temp/game_scr.png if younger than LOOTBUG_SCREEN_REUSE_AGE_S.
       Otherwise pull a fresh frame into temp/lootbug_scr.png.
    5. Match LOOTBUG_TEMPLATE inside LOOTBUG_DETECT_ROI. No hit -> done.
    6. Tap the matched lootbug (jitter), wait LOOTBUG_POST_CLICK_DELAY_S,
       then look for close_menu.png inside LOOTBUG_CLOSE_ROI and tap it
       to dismiss the resulting popup.

The worker runs in its own daemon thread, gated by `state.lootbug_enabled`
(toggleable via WebUI).
"""
import glob
import os
import threading
import time

import config.app_state as state
import config.settings as s
from config.settings import BASE_DIR

from core.file_logger import bot_log
from core.screen_cache import get_screen
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

    img, _, _ = get_screen(shared_slot, max_age=max_age, force=False)
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
    tap(cx, cy, jitter=j)


def _close_popup(popup_img, thr: float, label: str = "close-popup"):
    """Look for the close button and tap it. Returns True if found."""
    close_roi = tuple(getattr(s, "LOOTBUG_CLOSE_ROI", (395, 987, 503, 1085)))
    close_tpl = getattr(s, "LOOTBUG_CLOSE_TEMPLATE", "Lootbug/lootbug_close_menu.png")
    cm = find_template(popup_img, close_tpl, roi=close_roi, threshold=thr)
    if cm["found"]:
        _click(cm["cx"], cm["cy"], label)
        return True
    return False


def _check_founders(img, thr: float) -> bool:
    """Check for the founders lootbox and tap it if present. Returns True if clicked."""
    roi = tuple(getattr(s, "LOOTBUG_FOUNDERS_DETECT_ROI", (310, 495, 500, 905)))
    tpl = getattr(s, "LOOTBUG_FOUNDERS_TEMPLATE", "Lootbug/founders_bundle_tpl.png")
    m = find_template(img, tpl, roi=roi, threshold=float(getattr(s, "LOOTBUG_MATCH_THRESHOLD", 0.8)))
    if not m["found"]:
        _log(f"[LOOTBUG] founders: not present (score={m['score']:.3f})",
             "LOOTBUG_FOUNDERS_LOG_LEVEL")
        return False

    _log(f"[LOOTBUG] founders lootbox detected (score={m['score']:.3f}) -> clicking",
         "LOOTBUG_FOUNDERS_LOG_LEVEL")
    _click(m["cx"], m["cy"], "founders-lootbox")
    state.lootbug_founders_count = getattr(state, "lootbug_founders_count", 0) + 1

    time.sleep(float(getattr(s, "LOOTBUG_POST_CLICK_DELAY_S", 1.2)))
    popup_img = _fresh_own_screen()
    if popup_img is None:
        _log("[LOOTBUG] founders: no screenshot for close -> popup may stay open",
             "LOOTBUG_FOUNDERS_LOG_LEVEL")
        return True

    if not _close_popup(popup_img, thr, "close-founders-popup"):
        _log(f"[LOOTBUG] founders: close button NOT found -> popup may stay open",
             "LOOTBUG_FOUNDERS_LOG_LEVEL")
    return True


def _run_scan_cycle() -> bool:
    """Detect + click + dismiss lootbug (and optionally founders lootbox).
    Returns True if anything was clicked."""
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
        _log(f"[LOOTBUG] no lootbug present (best_score={m['score']:.3f} thr={thr} tpl={m.get('template')})",
             "LOOTBUG_LOG_LEVEL_DETECT")
    else:
        _log(f"[LOOTBUG] lootbug detected via {m.get('template')} (score={m['score']:.3f}) -> clicking",
             "LOOTBUG_LOG_LEVEL_DETECT")
        _click(m["cx"], m["cy"], "lootbug")

        state.lootbug_clicked_count = getattr(state, "lootbug_clicked_count", 0) + 1
        state.lootbug_last_click_ts = time.time()
        lootbug_clicked = True

        # Wait briefly for the popup to appear
        time.sleep(float(getattr(s, "LOOTBUG_POST_CLICK_DELAY_S", 1.2)))
        popup_img = _fresh_own_screen()
        if popup_img is None:
            _log("[LOOTBUG] no screenshot for close -> popup may stay open")
        else:
            # Optional gem-bonus purchase
            bonus_used = False
            if getattr(state, "lootbug_buy_bonus", False):
                bonus_roi = tuple(getattr(s, "LOOTBUG_BONUS_DETECT_ROI", (540, 497, 693, 640)))
                bm = _find_any_template(popup_img, bonus_roi, thr,
                                        pattern_attr="LOOTBUG_BONUS_TEMPLATE_GLOB",
                                        single_attr="LOOTBUG_BONUS_TEMPLATE")
                if bm["found"]:
                    buy_roi = tuple(getattr(s, "LOOTBUG_BONUS_BUY_ROI", (540, 846, 695, 914)))
                    bx = (buy_roi[0] + buy_roi[2]) // 2
                    by = (buy_roi[1] + buy_roi[3]) // 2
                    bj = int(getattr(s, "LOOTBUG_BONUS_TAP_JITTER_PX", 4))
                    delay = float(getattr(s, "LOOTBUG_BONUS_DOUBLE_CLICK_DELAY_S", 0.1))
                    _log(f"[LOOTBUG] bonus matched via {bm.get('template')} "
                         f"(score={bm['score']:.3f}) -> double-tap buy at ({bx},{by})",
                         "LOOTBUG_LOG_LEVEL_BONUS")
                    tap(bx, by, jitter=bj)
                    time.sleep(delay)
                    tap(bx, by, jitter=bj)
                    state.lootbug_bonus_count = getattr(state, "lootbug_bonus_count", 0) + 1
                    bonus_used = True
                else:
                    _log(f"[LOOTBUG] no desired bonus (best_score={bm['score']:.3f} "
                         f"tpl={bm.get('template')}) -> fallback to close",
                         "LOOTBUG_LOG_LEVEL_BONUS")

            if not bonus_used:
                if not _close_popup(popup_img, thr):
                    _log(f"[LOOTBUG] close button NOT found -> popup may stay open")

    # --- Founders lootbox (checked on same initial frame; fresh frame if lootbug was tapped) ---
    founders_clicked = False
    if getattr(s, "LOOTBUG_FOUNDERS_ENABLED", False):
        founders_img = _fresh_own_screen() if lootbug_clicked else img
        if founders_img is not None:
            founders_clicked = _check_founders(founders_img, thr)

    return lootbug_clicked or founders_clicked


def _try_run_with_lock() -> str:
    """Acquire the action lock and run a cycle.
    Returns: "ok" | "busy" | "no_game"
    """
    if not is_game_running():
        _log("[LOOTBUG] game not running -> skipping tick")
        return "no_game"

    lock = getattr(state, "ingame_action_lock", None)
    if lock is None:
        # No lock available — just run.
        _run_scan_cycle()
        return "ok"

    if not lock.acquire(blocking=False):
        _log("[LOOTBUG] another feature is busy -> postponing",
             "LOOTBUG_LOG_LEVEL_BUSY")
        return "busy"
    try:
        _run_scan_cycle()
    finally:
        lock.release()
    return "ok"


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
            if result == "busy":
                wait = min(busy_retry, interval)
            elif result == "no_game":
                wait = min(30.0, interval)
            else:
                wait = interval

            state.lootbug_next_check_ts = time.time() + wait
            _sleep_interruptible(wait)
        except Exception as e:
            _log(f"[LOOTBUG] worker error: {type(e).__name__}: {e}")
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
    _thread = threading.Thread(target=_worker, daemon=True, name="lootbug-worker")
    _thread.start()


def toggle() -> bool:
    """Tri-state cycle: OFF -> ON (no bonus) -> ON (with bonus) -> OFF.
    Returns the resulting `lootbug_enabled` value.
    Worker wakes immediately when transitioning into either ON state."""
    enabled = bool(getattr(state, "lootbug_enabled", False))
    buy = bool(getattr(state, "lootbug_buy_bonus", False))

    if not enabled:
        # OFF -> ON, no bonus
        state.lootbug_enabled = True
        state.lootbug_buy_bonus = False
        label = "ON (no bonus)"
    elif enabled and not buy:
        # ON, no bonus -> ON + bonus
        state.lootbug_buy_bonus = True
        label = "ON (+ bonus)"
    else:
        # ON + bonus -> OFF
        state.lootbug_enabled = False
        state.lootbug_buy_bonus = False
        label = "OFF"

    if state.lootbug_enabled:
        state.lootbug_next_check_ts = 0.0
        _wake_evt.set()
    _log(f"[LOOTBUG] toggled -> {label}")
    return state.lootbug_enabled
