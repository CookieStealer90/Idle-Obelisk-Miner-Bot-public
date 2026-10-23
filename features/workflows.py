# features/workflows.py - Workflow scheduler
"""
Central scheduler for user-defined workflows.

A workflow is a sequence of steps (taps, swipes, template clicks, waits).
Definitions live in config.config_workflows.WORKFLOWS; users edit them via
the WebUI workflow editor (saved to config/user_workflows.json).

Scheduling rules:
    - Master toggle `state.workflows_master_enabled` ("Auto WF" button).
      OFF => no auto-runs, no manual triggers.
    - Each WF has its own interval; +/- variance applied per cycle.
    - Multiple WFs due at the same time run sequentially (FIFO by next_due).
    - WF execution holds `state.ingame_action_lock` for the ENTIRE workflow
      — other features (freebies/lootbug) wait until the WF is fully done,
      including between steps and across nested call_workflow. If another
      feature already holds the lock when a WF wants to start, the WF retries
      after WORKFLOWS_BUSY_RETRY_S seconds.
    - Manual trigger ("Run" button) is REJECTED with a toast if any WF is
      currently executing a step.
    - Master OFF cancels in-progress WFs cooperatively between steps.
"""
import os
import random
import threading
import time
from functools import wraps

import cv2
import numpy as np

import config.app_state as state
import config.settings as s
import config.config_workflows as cfg_wf

from core.file_logger import bot_log
from core.screen_cache import get_screen
from core.vision import find_template
from core.rotation_cache import find_template_rotating
from core.tapper import tap
from core.scroll import scroll
from core.adb_helper import adb
from core.game_state import is_game_running


_thread = None
_thread_started = False
_stop_evt = threading.Event()
_wake_evt = threading.Event()
_cancel_evt = threading.Event()       # set on master-OFF -> abort step loop
_manual_queue = []                    # list of slugs to run manually ASAP
_manual_lock = threading.Lock()
_reload_evt = threading.Event()
_call_stack = []                      # active call_workflow chain (recursion guard)
_last_click_template_missed = False   # per-step flag: True when click_template
                                      # didn't find its template (even if optional
                                      # saved the step from failing). Consumed by
                                      # the 'if' last_step_ok evaluator.


# ============================================================
#  Logging helpers (per-WF override falls back to global)
# ============================================================


def _with_state_lock(function):
    @wraps(function)
    def locked(*args, **kwargs):
        with state.workflows_lock:
            return function(*args, **kwargs)
    return locked

def _wf_level(wf: dict, key: str, fallback_attr: str) -> str:
    val = wf.get(key) if isinstance(wf, dict) else None
    if val:
        return val
    return getattr(s, fallback_attr, "FULL")


def _log(msg: str, wf: dict = None):
    bot_log(msg, _wf_level(wf or {}, "log_level", "WORKFLOWS_LOG_LEVEL"))


def _log_step(msg: str, wf: dict = None):
    bot_log(msg, _wf_level(wf or {}, "log_level_step", "WORKFLOWS_LOG_LEVEL_STEP"))


def _log_busy(msg: str, wf: dict = None):
    bot_log(msg, _wf_level(wf or {}, "log_level_busy", "WORKFLOWS_LOG_LEVEL_BUSY"))


# ============================================================
#  Toast helper (lazy import to avoid circular deps)
# ============================================================

def _push_toast(msg: str, error: bool = False):
    try:
        from web.app import push_toast
        push_toast(msg, error=error)
    except Exception:
        pass


# ============================================================
#  Step executors
# ============================================================

def _wf_count(step: dict) -> tuple:
    """Return (count, interval_s) for dumb-repeat steps (tap_roi/tap_xy/swipe)."""
    _cnt = step.get("count")
    count = max(1, int(_cnt) if _cnt not in (None, "") else 1)
    _ci = step.get("count_interval_s")
    interval = max(0.0, float(_ci) if _ci not in (None, "") else 0.2)
    return count, interval


def _step_tap_roi(step: dict, wf: dict) -> bool:
    roi = step.get("roi") or [0, 0, 0, 0]
    x1, y1, x2, y2 = int(roi[0]), int(roi[1]), int(roi[2]), int(roi[3])
    if x2 <= x1 or y2 <= y1:
        _log_step(f"[WF] tap_roi invalid ROI {roi}", wf)
        return False
    j = int(step.get("jitter", getattr(s, "WORKFLOWS_TAP_JITTER_PX", 4)))
    count, interval = _wf_count(step)
    cnote = f" count={count} interval={interval}s" if count > 1 else ""
    for i in range(count):
        if i > 0:
            _interruptible_sleep(interval)
            if _cancel_evt.is_set() or _stop_evt.is_set():
                return False
        cx = random.randint(x1, x2)
        cy = random.randint(y1, y2)
        _log_step(f"[WF] tap_roi roi=({x1},{y1},{x2},{y2}) -> ({cx},{cy}) jitter=+/-{j}px{cnote if i == 0 else ''}", wf)
        if not tap(cx, cy, jitter=j):
            _log_step("[WF] tap_roi tap failed", wf)
            return False
    return True


