# features/detect_level.py - Periodic on-screen level detection
"""
Scans a configured ROI for digit templates and publishes the resulting
integer (1..999) to state.current_level.

Design:
    - Loads all images/level/digit_*_tpl.png at startup (digits 0..9).
      Missing digits are simply not detected; the template filename encodes
      the digit value (digit_<N>_tpl.png).
    - Runs in a daemon thread on DETECT_LEVEL_INTERVAL_S.
    - Reuses any recent cached screenshot (DETECT_LEVEL_CACHE_MAX_AGE_S),
      falling back to a fresh pull into its own slot. Newest among the
      accept-list wins — same policy as the game-running watchdog.
    - For each digit template, runs cv2.matchTemplate, extracts every peak
      above DETECT_LEVEL_THRESHOLD, then applies NMS by horizontal distance
      (digits can't overlap horizontally in the UI). Remaining peaks are
      sorted by X; their digit values concatenate into the level integer.

Workflow if-conditions (level_eq / level_gte / level_lte) consume
state.current_level — when None (scan failed or feature disabled) these
conditions evaluate to False.
"""
import glob
import os
import re
import threading
import time

import cv2
from core.image_io import read_image

import config.app_state as state
import config.settings as s

from core.file_logger import bot_log
from core.screen_cache import get_screen, get_latest_cached_screen
from core.game_state import is_game_running


_SCR_SLOT_DEFAULT = "level_scr"
_DIGIT_RE = re.compile(r"digit_(\d)_tpl\.png$", re.IGNORECASE)

_thread = None
_thread_started = False
_stop_evt = threading.Event()
_wake_evt = threading.Event()

# Loaded at startup: list of (digit:int, template_gray:np.ndarray, w:int, h:int)
_digit_templates = []


def _log(msg: str):
    level = getattr(s, "DETECT_LEVEL_LOG_LEVEL", "FULL")
    bot_log(msg, level)


