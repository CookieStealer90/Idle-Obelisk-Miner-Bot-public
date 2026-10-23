# features/freebies.py - Auto-claim freebies (daily gifts / diamond pack)
"""
Periodically checks whether a freebie is claimable and clicks through the
claim flow.

Flow (see README / chat spec):
    1. Wait `FREEBIES_CHECK_INTERVAL_S` seconds.
    2. Verify game is running. If not, skip this tick.
    3. Pull a fresh screenshot into temp/freebie_scr.png.
    4. Match `freebie_full.png` inside FREEBIES_DETECT_ROI on the base screen.
       If no match -> nothing to do, skip.
    5. Tap the matched button (humanlike jitter).
    6. Pull a new screen, search FREEBIES_CLAIM_ROI for `freebie_claim.png`.
       If not found: scroll to top (multiple full scrolls), then slow-scroll
       down up to FREEBIES_SCROLL_ATTEMPTS times, re-matching each time.
    7. On hit, tap the claim button and check the ADB result. Record an
       estimated X Diamonds (FREEBIES_DIAMONDS_PER_CLAIM); reward unverified.

The worker runs in its own daemon thread and is gated by
`state.freebies_enabled` (toggleable via WebUI).
"""
import threading
import time

import config.app_state as state
import config.settings as s

from core.file_logger import bot_log
from core.screen_cache import get_screen
from core.vision import find_template
from core.tapper import tap
from core.scroll import scroll_up, scroll_down
from core.game_state import is_game_running


_SCR_SLOT = "freebie_scr"
_thread = None
_thread_started = False
_stop_evt = threading.Event()
_wake_evt = threading.Event()   # set to make the worker run a cycle ASAP


def _log(msg: str):
    level = getattr(s, "FREEBIES_LOG_LEVEL", "FULL")
    bot_log(msg, level)


def _fresh_screen():
    """Force a new screenshot pull and return the gray image."""
    img, _, _ = get_screen(_SCR_SLOT, max_age=0.0, force=True)
    return img


def _click_with_log(cx: int, cy: int, what: str):
    j = int(getattr(s, "FREEBIES_TAP_JITTER_PX", 4))
    _log(f"[FREEBIES] tap {what} at ({cx},{cy}) jitter=+/-{j}px")
    ok = tap(cx, cy, jitter=j)
    if not ok:
        _log(f"[FREEBIES] tap failed: {what} at ({cx},{cy})")
    return ok


def _scroll_to_top():
    """Scroll area hard up (several full scrolls to reach the top)."""
    pre = int(getattr(s, "FREEBIES_SCROLL_TO_TOP_COUNT", 6))
    area = tuple(getattr(s, "FREEBIES_CLAIM_ROI", (645, 107, 835, 1472)))
    _log(f"[FREEBIES] scrolling to top ({pre}x fast, area={area})")
    for _ in range(pre):
        if not scroll_down(area=area, speed="fast"):  # finger DOWN -> list UP
            _log("[FREEBIES] scroll to top failed -> abort cycle")
            return False
        time.sleep(0.15)
    return True


def _try_find_claim() -> dict:
    img = _fresh_screen()
    if img is None:
        return {"found": False, "score": 0.0}
    roi = tuple(getattr(s, "FREEBIES_CLAIM_ROI", (645, 107, 835, 1472)))
    thr = float(getattr(s, "FREEBIES_MATCH_THRESHOLD", 0.8))
    tpl = getattr(s, "FREEBIES_CLAIM_TEMPLATE", "freebie/freebie_claim.png")
    m = find_template(img, tpl, roi=roi, threshold=thr)
    return m