def _step_tap_xy(step: dict, wf: dict) -> bool:
    x = int(step.get("x", 0))
    y = int(step.get("y", 0))
    j = int(step.get("jitter", getattr(s, "WORKFLOWS_TAP_JITTER_PX", 4)))
    _hm = step.get("hold_ms")
    hold_ms = int(_hm) if _hm not in (None, "") else None  # None => tapper default
    hold_note = f" hold={hold_ms}ms" if hold_ms and hold_ms > 0 else ""
    count, interval = _wf_count(step)
    cnote = f" count={count} interval={interval}s" if count > 1 else ""
    _log_step(f"[WF] tap_xy ({x},{y}) jitter=+/-{j}px{hold_note}{cnote}", wf)
    for i in range(count):
        if i > 0:
            _interruptible_sleep(interval)
            if _cancel_evt.is_set() or _stop_evt.is_set():
                return False
        if not tap(x, y, jitter=j, hold_ms=hold_ms):
            _log_step("[WF] tap_xy tap failed", wf)
            return False
    return True


def _step_swipe(step: dict, wf: dict) -> bool:
    """Drag-scroll inside an area — delegates to core/scroll.py.
    Speed presets (slow/mid/fast) come from settings.py SCROLL_* values.
    `duration_ms` and `distance_px` (optional) override the preset — the
    game's inertial scroll keys off drag distance, so longer duration /
    bigger distance = faster post-release scroll."""
    direction = str(step.get("direction", "up")).lower()
    if direction not in ("up", "down"):
        _log_step(f"[WF] swipe invalid direction '{direction}'", wf)
        return False
    area = step.get("area")
    area_t = None
    if area:
        try:
            vals = [int(v) for v in area]
        except (TypeError, ValueError):
            vals = []
        if len(vals) == 4:
            area_t = tuple(vals)
        else:
            _log_step(f"[WF] swipe invalid area {area!r} (need 4 ints) -> using default", wf)
    speed = str(step.get("speed", "mid")).lower()

    def _opt_int(key):
        v = step.get(key)
        if v in (None, ""):
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    duration_ms = _opt_int("duration_ms")
    distance_px = _opt_int("distance_px")

    extras = []
    if duration_ms is not None: extras.append(f"dur={duration_ms}ms")
    if distance_px is not None: extras.append(f"dist={distance_px}px")
    extra_s = (" " + " ".join(extras)) if extras else ""
    count, interval = _wf_count(step)
    cnote = f" count={count} interval={interval}s" if count > 1 else ""
    _log_step(f"[WF] swipe {direction} speed={speed} area={area_t}{extra_s}{cnote}", wf)
    ok = True
    for i in range(count):
        if i > 0:
            _interruptible_sleep(interval)
            if _cancel_evt.is_set() or _stop_evt.is_set():
                return False
        ok = scroll(direction, area=area_t, speed=speed,
                    duration_ms=duration_ms, distance=distance_px) and ok
    return ok


def _wf_screen(force: bool = False):
    slot = getattr(s, "WORKFLOWS_OWN_SCREEN_SLOT", "wf_scr")
    age = float(getattr(s, "WORKFLOWS_SCREEN_REUSE_AGE_S", 2.0))
    img, _, _ = get_screen(slot, max_age=(0.0 if force else age), force=force)
    return img


def _step_click_template(step: dict, wf: dict) -> bool:
    tpl_name = step.get("template", "")
    if not tpl_name:
        _log_step("[WF] click_template missing template name", wf)
        return False
    # All workflow templates live under images/workflows/
    tpl_path = f"workflows/{tpl_name}" if not tpl_name.startswith("workflows/") else tpl_name
    if not tpl_path.lower().endswith((".png", ".jpg", ".bmp")):
        tpl_path += ".png"

    use_prev = bool(step.get("use_prev_screenshot", False))
    img = _wf_screen(force=not use_prev)
    if img is None:
        _log_step("[WF] click_template no screenshot", wf)
        return False

    roi = step.get("roi")
    roi_t = tuple(int(v) for v in roi) if roi else None
    thr = float(step.get("threshold", 0.8))
    m = find_template(img, tpl_path, roi=roi_t, threshold=thr)

    if not m["found"]:
        global _last_click_template_missed
        _last_click_template_missed = True
        optional = bool(step.get("optional", False))
        msg = f"[WF] click_template '{tpl_name}' NOT found (score={m['score']:.3f} thr={thr})"
        _log_step(msg + (" [optional]" if optional else " [FAIL]"), wf)
        return optional  # optional => treat as success-skip

    ox = int(step.get("offset_x", 0))
    oy = int(step.get("offset_y", 0))
    cx = m["cx"] + ox
    cy = m["cy"] + oy
    j = int(step.get("jitter", getattr(s, "WORKFLOWS_TAP_JITTER_PX", 4)))
    _cl = step.get("clicks")
    clicks = max(1, int(_cl) if _cl not in (None, "") else 1)
    _ci = step.get("click_interval_s")
    click_interval = max(0.0, float(_ci) if _ci not in (None, "") else 0.5)
    _hm = step.get("hold_ms")
    hold_ms = int(_hm) if _hm not in (None, "") else None
    hold_note = f" hold={hold_ms}ms" if hold_ms and hold_ms > 0 else ""
    _log_step(
        f"[WF] click_template '{tpl_name}' hit (score={m['score']:.3f}) "
        f"-> tap ({cx},{cy}) offset=({ox},{oy}) jitter=+/-{j}px "
        f"clicks={clicks} interval={click_interval}s{hold_note}",
        wf,
    )
    for i in range(clicks):
        if i > 0:
            _interruptible_sleep(click_interval)
            if _cancel_evt.is_set() or _stop_evt.is_set():
                return False
        if not tap(cx, cy, jitter=j, hold_ms=hold_ms):
            _log_step(f"[WF] click_template '{tpl_name}' tap failed", wf)
            return False
    return True


