# core/scroll.py - Central scroll primitive
"""
Central scroll function for the Idle Obelisk Miner Bot.

Why this module exists:
    Idle Obelisk Miner does NOT scroll on a normal Android flick gesture
    (fast swipe that releases the finger early). The game only reacts to
    a DRAG gesture: finger pressed down, moved, released at the destination.

    `adb shell input swipe x1 y1 x2 y2 <duration_ms>` emulates exactly that
    when `duration_ms` is high enough — short durations behave like flicks
    and are ignored by the game. Duration is therefore the critical knob.

Features use this module exclusively; never call `input swipe` directly
from feature code. That way scroll behaviour stays globally tunable via
settings.py and the WebUI "scroll" section.

API:
    scroll_up(area=None, speed=None, distance=None, duration_ms=None)
    scroll_down(...)
    scroll(direction, area=None, speed=None, distance=None, duration_ms=None)

    - area:        (x1, y1, x2, y2) rectangle. Finger starts centered
                   horizontally inside this rectangle and travels vertically.
                   Defaults to settings.SCROLL_DEFAULT_AREA.
    - speed:       "slow" | "mid" | "fast". Picks duration + distance presets.
                   Defaults to settings.SCROLL_DEFAULT_SPEED.
    - distance:    Explicit vertical travel in px (overrides speed preset).
    - duration_ms: Explicit swipe duration in ms (overrides speed preset).

    `direction` refers to FINGER movement:
        "up"   finger moves up   => reveals content below (= list scrolls down)
        "down" finger moves down => reveals content above (= list scrolls up)
"""

from core.adb_helper import adb
from core.file_logger import bot_log
import config.settings as s


_SPEED_PRESETS = {
    "slow": ("SCROLL_DURATION_SLOW_MS", "SCROLL_DISTANCE_SLOW_PX"),
    "mid":  ("SCROLL_DURATION_MID_MS",  "SCROLL_DISTANCE_MID_PX"),
    "fast": ("SCROLL_DURATION_FAST_MS", "SCROLL_DISTANCE_FAST_PX"),
}


def _resolve_preset(speed: str) -> tuple[int, int]:
    """Return (duration_ms, distance_px) for the given speed name."""
    key = (speed or "").lower().strip()
    if key not in _SPEED_PRESETS:
        key = getattr(s, "SCROLL_DEFAULT_SPEED", "mid").lower().strip()
        if key not in _SPEED_PRESETS:
            key = "mid"
    dur_attr, dist_attr = _SPEED_PRESETS[key]
    return int(getattr(s, dur_attr)), int(getattr(s, dist_attr))


def _resolve_area(area) -> tuple[int, int, int, int]:
    a = area if area is not None else getattr(s, "SCROLL_DEFAULT_AREA", (0, 102, 900, 1457))
    x1, y1, x2, y2 = int(a[0]), int(a[1]), int(a[2]), int(a[3])
    # Normalize (ensure x1<=x2, y1<=y2)
    if x2 < x1: x1, x2 = x2, x1
    if y2 < y1: y1, y2 = y2, y1
    return x1, y1, x2, y2


def scroll(direction: str,
           area=None,
           speed: str = None,
           distance: int = None,
           duration_ms: int = None) -> bool:
    """Perform a drag-scroll gesture inside `area`.

    Returns True on success, False on failure (errors are suppressed per
    runtime_flags.SUPPRESS_EXCEPTIONS but always logged).
    """
    level = getattr(s, "SCROLL_LOG_LEVEL", "FULL")

    direction = (direction or "").lower().strip()
    if direction not in ("up", "down"):
        bot_log(f"[SCROLL] invalid direction '{direction}' (expected 'up'|'down')", level)
        return False

    x1, y1, x2, y2 = _resolve_area(area)
    dur_preset, dist_preset = _resolve_preset(speed)
    dur = int(duration_ms) if duration_ms is not None else dur_preset
    dist = int(distance) if distance is not None else dist_preset

    pad = int(getattr(s, "SCROLL_EDGE_PADDING_PX", 20))
    cx = (x1 + x2) // 2

    # Place start point near the edge opposite the finger movement direction,
    # so we have room to travel `dist` pixels without leaving the area.
    if direction == "up":
        start_y = y2 - pad
        end_y = max(y1 + pad, start_y - dist)
    else:  # "down"
        start_y = y1 + pad
        end_y = min(y2 - pad, start_y + dist)

    actual_travel = abs(end_y - start_y)
    speed_label = (speed or getattr(s, "SCROLL_DEFAULT_SPEED", "mid")).lower().strip()

    bot_log(
        f"[SCROLL] {direction} | area=({x1},{y1},{x2},{y2}) "
        f"| speed={speed_label} dur={dur}ms dist={actual_travel}px "
        f"| ({cx},{start_y})->({cx},{end_y})",
        level,
    )

    try:
        adb("shell", "input", "swipe", str(cx), str(start_y), str(cx), str(end_y), str(dur))
        return True
    except Exception as e:
        bot_log(f"[SCROLL] FAILED {direction}: {type(e).__name__}: {e}", level)
        return False


def scroll_up(area=None, speed: str = None, distance: int = None, duration_ms: int = None) -> bool:
    return scroll("up", area=area, speed=speed, distance=distance, duration_ms=duration_ms)


def scroll_down(area=None, speed: str = None, distance: int = None, duration_ms: int = None) -> bool:
    return scroll("down", area=area, speed=speed, distance=distance, duration_ms=duration_ms)