def _run_claim_cycle() -> bool:
    """Full flow: detect button on base screen, open menu, find+tap claim.
    Returns True on full success.
    """
    # Step 1: Detect base button
    base_img = _fresh_screen()
    if base_img is None:
        _log("[FREEBIES] no screenshot -> skipping cycle")
        return False

    detect_roi = tuple(getattr(s, "FREEBIES_DETECT_ROI", (713, 1470, 820, 1550)))
    thr = float(getattr(s, "FREEBIES_MATCH_THRESHOLD", 0.8))
    tpl_full = getattr(s, "FREEBIES_FULL_TEMPLATE", "freebie/freebie_full.png")
    tpl_full2 = getattr(s, "FREEBIES_FULL2_TEMPLATE", "freebie/freebie_full2.png")

    m = find_template(base_img, tpl_full, roi=detect_roi, threshold=thr)
    which = "full"
    if not m["found"]:
        m2 = find_template(base_img, tpl_full2, roi=detect_roi, threshold=thr)
        if m2["found"]:
            m = m2
            which = "full2"
        else:
            _log(f"[FREEBIES] nothing to claim (full={m['score']:.3f} full2={m2['score']:.3f} thr={thr})")
            return False

    _log(f"[FREEBIES] freebie available ({which} score={m['score']:.3f}) -> opening menu")
    if not _click_with_log(m["cx"], m["cy"], "freebie-icon"):
        return False

    # Give the menu a moment to open
    time.sleep(float(getattr(s, "FREEBIES_POST_OPEN_DELAY_S", 1.0)))

    # Step 2: Search claim button, scrolling if necessary
    max_scroll_attempts = int(getattr(s, "FREEBIES_SCROLL_ATTEMPTS", 4))
    claim_area = tuple(getattr(s, "FREEBIES_CLAIM_ROI", (645, 107, 835, 1472)))

    m = _try_find_claim()
    if m["found"]:
        _log(f"[FREEBIES] claim button visible immediately (score={m['score']:.3f})")
    else:
        _log(f"[FREEBIES] claim button not visible (score={m['score']:.3f}) -> scrolling")
        if not _scroll_to_top():
            return False
        time.sleep(0.4)
        m = _try_find_claim()
        attempts = 0
        while (not m["found"]) and attempts < max_scroll_attempts:
            attempts += 1
            _log(f"[FREEBIES] slow-scroll searching attempt {attempts}/{max_scroll_attempts}")
            if not scroll_up(area=claim_area, speed="slow"):
                _log("[FREEBIES] search scroll failed -> abort cycle")
                return False
            time.sleep(0.4)
            m = _try_find_claim()

    if not m["found"]:
        _log(f"[FREEBIES] claim button NOT found after {max_scroll_attempts} scrolls -> abort cycle")
        return False

    if not _click_with_log(m["cx"], m["cy"], "claim-button"):
        return False
    amount = int(getattr(s, "FREEBIES_DIAMONDS_PER_CLAIM", 0))
    state.freebies_claimed_count = getattr(state, "freebies_claimed_count", 0) + 1
    state.freebies_diamonds_total = getattr(state, "freebies_diamonds_total", 0) + amount
    state.freebies_last_claim_ts = time.time()
    claimed_level = getattr(s, "FREEBIES_LOG_LEVEL_CLAIMED", getattr(s, "FREEBIES_LOG_LEVEL", "FULL"))
    bot_log(f"[FREEBIES] Claim tap sent; estimated +{amount} Diamonds (totals: {state.freebies_diamonds_total} estimated gems / {state.freebies_claimed_count}x; reward unverified)", claimed_level)

    # Record into Freebie-Gems statistics (survives restarts, tracked per hourly bucket)
    try:
        from features.gem_statistics import get_gem_statistics
        recorded = get_gem_statistics().record_claim("gem", amount=amount)
        if recorded is not None:
            _log(f"[FREEBIES] Freebie-Gems stats updated (+{recorded})")
    except Exception as e:
        _log(f"[FREEBIES] stats update failed: {type(e).__name__}: {e}")

    # Step 3: close the menu
    time.sleep(float(getattr(s, "FREEBIES_POST_CLAIM_DELAY_S", 1.0)))
    close_img = _fresh_screen()
    if close_img is not None:
        close_roi = tuple(getattr(s, "FREEBIES_CLOSE_ROI", (3, 1472, 898, 1547)))
        close_tpl = getattr(s, "FREEBIES_CLOSE_TEMPLATE", "close_menu.png")
        cm = find_template(close_img, close_tpl, roi=close_roi, threshold=thr)
        if cm["found"]:
            if not _click_with_log(cm["cx"], cm["cy"], "close-menu"):
                return False  # claim was sent, but the complete cycle failed
        else:
            _log(f"[FREEBIES] close button NOT found (score={cm['score']:.3f}) -> menu stays open")
    return True


def _worker():
    _log("[FREEBIES] worker thread started")
    # Small initial delay so ADB + game_state get a head start (wake-able)
    _sleep_interruptible(3.0)
    while not _stop_evt.is_set():
        try:
            interval = float(getattr(s, "FREEBIES_CHECK_INTERVAL_S", 300.0))
            if not getattr(state, "freebies_enabled", True):
                state.freebies_next_check_ts = 0.0  # disabled -> no cooldown shown
                # Use interruptible sleep so a toggle-ON wake doesn't get
                # buffered and trigger an extra cycle after the first run.
                _sleep_interruptible(min(5.0, interval))
                continue

            if not is_game_running():
                _log("[FREEBIES] game not running -> skipping tick")
                wait = min(30.0, interval)
                state.freebies_next_check_ts = time.time() + wait
                _sleep_interruptible(wait)
                continue

            lock = getattr(state, "ingame_action_lock", None)
            if lock is not None:
                # Block — freebies cycles are infrequent, waiting is fine.
                with lock:
                    _run_claim_cycle()
            else:
                _run_claim_cycle()
            state.freebies_next_check_ts = time.time() + interval
            _sleep_interruptible(interval)
        except Exception as e:
            _log(f"[FREEBIES] worker error: {type(e).__name__}: {e}")
            time.sleep(5.0)


def _sleep_interruptible(seconds: float):
    """Sleep until `seconds` elapse, or until stop/wake is signalled.
    Wake clears itself, so a toggle()-induced wake triggers exactly one cycle."""
    if _wake_evt.wait(timeout=seconds):
        _wake_evt.clear()


def _sync_statistics(active):
    """Keep statistics failures from stopping game automation or its switch."""
    try:
        from features.gem_statistics import get_gem_statistics
        get_gem_statistics().set_active(active)
    except Exception as exc:
        _log(f"[FREEBIES] statistics state update failed: {type(exc).__name__}: {exc}")


def start():
    """Start the background worker (idempotent)."""
    global _thread, _thread_started
    if _thread_started:
        return
    _sync_statistics(bool(getattr(state, "freebies_enabled", True)))
    _thread_started = True
    _stop_evt.clear()
    _thread = threading.Thread(target=_worker, daemon=True, name="freebies-worker")
    _thread.start()


def toggle() -> bool:
    """Flip state.freebies_enabled. Returns the new value.
    On ON-transition the worker wakes immediately and runs a cycle — no
    waiting for the configured interval first."""
    new = not bool(getattr(state, "freebies_enabled", True))
    _sync_statistics(new)
    state.freebies_enabled = new
    if new:
        # Wake the worker so it runs a cycle immediately instead of sleeping.
        state.freebies_next_check_ts = 0.0
        _wake_evt.set()
    _log(f"[FREEBIES] toggled -> {'ON' if new else 'OFF'}")
    return new