def _step_click_rotating(step: dict, wf: dict) -> bool:
    """Like click_template, but the template is matched against N rotated
    copies (cached in RAM via core/rotation_cache). Used for in-game
    elements that spin around their own axis (e.g. star-sign templates
    under images/workflows/stargazing/).

    Click point = bbox center of the best-scoring rotation, in screen
    coords; offsets are NOT rotated with the template.

    log_mode (per-step): 'both' | 'hit_only' | 'miss_only' | 'none'
    Gates whether the hit/miss line is emitted at all. The workflow's
    log_level_step still controls FULL/TXT/UI routing as usual.
    """
    tpl_name = step.get("template", "")
    if not tpl_name:
        _log_step("[WF] click_rotating missing template name", wf)
        return False
    tpl_path = f"workflows/{tpl_name}" if not tpl_name.startswith("workflows/") else tpl_name
    if not tpl_path.lower().endswith((".png", ".jpg", ".bmp")):
        tpl_path += ".png"

    use_prev = bool(step.get("use_prev_screenshot", False))
    img = _wf_screen(force=not use_prev)
    if img is None:
        _log_step("[WF] click_rotating no screenshot", wf)
        return False

    roi = step.get("roi")
    roi_t = tuple(int(v) for v in roi) if roi else None
    thr = float(step.get("threshold", 0.8))
    _rot = step.get("rotations")
    rotations = max(1, int(_rot) if _rot not in (None, "") else 24)
    mask_mode = str(step.get("mask", "circle")).lower()
    _ds = step.get("downscale")
    downscale = max(1, int(_ds) if _ds not in (None, "") else 2)

    log_mode = str(step.get("log_mode", "both")).lower()
    log_hit = log_mode in ("both", "hit_only")
    log_miss = log_mode in ("both", "miss_only")

    m = find_template_rotating(img, tpl_path, roi=roi_t,
                                threshold=thr, rotations=rotations,
                                early_exit=True, mask_mode=mask_mode,
                                downscale=downscale)

    if not m["found"]:
        global _last_click_template_missed
        _last_click_template_missed = True
        optional = bool(step.get("optional", False))
        if log_miss:
            reason = m.get("reason") or ""
            reason_s = f" reason={reason}" if reason else ""
            _log_step(
                f"[WF] click_rotating '{tpl_name}' NOT found "
                f"(best_score={m['score']:.3f} thr={thr} "
                f"best_angle={m['angle']:.1f}° rotations={rotations}){reason_s}"
                + (" [optional]" if optional else " [FAIL]"),
                wf,
            )
        return optional

    ox = int(step.get("offset_x", 0))
    oy = int(step.get("offset_y", 0))
    cx = m["cx"] + ox
    cy = m["cy"] + oy
    j = int(step.get("jitter", getattr(s, "WORKFLOWS_TAP_JITTER_PX", 4)))
    _cl = step.get("clicks")
    clicks = max(1, int(_cl) if _cl not in (None, "") else 1)
    _ci = step.get("click_interval_s")
    click_interval = max(0.0, float(_ci) if _ci not in (None, "") else 0.5)
    _hm = step.get("hold_ms")
    hold_ms = int(_hm) if _hm not in (None, "") else None
    hold_note = f" hold={hold_ms}ms" if hold_ms and hold_ms > 0 else ""
    if log_hit:
        _log_step(
            f"[WF] click_rotating '{tpl_name}' hit @angle={m['angle']:.1f}° "
            f"(score={m['score']:.3f} tried={m['rotations_tried']}/{rotations}) "
            f"-> tap ({cx},{cy}) offset=({ox},{oy}) jitter=+/-{j}px "
            f"clicks={clicks} interval={click_interval}s{hold_note}",
            wf,
        )
    for i in range(clicks):
        if i > 0:
            _interruptible_sleep(click_interval)
            if _cancel_evt.is_set() or _stop_evt.is_set():
                return False
        if not tap(cx, cy, jitter=j, hold_ms=hold_ms):
            _log_step(f"[WF] click_rotating '{tpl_name}' tap failed", wf)
            return False
    return True


def _step_wait(step: dict, wf: dict) -> bool:
    secs = float(step.get("seconds", 0.0))
    _log_step(f"[WF] wait {secs}s", wf)
    _interruptible_sleep(secs)
    return True


