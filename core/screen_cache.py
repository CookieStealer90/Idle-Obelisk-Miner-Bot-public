# core/screen_cache.py - Screenshot pulling with per-slot freshness cache
"""
Central screenshot cache for the Idle Obelisk Miner Bot.

Every feature that needs a screen should ask via `get_screen(slot, max_age)`:
    img, w, h = get_screen("freebie_scr", max_age=5.0)

Pulled PNGs live in ./temp/<slot>.png. If the file on disk is newer than
`max_age` seconds, we skip the ADB pull and reuse it — saving round-trips
for features that poll close together (e.g. game-running detection).

Each slot is independent: different features with different staleness needs
won't share a cached frame they didn't ask for.
"""
import os
import time

import cv2

from config.settings import BASE_DIR, REMOTE_SCREEN
from core.adb_helper import adb

TEMP_DIR = os.path.join(str(BASE_DIR), "temp")


def _ensure_temp_dir():
    os.makedirs(TEMP_DIR, exist_ok=True)


def _slot_path(slot: str) -> str:
    _ensure_temp_dir()
    return os.path.join(TEMP_DIR, f"{slot}.png")


def _pull_screen(local_path: str):
    adb("shell", "screencap", "-p", REMOTE_SCREEN)
    adb("pull", REMOTE_SCREEN, local_path)
    adb("shell", "rm", REMOTE_SCREEN)


def get_screen(slot: str, max_age: float = 5.0, force: bool = False):
    """Return (gray_img, width, height) for the given slot.

    - slot      filename stem under ./temp/ (e.g. "freebie_scr")
    - max_age   reuse on-disk PNG if its mtime is within `max_age` seconds
    - force     ignore cache and pull fresh

    Returns (None, 0, 0) if ADB pull failed and no cached file exists.
    """
    path = _slot_path(slot)
    now = time.time()
    reuse = False
    if not force and os.path.exists(path):
        age = now - os.path.getmtime(path)
        if age < max_age:
            reuse = True

    if not reuse:
        try:
            _pull_screen(path)
        except Exception:
            # Fall back to whatever is on disk — may be stale but beats nothing
            if not os.path.exists(path):
                return None, 0, 0

    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None, 0, 0
    h, w = img.shape[:2]
    return img, w, h


def screen_path(slot: str) -> str:
    """Return the on-disk path for a slot (without pulling)."""
    return _slot_path(slot)
