"""Independent notice capture/dismiss worker; no OCR or import-time ADB calls."""
import random
import threading
import time

import config.app_state as state
import config.settings as s
from core.notice_archive import NoticeArchive
from core.notice_detection import detect_notice
from core.screen_cache import get_cached_screen, get_screen
from core.tapper import tap
from core.game_state import is_game_running
from core.file_logger import bot_log

archive = NoticeArchive(s.TEMP_DIR / "notices")
_wake = threading.Event()
_thread = None
_generation = 0


def _active(generation):
    return state.notices_enabled and generation == _generation


def _image(fresh=False):
    if not fresh:
        image, _, _ = get_cached_screen("game_scr", max_age=s.NOTICES_SCREEN_REUSE_AGE_S, color=True)
        if image is not None:
            return image
    image, _, _ = get_screen("notices_scr", max_age=0, force=True, color=True)
    if image is None:
        raise OSError("Notice screenshot unavailable; stale fallback disabled")
    return image


def inspect(image):
    return detect_notice(image, s.NOTICES_DETECT_ROI, s.BASE_DIR / "images",
                         s.NOTICES_TEMPLATE_GLOB, s.NOTICES_MATCH_THRESHOLD)


def _cycle():
    generation = _generation
    if not state.ingame_action_lock.acquire(blocking=False):
        state.notices_status = "Waiting for another feature"
        return "retry"
    try:
        if not _active(generation):
            return "off"
        if not is_game_running():
            state.notices_status = "Waiting for game"
            return "retry"
        # Acquire action lock before checking cache age, never before a long wait.
        image = _image()
        count = 0
        while _active(generation):
            match = inspect(image)
            if not _active(generation):
                return "off"
            state.notices_last_score = match["score"]
            state.notices_last_scan_ts = time.time()
            if not match["found"]:
                archive.clear_pending()
                state.notices_status = "No notices found"
                return "ok"
            if count >= s.NOTICES_MAX_PER_CYCLE:
                state.notices_status = "More notices pending"
                return "retry"
            x1, y1, x2, y2 = match["roi"]
            ix1, iy1, ix2, iy2 = match["identity_roi"]
            identifier, attempted = archive.prepare(image[y1:y2, x1:x2], match["variant"],
                                                     s.NOTICES_MAX_ARCHIVE_MB,
                                                     identity=image[iy1:iy2, ix1:ix2])
            if attempted:
                state.notices_status = "Unchanged notice; waiting without another tap"
                return "retry"
            if not _active(generation):
                return "off"
            h, w = image.shape[:2]
            j = s.NOTICES_TAP_JITTER_PX
            if not (j <= s.NOTICES_TAP_X < w - j and j <= s.NOTICES_TAP_Y < h - j):
                raise ValueError("Notice tap position and jitter must fit inside the screenshot")
            archive.mark_attempted(identifier)
            if not tap(s.NOTICES_TAP_X, s.NOTICES_TAP_Y, jitter=j):
                raise OSError("Notice tap failed; unchanged image will not be clicked again")
            state.notices_clicked_count += 1
            count += 1
            bot_log(f"[NOTICES] saved {match['variant']} ({identifier}); tap sent", s.NOTICES_LOG_LEVEL)
            state.notices_status = "Checking next notice"
            # A wake event from activation must not skip the animation delay.
            deadline = time.monotonic() + s.NOTICES_POST_CLICK_DELAY_S
            while _active(generation) and time.monotonic() < deadline:
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))
            if not _active(generation):
                return "off"
            image = _image(fresh=True)
        return "off"
    finally:
        state.ingame_action_lock.release()


def _worker():
    while True:
        _wake.clear()
        generation = _generation
        if not state.notices_enabled:
            state.notices_next_check_ts = 0.0
            _wake.wait()
            _wake.clear()
            continue
        try:
            state.notices_error = ""
            result = _cycle()
        except Exception as exc:
            state.notices_error = f"{type(exc).__name__}: {exc}"
            state.notices_status = "Retry required"
            bot_log(f"[NOTICES] {state.notices_error}", s.NOTICES_LOG_LEVEL)
            result = "retry"
        if generation != _generation:
            continue
        if not state.notices_enabled:
            continue
        delay = _next_delay(result)
        state.notices_next_check_ts = time.time() + delay
        _wake.wait(delay)
        _wake.clear()


def _next_delay(result):
    if result != "ok":
        return s.NOTICES_RETRY_S
    variance = s.NOTICES_INTERVAL_VARIANCE_PCT / 100
    return max(0.1, s.NOTICES_CHECK_INTERVAL_S * random.uniform(1 - variance, 1 + variance))


def start():
    global _thread
    if _thread is None:
        _thread = threading.Thread(target=_worker, name="notices-worker", daemon=True)
        _thread.start()


def toggle():
    global _generation
    _generation += 1
    state.notices_enabled = not state.notices_enabled
    state.notices_next_check_ts = 0.0
    state.notices_error = ""
    state.notices_status = "Ready" if state.notices_enabled else "Off"
    _wake.set()
    return state.notices_enabled