def _step_rainbow_check(step: dict, wf: dict) -> bool:
    """Detect Rainbow Floor via HSV saturation + hue diversity.

    Required fields:
        roi                     [x1,y1,x2,y2]
    Optional:
        sat_min                 S threshold (0..255, default 180)
        val_min                 V threshold (0..255, default 150)
        min_sat_pixels          min. saturated pixel count (default 40000)
        min_hue_buckets         min. active hue buckets (default 5)
        min_pixels_per_bucket   pixels for bucket to count (default 200)
        hue_buckets             number of buckets over 0..180 (default 12)
        optional                True => miss treated as "ok" (default False: miss => fail => WF aborts)
        use_prev_screenshot     reuse cached color PNG instead of fresh pull
    """
    roi = step.get("roi")
    if not roi or len(roi) != 4:
        _log_step("[WF] rainbow_check missing roi", wf)
        return False

    # Get color from the same validated snapshot; never re-read a stale file
    # after a failed capture.
    slot = getattr(s, "WORKFLOWS_OWN_SCREEN_SLOT", "wf_scr")
    age = float(getattr(s, "WORKFLOWS_SCREEN_REUSE_AGE_S", 2.0))
    use_prev = bool(step.get("use_prev_screenshot", False))
    img, _, _ = get_screen(slot, max_age=(0.0 if not use_prev else age),
                           force=not use_prev, color=True)
    if img is None:
        _log_step("[WF] rainbow_check no screenshot", wf)
        return False

    x1, y1, x2, y2 = [int(v) for v in roi]
    h_img, w_img = img.shape[:2]
    x1 = max(0, min(x1, w_img)); x2 = max(x1, min(x2, w_img))
    y1 = max(0, min(y1, h_img)); y2 = max(y1, min(y2, h_img))
    if x2 <= x1 or y2 <= y1:
        _log_step(f"[WF] rainbow_check invalid ROI {roi}", wf)
        return False

    crop = img[y1:y2, x1:x2]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

    def _num(key, default, caster=float):
        v = step.get(key)
        if v is None or v == "":
            return caster(default)
        try:
            return caster(v)
        except (TypeError, ValueError):
            return caster(default)

    sat_min = _num("sat_min", 180, int)
    val_min = _num("val_min", 150, int)
    min_sat_pixels = _num("min_sat_pixels", 40000, int)
    min_hue_buckets = _num("min_hue_buckets", 5, int)
    min_per_bucket = _num("min_pixels_per_bucket", 200, int)
    n_buckets = _num("hue_buckets", 12, int)
    min_hue_entropy = _num("min_hue_entropy", 1.5, float)

    mask = (hsv[..., 1] >= sat_min) & (hsv[..., 2] >= val_min)
    sat_count = int(mask.sum())
    hues = hsv[..., 0][mask]
    edges = np.linspace(0, 180, n_buckets + 1)
    counts, _ = np.histogram(hues, bins=edges)
    active = int((counts >= min_per_bucket).sum())

    # Shannon entropy over the hue histogram: rainbows spread across all
    # buckets (high entropy); colorful-but-concentrated scenes (flowers,
    # single-color objects) stay low even when total sat_px is high.
    probs = counts.astype(np.float64)
    if probs.sum() > 0:
        probs /= probs.sum()
        nz = probs[probs > 0]
        entropy = float(-(nz * np.log2(nz)).sum())
    else:
        entropy = 0.0

    found = (
        sat_count >= min_sat_pixels
        and active >= min_hue_buckets
        and entropy >= min_hue_entropy
    )
    _log_step(
        f"[WF] rainbow_check sat_px={sat_count} (thr={min_sat_pixels}) "
        f"buckets={active} (thr={min_hue_buckets}) "
        f"entropy={entropy:.3f} (thr={min_hue_entropy:.2f}) "
        f"-> {'RAINBOW' if found else 'no rainbow'}",
        wf,
    )
    if found:
        return True
    optional = bool(step.get("optional", False))
    return optional  # miss: optional => skip ok, else => fail => abort WF


def _step_call_workflow(step: dict, wf: dict) -> bool:
    """Run another workflow (including inactive ones) inline.

    Fields:
        target     slug of the target workflow
    Target failure propagates (aborts caller).
    """
    target = str(step.get("target", "")).strip()
    if not target:
        _log_step("[WF] call_workflow missing target", wf)
        return False
    tgt_wf = cfg_wf.WORKFLOWS.get(target)
    if not tgt_wf:
        _log_step(f"[WF] call_workflow unknown target '{target}'", wf)
        return False

    max_depth = int(getattr(s, "WORKFLOWS_MAX_CALL_DEPTH", 5))
    if len(_call_stack) >= max_depth:
        _log_step(f"[WF] call_workflow max depth {max_depth} reached -> abort", wf)
        return False
    if target in _call_stack:
        _log_step(f"[WF] call_workflow recursion detected ({'->'.join(_call_stack + [target])}) -> abort", wf)
        return False

    _log_step(f"[WF] call_workflow -> '{target}' (depth={len(_call_stack) + 1})", wf)
    _call_stack.append(target)
    try:
        # The outer WF holds the action lock for its entire duration; the
        # nested call runs under that same lock (see _run_workflow).
        result = _run_workflow(target, tgt_wf, manual=False)
    finally:
        _call_stack.pop()

    if result == "ok":
        return True
    _log_step(f"[WF] call_workflow '{target}' ended with '{result}' -> caller aborts", wf)
    return False