def _load_digit_templates():
    """Discover images/level/digit_*_tpl.png files and load them as grayscale."""
    global _digit_templates
    _digit_templates = []
    from config.settings import IMG_DIR
    level_dir = os.path.join(str(IMG_DIR), "level")
    if not os.path.isdir(level_dir):
        return 0
    for path in sorted(glob.glob(os.path.join(level_dir, "digit_*_tpl.png"))):
        m = _DIGIT_RE.search(os.path.basename(path))
        if not m:
            continue
        digit = int(m.group(1))
        img = read_image(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        h, w = img.shape[:2]
        _digit_templates.append((digit, img, w, h))
    return len(_digit_templates)


def _best_cached_screen(max_age: float):
    """Return (img_gray, slot_name) from the freshest accepted cache slot
    younger than max_age, or (None, None) if nothing qualifies."""
    slots = list(getattr(s, "DETECT_LEVEL_ACCEPT_SLOTS", [_SCR_SLOT_DEFAULT]))
    img, _, _, slot, _ = get_latest_cached_screen(slots, max_age)
    return img, slot


def _get_screen_for_scan():
    """Reuse a fresh cached screenshot if available; otherwise pull into own slot."""
    max_age = float(getattr(s, "DETECT_LEVEL_CACHE_MAX_AGE_S", 15.0))
    img, slot = _best_cached_screen(max_age)
    if img is not None:
        return img, slot
    own_slot = getattr(s, "DETECT_LEVEL_OWN_SCREEN_SLOT", _SCR_SLOT_DEFAULT)
    img, _w, _h = get_screen(own_slot, max_age=0.0, force=True)
    return img, own_slot


def _scan_level():
    """Run one detection pass. Returns (level:int | None, reason:str)."""
    if not _digit_templates:
        return None, "no digit templates loaded"

    img, _slot = _get_screen_for_scan()
    if img is None:
        return None, "no screenshot"

    roi = tuple(getattr(s, "DETECT_LEVEL_ROI", (0, 61, 60, 89)))
    threshold = float(getattr(s, "DETECT_LEVEL_THRESHOLD", 0.85))
    min_dx = int(getattr(s, "DETECT_LEVEL_NMS_MIN_DX_PX", 8))

    x1, y1, x2, y2 = roi
    h_img, w_img = img.shape[:2]
    x1 = max(0, min(int(x1), w_img))
    y1 = max(0, min(int(y1), h_img))
    x2 = max(x1, min(int(x2), w_img))
    y2 = max(y1, min(int(y2), h_img))
    if x2 <= x1 or y2 <= y1:
        return None, f"invalid ROI {roi}"
    area = img[y1:y2, x1:x2]

    # Collect all candidate peaks above threshold across all digit templates.
    # Each peak: (score, cx_in_roi, digit)
    peaks = []
    for digit, tpl, tw, th in _digit_templates:
        if area.shape[0] < th or area.shape[1] < tw:
            continue
        res = cv2.matchTemplate(area, tpl, cv2.TM_CCOEFF_NORMED)
        # Grab all matches above threshold
        ys, xs = (res >= threshold).nonzero()
        for py, px in zip(ys, xs):
            score = float(res[py, px])
            cx = int(px) + tw // 2
            peaks.append((score, cx, digit))

    if not peaks:
        return None, f"no digits matched above threshold {threshold:.2f}"

    # NMS: sort by score desc, accept peak if it's not within min_dx of
    # an already-accepted peak (on X axis — digits don't overlap horizontally).
    peaks.sort(key=lambda p: p[0], reverse=True)
    accepted = []
    for score, cx, digit in peaks:
        if any(abs(cx - acx) < min_dx for _s, acx, _d in accepted):
            continue
        accepted.append((score, cx, digit))

    if len(accepted) > 3:
        # Keep the 3 highest-confidence digits — extras are likely false positives.
        accepted.sort(key=lambda p: p[0], reverse=True)
        dropped = len(accepted) - 3
        accepted = accepted[:3]
        _log(f"[LEVEL] NMS kept 3 highest-confidence digits, dropped {dropped}")

    if len(accepted) < 1:
        return None, "no digits survived NMS"

    # Left-to-right by X
    accepted.sort(key=lambda p: p[1])
    digits_str = "".join(str(d) for _s, _x, d in accepted)
    try:
        value = int(digits_str)
    except ValueError:
        return None, f"parse failed from '{digits_str}'"

    if value < 1 or value > 999:
        return None, f"out of range: {value}"
    return value, ""


def _run_cycle():
    level, reason = _scan_level()
    if level is None:
        state.current_level = None
        state.detect_level_last_error = reason
        _log(f"[LEVEL] Level scan failed: {reason}")
        return False
    state.current_level = int(level)
    state.current_level_ts = time.time()
    state.detect_level_last_error = ""
    _log(f"[LEVEL] Level scanned - current {level}")
    return True


def _sleep_interruptible(seconds: float):
    if _wake_evt.wait(timeout=seconds):
        _wake_evt.clear()


def _worker():
    _log("[LEVEL] worker thread started")
    _sleep_interruptible(3.0)
    while not _stop_evt.is_set():
        try:
            interval = float(getattr(s, "DETECT_LEVEL_INTERVAL_S", 60.0))
            if not getattr(state, "detect_level_enabled", True):
                state.current_level = None
                state.detect_level_next_check_ts = 0.0
                _sleep_interruptible(min(5.0, interval))
                continue

            if not is_game_running():
                state.detect_level_next_check_ts = time.time() + min(30.0, interval)
                _sleep_interruptible(min(30.0, interval))
                continue

            # Detection is read-only — no ingame_action_lock needed.
            _run_cycle()
            state.detect_level_next_check_ts = time.time() + interval
            _sleep_interruptible(interval)
        except Exception as e:
            _log(f"[LEVEL] worker error: {type(e).__name__}: {e}")
            time.sleep(5.0)


def start():
    """Start the background worker (idempotent). Loads digit templates."""
    global _thread, _thread_started
    if _thread_started:
        return
    n = _load_digit_templates()
    state.detect_level_digits_loaded = n
    if n == 0:
        bot_log("[LEVEL] Level detection disabled: no digit templates found in images/level/",
                getattr(s, "DETECT_LEVEL_LOG_LEVEL", "FULL"))
        # Don't start the worker; leave state.current_level = None.
        _thread_started = True
        return
    bot_log(f"[LEVEL] Level detection armed ({n} digit templates loaded)",
            getattr(s, "DETECT_LEVEL_LOG_LEVEL", "FULL"))
    _thread_started = True
    _stop_evt.clear()
    _thread = threading.Thread(target=_worker, daemon=True, name="detect-level-worker")
    _thread.start()


def toggle() -> bool:
    """Flip state.detect_level_enabled. Returns the new value."""
    new = not bool(getattr(state, "detect_level_enabled", True))
    state.detect_level_enabled = new
    if new:
        state.detect_level_next_check_ts = 0.0
        _wake_evt.set()
    else:
        state.current_level = None
    _log(f"[LEVEL] toggled -> {'ON' if new else 'OFF'}")
    return new


def trigger_now():
    """Wake the worker for an immediate scan."""
    _wake_evt.set()
