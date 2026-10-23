# core/game_state.py - Game-running detection
"""
Detects whether the Idle Obelisk Miner game is in the foreground by matching
`images/game_running.png` inside a small ROI on the latest screenshot.

Reuses the cached screenshot (./temp/game_scr.png) if it's younger than
RUNNING_CHECK_CACHE_AGE_S to avoid hammering ADB — our callers may poll this.
Updates `config.app_state.game_running` as a side effect so the WebUI
status badge reflects reality.
"""
import os
import time

import cv2

import config.app_state as state
import config.settings as s
from core.screen_cache import get_screen, screen_path
from core.vision import find_template
from core.file_logger import bot_log


_GAME_SCR_SLOT = "game_scr"


def _youngest_fresh_slot(slots, max_age: float):
    """Return (slot, age) of the youngest slot with age < max_age, else (None, None)."""
    now = time.time()
    best = None
    for slot in slots:
        path = screen_path(slot)
        if not os.path.exists(path):
            continue
        age = now - os.path.getmtime(path)
        if age >= max_age:
            continue
        if best is None or age < best[1]:
            best = (slot, age)
    return best if best else (None, None)


def is_game_running(force: bool = False) -> bool:
    """Match game_running.png in the configured ROI. Updates state.game_running.

    - force  ignore the screenshot cache (pull a fresh frame)
    """
    level = getattr(s, "RUNNING_LOG_LEVEL", "FULL")
    max_age = float(getattr(s, "RUNNING_CHECK_CACHE_AGE_S", 5.0))
    roi = tuple(getattr(s, "RUNNING_ROI", (8, 3, 48, 43)))
    threshold = float(getattr(s, "RUNNING_MATCH_THRESHOLD", 0.8))
    tpl = getattr(s, "RUNNING_TEMPLATE", "game_running.png")
    accept_slots = list(getattr(s, "RUNNING_ACCEPT_SLOTS", [_GAME_SCR_SLOT]))

    img = None
    if not force:
        slot, _age = _youngest_fresh_slot(accept_slots, max_age)
        if slot is not None:
            img = cv2.imread(screen_path(slot), cv2.IMREAD_GRAYSCALE)

    if img is None:
        img, _, _ = get_screen(_GAME_SCR_SLOT, max_age=max_age, force=force)
    if img is None:
        if state.game_running:
            bot_log("[RUNNING] no screenshot available -> marking STOPPED", level)
        state.game_running = False
        return False

    m = find_template(img, tpl, roi=roi, threshold=threshold)
    running = bool(m["found"])

    if running != state.game_running:
        bot_log(
            f"[RUNNING] state change: {state.game_running} -> {running} "
            f"(score={m['score']:.3f} thr={threshold})",
            level,
        )
    state.game_running = running
    return running