def _step_hold_and_wiggle(step: dict, wf: dict) -> bool:
    """Chain many short swipes inside ROI to approximate a held-finger wiggle.

    We cannot truly keep the finger down across `adb input swipe` calls, so we
    chain swipes back-to-back: the endpoint of swipe N becomes the start of
    swipe N+1, with no gap. Most games treat rapid re-touch as a continuous
    drag.

    Fields:
        roi             [x1,y1,x2,y2]
        duration_s      total wiggle duration (default 5.0)
        step_ms         per-swipe duration (default 200)
        max_step_px     max random step size (default 120)
    """
    roi = step.get("roi")
    if not roi or len(roi) != 4:
        _log_step("[WF] hold_and_wiggle missing roi", wf)
        return False
    x1, y1, x2, y2 = [int(v) for v in roi]
    if x2 <= x1 or y2 <= y1:
        _log_step(f"[WF] hold_and_wiggle invalid ROI {roi}", wf)
        return False

    def _n(k, d, cast):
        v = step.get(k)
        if v is None or v == "":
            return cast(d)
        try:
            return cast(v)
        except (TypeError, ValueError):
            return cast(d)
    total = max(0.1, _n("duration_s", 5.0, float))
    step_ms = max(30, _n("step_ms", 200, int))
    max_step = max(10, _n("max_step_px", 120, int))

    # Start near center of ROI
    cx = (x1 + x2) // 2 + random.randint(-20, 20)
    cy = (y1 + y2) // 2 + random.randint(-20, 20)
    cx = max(x1, min(x2, cx))
    cy = max(y1, min(y2, cy))

    _log_step(
        f"[WF] hold_and_wiggle roi=({x1},{y1},{x2},{y2}) duration={total}s "
        f"step_ms={step_ms} max_step={max_step}px",
        wf,
    )

    # Per iteration: pick a uniformly-random target point anywhere in the ROI,
    # then step toward it at most `max_step_px` — ensures full-ROI coverage
    # (pure delta-walks bias toward the center because reflecting boundaries).
    end_ts = time.monotonic() + total
    swipes = 0
    tgt_x = random.randint(x1, x2)
    tgt_y = random.randint(y1, y2)
    while time.monotonic() < end_ts:
        if _cancel_evt.is_set() or _stop_evt.is_set():
            break
        # Re-pick target if we're close to the current one
        dx = tgt_x - cx
        dy = tgt_y - cy
        dist = (dx * dx + dy * dy) ** 0.5
        if dist < max_step * 0.5:
            tgt_x = random.randint(x1, x2)
            tgt_y = random.randint(y1, y2)
            dx = tgt_x - cx
            dy = tgt_y - cy
            dist = (dx * dx + dy * dy) ** 0.5 or 1.0
        # Cap step length to max_step_px
        if dist > max_step:
            scale = max_step / dist
            nx = int(cx + dx * scale)
            ny = int(cy + dy * scale)
        else:
            nx = tgt_x
            ny = tgt_y
        nx = max(x1, min(x2, nx))
        ny = max(y1, min(y2, ny))
        try:
            adb("shell", "input", "swipe", str(cx), str(cy), str(nx), str(ny), str(step_ms))
        except Exception as e:
            _log_step(f"[WF] hold_and_wiggle adb error: {e}", wf)
            return False
        cx, cy = nx, ny
        swipes += 1
    _log_step(f"[WF] hold_and_wiggle done ({swipes} swipes)", wf)
    return True


_STEP_EXECUTORS = {
    "tap_roi": _step_tap_roi,
    "tap_xy": _step_tap_xy,
    "swipe": _step_swipe,
    "click_template": _step_click_template,
    "click_rotating": _step_click_rotating,
    "wait": _step_wait,
    "rainbow_check": _step_rainbow_check,
    "call_workflow": _step_call_workflow,
    "hold_and_wiggle": _step_hold_and_wiggle,
}


# ============================================================
#  If / ElseIf / Else — condition evaluator
# ============================================================
#
# "If" steps are block-steps with shape:
#   {
#     "type": "if",
#     "_disabled": False,
#     "on_missing_template": "false" | "fail_wf",
#     "branches": [
#       {"condition": {...}, "steps": [...]},   # if
#       {"condition": {...}, "steps": [...]},   # elseif (0..n)
#     ],
#     "else_steps": [...],                      # optional
#   }
#
# Supported condition kinds:
#   - template_visible / template_not_visible  {roi, template, threshold}
#   - level_eq / level_gte / level_lte         {value}
#   - last_step_ok / last_step_failed          (no args)
#
# Nesting: max depth 1. An if-step appearing inside a branch is logged and
# skipped (depth>0 => no further nesting).
#
# on_missing_template:
#   "false"   (default) — template_* cond with missing template counts as False
#   "fail_wf"           — such a miss aborts the whole workflow with "error"

def _eval_condition(cond: dict, wf: dict, last_ok: bool, on_missing: str):
    """Return (result: bool, abort: bool).
    abort=True requests WF abort (only triggered when on_missing='fail_wf'
    AND a template_* condition references a template that cannot be matched)."""
    if not isinstance(cond, dict):
        return False, False
    kind = str(cond.get("kind", "")).strip()

    if kind == "last_step_ok":
        return bool(last_ok), False
    if kind == "last_step_failed":
        return (not bool(last_ok)), False

    if kind in ("level_eq", "level_gte", "level_lte"):
        cur = getattr(state, "current_level", None)
        if cur is None:
            return False, False
        try:
            v = int(cond.get("value"))
        except (TypeError, ValueError):
            return False, False
        if kind == "level_eq":
            return (int(cur) == v), False
        if kind == "level_gte":
            return (int(cur) >= v), False
        if kind == "level_lte":
            return (int(cur) <= v), False

    if kind in ("template_visible", "template_not_visible"):
        tpl_name = str(cond.get("template", "")).strip()
        if not tpl_name:
            return False, (on_missing == "fail_wf")
        tpl_path = tpl_name if tpl_name.startswith("workflows/") else f"workflows/{tpl_name}"
        if not tpl_path.lower().endswith((".png", ".jpg", ".bmp")):
            tpl_path += ".png"
        img = _wf_screen(force=True)
        if img is None:
            return False, (on_missing == "fail_wf")
        roi = cond.get("roi")
        roi_t = tuple(int(v) for v in roi) if roi else None
        thr = float(cond.get("threshold", 0.8))
        m = find_template(img, tpl_path, roi=roi_t, threshold=thr)
        found = bool(m.get("found"))
        if kind == "template_visible":
            return found, False
        return (not found), False

    # Unknown kind -> False, don't abort
    return False, False


