# core/tapper.py - Humanlike tap primitive
"""
Central tap helper. Adds ±jitter to coordinates so taps don't land on the
exact same pixel every time. Use `tap(x, y)` everywhere instead of calling
`adb input tap` / `input swipe` directly.

Why `input swipe x y x y <ms>` instead of `input tap`:
    Idle Obelisk Miner (like many games) ignores the ultra-brief DOWN/UP
    that `input tap` emits. A zero-distance swipe with a real duration
    produces a proper press-and-release the game registers.

    Set TAP_HOLD_MS = 0 in settings.py to fall back to plain `input tap`.
"""
import random

from core.adb_helper import adb
import config.settings as s


def tap(x: int, y: int, jitter: int = None, hold_ms: int = None) -> bool:
    """Tap at (x, y) with +/- jitter px, held for `hold_ms` ms."""
    j = int(jitter) if jitter is not None else int(getattr(s, "TAP_JITTER_PX", 4))
    hold = int(hold_ms) if hold_ms is not None else int(getattr(s, "TAP_HOLD_MS", 100))

    tx = int(x) + random.randint(-j, j)
    ty = int(y) + random.randint(-j, j)

    try:
        if hold > 0:
            # Zero-distance swipe = press-and-release with duration.
            adb("shell", "input", "swipe", str(tx), str(ty), str(tx), str(ty), str(hold))
        else:
            adb("shell", "input", "tap", str(tx), str(ty))
        return True
    except Exception:
        return False
