# core/game_state.py - Game-running detection
"""
Detects whether the Idle Obelisk Miner game is in the foreground by matching
`images/game_running.png` inside a small ROI on the latest screenshot.

Reuses the youngest valid full screenshot from RUNNING_ACCEPT_SLOTS when
younger than RUNNING_CHECK_CACHE_AGE_S, otherwise captures its own game_scr.
Updates `config.app_state.game_running` as a side effect so the WebUI
status badge reflects reality.
"""
import threading

import config.app_state as state
import config.settings as s
from core.screen_cache import get_screen, get_latest_cached_screen
from core.vision import find_template
from core.file_logger import bot_log


_GAME_SCR_SLOT = "game_scr"
_check_lock = threading.Lock()


def is_game_running(force: bool = False) -> bool:
    """Match game_running.png in the configured ROI. Updates state.game_running.

    - force  ignore the screenshot cache (pull a fresh frame)
    """
    with _check_lock:
        return _check_game_running(force)


def _check_game_running(force: bool) -> bool:
    level = getattr(s, "RUNNING_LOG_LEVEL", "FULL")
    max_age = float(getattr(s, "RUNNING_CHECK_CACHE_AGE_S", 5.0))
    roi = tuple(getattr(s, "RUNNING_ROI", (8, 3, 48, 43)))
    threshold = float(getattr(s, "RUNNING_MATCH_THRESHOLD", 0.8))
    tpl = getattr(s, "RUNNING_TEMPLATE", "game_running.png")
    accept_slots = list(getattr(s, "RUNNING_ACCEPT_SLOTS", [_GAME_SCR_SLOT]))

    img = None
    source = "fresh:game_scr"
    if not force:
        img, _, _, slot, age = get_latest_cached_screen(accept_slots, max_age)
        if img is not None:
            source = f"cache:{slot} age={age:.3f}s"

    if img is None:
        img, _, _ = get_screen(_GAME_SCR_SLOT, max_age=max_age, force=True)
    if img is None:
        if state.game_running:
            bot_log("[RUNNING] screenshot capture failed after retries -> marking STOPPED "
                    "(game stop unconfirmed; see [SCREENSHOT] failure details)", level)
        state.game_running = False
        return False

    m = find_template(img, tpl, roi=roi, threshold=threshold)
    running = bool(m["found"])

    if running != state.game_running:
        bot_log(
            f"[RUNNING] state change: {state.game_running} -> {running} "
            f"(score={m['score']:.3f} thr={threshold} source={source})",
            level,
        )
    state.game_running = running
    return running