def _describe_condition(cond: dict) -> str:
    if not isinstance(cond, dict):
        return "<invalid>"
    k = cond.get("kind", "?")
    if k in ("template_visible", "template_not_visible"):
        return f"{k}('{cond.get('template','')}' thr={cond.get('threshold',0.8)})"
    if k in ("level_eq", "level_gte", "level_lte"):
        return f"{k}({cond.get('value')})"
    return str(k)


# ============================================================
#  Workflow execution
# ============================================================

def _run_step_list(slug: str, wf: dict, steps: list, depth: int, last_ok_ref: list) -> str:
    """Execute a list of steps. Handles the 'if' block-step inline.
    last_ok_ref is a single-element list used as a mutable reference to the
    'last functional step ok' flag — shared across nested branches and the
    outer loop so `last_step_ok` conditions reflect the prior regular step.
    Returns: "ok" | "cancelled" | "error"
    """
    for idx, step in enumerate(steps, 1):
        if _cancel_evt.is_set() or _stop_evt.is_set():
            _log(f"[WF:{slug}] cancelled at step {idx}/{len(steps)} (depth={depth})", wf)
            return "cancelled"
        if not isinstance(step, dict):
            _log_step(f"[WF:{slug}] step {idx} is invalid ({type(step).__name__}) -> skip", wf)
            continue
        if step.get("_disabled"):
            continue

        stype = str(step.get("type", "")).strip()

        # ---- If/ElseIf/Else block ----
        if stype == "if":
            if depth >= 1:
                _log_step(f"[WF:{slug}] nested 'if' at depth {depth} not allowed (max depth 1) -> skip", wf)
                continue
            on_missing = str(step.get("on_missing_template", "false")).lower()
            branches = step.get("branches") or []
            matched = None
            for bi, br in enumerate(branches):
                cond = br.get("condition") if isinstance(br, dict) else None
                result, abort = _eval_condition(cond or {}, wf, bool(last_ok_ref[0]), on_missing)
                if abort:
                    _log_step(f"[WF:{slug}] if-step: template missing with on_missing_template='fail_wf' -> abort", wf)
                    return "error"
                if result:
                    label = "if" if bi == 0 else f"elseif#{bi}"
                    _log_step(f"[WF:{slug}] if-step: branch '{label}' matched [{_describe_condition(cond or {})}]", wf)
                    matched = br
                    break
            if matched is not None:
                sub = matched.get("steps") or []
            else:
                sub = step.get("else_steps") or []
                if sub:
                    _log_step(f"[WF:{slug}] if-step: no branch matched, entering else", wf)
                else:
                    _log_step(f"[WF:{slug}] if-step: no branch matched, no else -> skip", wf)

            if sub:
                sub_result = _run_step_list(slug, wf, sub, depth + 1, last_ok_ref)
                if sub_result != "ok":
                    return sub_result

            sleep_after = float(step.get("sleep_after", 0.0))
            if sleep_after > 0:
                _interruptible_sleep(sleep_after)
            continue

        # ---- Regular step ----
        executor = _STEP_EXECUTORS.get(stype)
        if executor is None:
            _log_step(f"[WF:{slug}] unknown step type '{stype}' -> skip", wf)
            continue

        global _last_click_template_missed
        _last_click_template_missed = False
        try:
            ok = executor(step, wf)
        except Exception as exc:
            _log_step(f"[WF:{slug}] step {idx} ({stype}) failed: {type(exc).__name__}: {exc}", wf)
            return "error"
        if _cancel_evt.is_set() or _stop_evt.is_set():
            return "cancelled"

        # functional_ok semantics: click_template with optional+miss returns
        # True (no fail) but is NOT functionally ok.
        functional_ok = bool(ok) and not _last_click_template_missed
        last_ok_ref[0] = functional_ok

        if not ok:
            _log_step(f"[WF:{slug}] step {idx} ({stype}) reported failure -> abort", wf)
            return "error"

        sleep_after = float(step.get("sleep_after", 0.0))
        if sleep_after > 0:
            _interruptible_sleep(sleep_after)

    return "cancelled" if _cancel_evt.is_set() or _stop_evt.is_set() else "ok"


def _run_workflow(slug: str, wf: dict, manual: bool = False) -> str:
    """Execute all enabled steps of `wf`. Holds the action lock for the
    entire workflow so freebies/lootbug cannot interleave between steps.
    Nested call_workflow runs under the same held lock (no re-acquire).
    Returns: "ok" | "busy" | "no_game" | "cancelled" | "error"
    """
    if not is_game_running():
        _log(f"[WF:{slug}] game not running -> skipping", wf)
        return "no_game"

    top_steps = [st for st in wf.get("steps", []) if isinstance(st, dict) and not st.get("_disabled")]
    if not top_steps:
        _log(f"[WF:{slug}] no enabled steps -> skip", wf)
        return "ok"

    lock = getattr(state, "ingame_action_lock", None)
    # Nested call_workflow path: the outer WF already holds the lock on this
    # thread, so we must not try to acquire it again (threading.Lock is not
    # reentrant). Detect nesting via _call_stack.
    # `ignore_action_lock` (per-WF override): bypass acquire entirely so this
    # WF can run concurrently with feature daemon threads (Freebies/Lootbug).
    # Intended for tiny defensive WFs only — see WF editor tooltip.
    owns_lock = False
    ignore_lock = bool(wf.get("ignore_action_lock", False))
    if ignore_lock:
        _log(f"[WF:{slug}] override: ignoring action lock", wf)
    elif lock is not None and not _call_stack:
        if not lock.acquire(blocking=False):
            _log_busy(f"[WF:{slug}] postponed — another feature busy", wf)
            return "busy"
        owns_lock = True

    _log(f"[WF:{slug}] starting ({len(top_steps)} step(s){', manual' if manual else ''})", wf)
    with state.workflows_lock:
        prev_running = getattr(state, "workflows_running", None)
        state.workflows_running = slug

    try:
        last_ok_ref = [False]  # mutable ref shared with _run_step_list + branches
        result = _run_step_list(slug, wf, top_steps, depth=0, last_ok_ref=last_ok_ref)
        if result == "ok":
            _log(f"[WF:{slug}] completed", wf)
        return result
    finally:
        with state.workflows_lock:
            state.workflows_running = prev_running
        if owns_lock:
            lock.release()


# ============================================================
#  Scheduler core
# ============================================================

def _interruptible_sleep(seconds: float):
    """Wake on stop/master-cancel. Used between steps and as scheduler tick."""
    if seconds <= 0:
        return
    end = time.monotonic() + seconds
    while True:
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        if _stop_evt.is_set() or _cancel_evt.is_set():
            return
        # Slice into ≤0.5s chunks so cancel propagates promptly
        _wake_evt.wait(timeout=min(0.5, remaining))
        if _wake_evt.is_set():
            _wake_evt.clear()
            return


def _next_due(wf: dict) -> float:
    interval = float(wf.get("interval_s", 60.0))
    var = wf.get("interval_variance_pct")
    if var is None:
        var = float(getattr(s, "WF_INTERVAL_VARIANCE_PCT", 0.0))
    var = max(0.0, float(var))
    if var > 0:
        factor = 1.0 + random.uniform(-var, var) / 100.0
        interval = max(1.0, interval * factor)
    return time.time() + interval


@_with_state_lock
def _ensure_runtime_entry(slug: str, wf: dict):
    if slug not in state.workflows:
        state.workflows[slug] = _new_runtime_entry(wf)


def _new_runtime_entry(wf):
    return {"enabled": bool(wf.get("enabled_default", False)), "next_due_ts": 0.0,
            "last_run_ts": 0.0, "run_count": 0, "last_status": ""}


@_with_state_lock
def _eligible_workflows():
    """Return list of (slug, wf, runtime) for WFs that may auto-run."""
    out = []
    for slug, wf in cfg_wf.WORKFLOWS.items():
        if not isinstance(wf, dict):
            continue
        if wf.get("inactive"):
            continue
        _ensure_runtime_entry(slug, wf)
        rt = state.workflows[slug]
        if not rt["enabled"]:
            continue
        out.append((slug, wf, rt))
    return out


def _drain_manual_queue():
    with _manual_lock:
        items = list(_manual_queue)
        _manual_queue.clear()
    return items


def _scheduler_tick():
    # This boundary belongs exclusively to the worker; nested calls and all
    # result accounting from the previous tick have finished before reload.
    _apply_pending_reload()
    if _reload_evt.is_set():
        return  # another reload arrived while the candidate was being loaded
    # 1) Manual triggers first (already validated when enqueued).
    manual_items = _drain_manual_queue()
    for index, slug in enumerate(manual_items):
        wf = cfg_wf.WORKFLOWS.get(slug)
        if not wf:
            continue
        with state.workflows_lock:
            _ensure_runtime_entry(slug, wf)
            rt = state.workflows[slug]
        result = _run_workflow(slug, wf, manual=True)
        with state.workflows_lock:
            rt["last_status"] = result
            rt["last_run_ts"] = time.time()
            if result == "ok":
                rt["run_count"] = rt.get("run_count", 0) + 1
        if _cancel_evt.is_set():
            return
        if _reload_evt.is_set():
            with _manual_lock:
                _manual_queue[:0] = manual_items[index + 1:]
            return

    # 2) Auto runs: collect due, FIFO by next_due_ts
    if not state.workflows_master_enabled:
        return

    now = time.time()
    due = []
    with state.workflows_lock:
        for slug, wf, rt in _eligible_workflows():
            nxt = rt.get("next_due_ts", 0.0)
            if nxt <= 0.0:
                # First seen since enable -> schedule
                rt["next_due_ts"] = _next_due(wf)
                continue
            if nxt <= now:
                due.append((nxt, slug, wf, rt))
    due.sort(key=lambda t: t[0])

    for _, slug, wf, rt in due:
        if _cancel_evt.is_set() or not state.workflows_master_enabled:
            return
        with state.workflows_lock:
            if not rt.get("enabled", False):
                continue
        result = _run_workflow(slug, wf, manual=False)
        with state.workflows_lock:
            rt["last_status"] = result
            rt["last_run_ts"] = time.time()
            if result == "ok":
                rt["run_count"] = rt.get("run_count", 0) + 1
            if result == "busy":
                rt["next_due_ts"] = time.time() + float(getattr(s, "WORKFLOWS_BUSY_RETRY_S", 10.0))
            elif result == "no_game":
                rt["next_due_ts"] = time.time() + 30.0
            else:
                rt["next_due_ts"] = _next_due(wf)
        if _reload_evt.is_set():
            return


def _worker():
    _log("[WORKFLOWS] worker thread started")
    _interruptible_sleep(3.0)
    while not _stop_evt.is_set():
        try:
            _scheduler_tick()
        except Exception as e:
            _log(f"[WORKFLOWS] scheduler error: {type(e).__name__}: {e}")
        # Tick every 1s (cheap; no ADB calls here)
        _wake_evt.wait(timeout=1.0)
        if _wake_evt.is_set():
            _wake_evt.clear()


# ============================================================
#  Public API
# ============================================================

def start():
    """Start the scheduler thread (idempotent)."""
    global _thread, _thread_started
    if _thread_started:
        return
    _thread_started = True
    _stop_evt.clear()
    # Initial state: master + per-WF defaults
    state.workflows_master_enabled = bool(getattr(s, "WORKFLOWS_ENABLED_DEFAULT", False))
    for slug, wf in cfg_wf.WORKFLOWS.items():
        if isinstance(wf, dict):
            _ensure_runtime_entry(slug, wf)
    _thread = threading.Thread(target=_worker, daemon=True, name="workflows-worker")
    _thread.start()


@_with_state_lock
def toggle_master() -> bool:
    """Flip master switch. Off => cancel any in-progress WF cooperatively."""
    new = not bool(getattr(state, "workflows_master_enabled", False))
    state.workflows_master_enabled = new
    if new:
        _cancel_evt.clear()
        # Re-arm next_due for enabled WFs that were sitting idle
        for slug, wf in cfg_wf.WORKFLOWS.items():
            if isinstance(wf, dict):
                _ensure_runtime_entry(slug, wf)
                if state.workflows[slug]["enabled"]:
                    state.workflows[slug]["next_due_ts"] = _next_due(wf)
        _wake_evt.set()
    else:
        _cancel_evt.set()
        # Clear any queued manual runs
        with _manual_lock:
            _manual_queue.clear()
    _log(f"[WORKFLOWS] master toggled -> {'ON' if new else 'OFF'}")
    # When OFF, leave _cancel_evt set briefly so the running step loop sees it.
    # The scheduler clears it on next master-ON.
    return new


@_with_state_lock
def toggle_wf(slug: str) -> bool:
    """Per-WF auto toggle."""
    wf = cfg_wf.WORKFLOWS.get(slug)
    if not wf:
        return False
    _ensure_runtime_entry(slug, wf)
    rt = state.workflows[slug]
    rt["enabled"] = not bool(rt.get("enabled", False))
    if rt["enabled"]:
        rt["next_due_ts"] = _next_due(wf)
        _wake_evt.set()
    else:
        rt["next_due_ts"] = 0.0
    _log(f"[WORKFLOWS] {slug} auto -> {'ON' if rt['enabled'] else 'OFF'}")
    return rt["enabled"]


@_with_state_lock
def manual_trigger(slug: str):
    """Queue a manual run. Rejected (toast) if master OFF or WF currently running."""
    if not state.workflows_master_enabled:
        _log_busy(f"[WORKFLOWS] manual '{slug}' rejected — master OFF")
        _push_toast("Auto WF is OFF — enable it to run workflows", error=True)
        return
    if state.workflows_running is not None:
        _log_busy(f"[WORKFLOWS] manual '{slug}' rejected — '{state.workflows_running}' is busy")
        _push_toast(f"Workflow '{state.workflows_running}' is running — try again", error=True)
        return
    wf = cfg_wf.WORKFLOWS.get(slug)
    if not wf:
        _push_toast(f"Unknown workflow: {slug}", error=True)
        return
    with _manual_lock:
        _manual_queue.append(slug)
    _wake_evt.set()
    _log(f"[WORKFLOWS] manual '{slug}' queued")


def reload_workflows():
    """Request reload; only the workflow worker may publish definitions."""
    with state.workflows_lock:
        _reload_evt.set()
        state.workflows_reload_status = "pending"
        state.workflows_reload_error = ""
    # Do not set _wake_evt: that would shorten a running workflow's waits.
    _log("[WORKFLOWS] reload requested; applying at next idle scheduler boundary")


def _apply_pending_reload():
    """Worker-only; keep the active generation intact on any loading error."""
    with state.workflows_lock:
        if not _reload_evt.is_set():
            return
        _reload_evt.clear()
    try:
        candidate = cfg_wf.load_workflow_definitions()
        with state.workflows_lock:
            # Publish definitions and matching runtime as one metadata update.
            runtime = {slug: state.workflows[slug] if slug in state.workflows else _new_runtime_entry(wf)
                       for slug, wf in candidate.items()}
            with _manual_lock:
                _manual_queue[:] = [slug for slug in _manual_queue if slug in candidate]
            state.workflows = runtime
            cfg_wf.WORKFLOWS = candidate
            state.workflows_reload_status = "pending" if _reload_evt.is_set() else "applied"
            state.workflows_reload_error = ""
        _log("[WORKFLOWS] reload completed")
    except Exception as e:
        message = f"{type(e).__name__}: {e}"
        with state.workflows_lock:
            state.workflows_reload_status = "pending" if _reload_evt.is_set() else "error"
            state.workflows_reload_error = message
        _log(f"[WORKFLOWS] reload failed; keeping active definitions: {message}")
