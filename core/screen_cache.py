"""Full-device captures with isolated Android paths and atomic local caches.

get_screen may capture; get_cached_screen/get_latest_cached_screen never do.
Readers and publishers share a per-target lock, including legacy captures.
No screenshot operation acquires the ingame action lock.
"""
import math
import os
import posixpath
import re
import threading
import time
import uuid

import cv2
import numpy as np

import config.settings as s
from core.adb_helper import adb, get_active_device
from core.file_logger import bot_log

TEMP_DIR = os.path.join(str(s.BASE_DIR), "temp")
_locks = {}
_locks_guard = threading.Lock()
_SLOT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _log(message):
    bot_log(f"[SCREENSHOT] {message}", getattr(s, "SCREENSHOT_LOG_LEVEL", "TXT"))


def _validate_slot(slot):
    if not isinstance(slot, str) or not _SLOT_RE.fullmatch(slot):
        raise ValueError(f"Invalid screenshot slot: {slot!r}")
    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved.update(f"{prefix}{i}" for prefix in ("COM", "LPT") for i in range(1, 10))
    if slot.upper() in reserved:
        raise ValueError(f"Reserved screenshot slot: {slot!r}")
    return slot


def _path_lock(path):
    key = os.path.normcase(os.path.abspath(path))
    with _locks_guard:
        return _locks.setdefault(key, threading.RLock())


def screen_path(slot: str) -> str:
    """Validated slot path, without filesystem or ADB side effects."""
    return os.path.join(TEMP_DIR, f"{_validate_slot(slot)}.png")


def _decode(data, color=False):
    if not data.startswith(_PNG_SIGNATURE):
        raise ValueError("missing PNG signature")
    # OpenCV may accept some truncated PNGs. Require the final IEND chunk too.
    if not data.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82"):
        raise ValueError("incomplete PNG (missing IEND)")
    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8),
                       cv2.IMREAD_COLOR if color else cv2.IMREAD_GRAYSCALE)
    if img is None or img.size == 0 or min(img.shape[:2]) <= 0:
        raise ValueError("PNG could not be decoded")
    return img


def _cached_data(path, max_age):
    """Read an immutable PNG snapshot. Caller holds the path lock."""
    with open(path, "rb") as stream:
        age = time.time() - os.fstat(stream.fileno()).st_mtime
        if age < 0 or age >= max_age:
            return None, age
        return stream.read(), age


def _read_cached(slot, max_age, color=False):
    path = screen_path(slot)
    with _path_lock(path):
        try:
            data, age = _cached_data(path, max_age)
            if data is None:
                return None, 0, 0, age
            img = _decode(data, color)
        except FileNotFoundError:
            return None, 0, 0, None
        except (OSError, ValueError, cv2.error) as exc:
            _log(f"slot={slot} phase=cache_read failed: {type(exc).__name__}: {exc}")
            return None, 0, 0, None
    if getattr(s, "SCREENSHOT_LOG_CACHE_HITS", False):
        _log(f"slot={slot} cache_hit age={age:.3f}s color={color}")
    h, w = img.shape[:2]
    return img, w, h, age


def get_cached_screen(slot: str, max_age: float = 5.0, color: bool = False):
    """Only read a fresh, valid local frame. Never capture or return stale data."""
    img, w, h, _ = _read_cached(slot, max_age, color)
    return img, w, h


def _newest_slots(slots):
    candidates = []
    for slot in dict.fromkeys(slots):
        try:
            path = screen_path(slot)
            candidates.append((os.path.getmtime(path), slot))
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as exc:
            _log(f"slot={slot!r} phase=cache_stat failed: {type(exc).__name__}: {exc}")
    return [slot for _, slot in sorted(candidates, reverse=True)]


def get_latest_cached_screen(slots, max_age: float, color: bool = False):
    """Return (image, width, height, slot, age), skipping broken/stale slots."""
    for slot in _newest_slots(slots):
        img, w, h, age = _read_cached(slot, max_age, color)
        if img is not None:
            return img, w, h, slot, age
    return None, 0, 0, None, None


def latest_cached_png(filenames):
    """Dashboard: (PNG bytes, filename), without capturing or open file handles.

    Only plain slot filenames are accepted, never paths or staging files.
    """
    slots = []
    for filename in filenames:
        if not isinstance(filename, str) or not filename.endswith(".png"):
            continue
        try:
            slots.append(_validate_slot(filename[:-4]))
        except ValueError:
            continue
    for slot in _newest_slots(slots):
        with _path_lock(screen_path(slot)):
            try:
                data, _ = _cached_data(screen_path(slot), float("inf"))
                if data is None:
                    continue
                _decode(data)
                return data, f"{slot}.png"
            except FileNotFoundError:
                continue
            except (OSError, ValueError, cv2.error) as exc:
                _log(f"slot={slot} phase=viewer_read failed: {type(exc).__name__}: {exc}")
    return None, None


def capture_screen(local_path: str, slot: str = "manual_scr", color: bool = False):
    """Fresh capture with retries, pinned device and atomic publication.

    Each attempt owns its remote file and local staging file. Failed cleanup
    does not invalidate a successful capture. No stale fallback is allowed.
    """
    _validate_slot(slot)
    path = os.path.abspath(local_path)
    attempts = max(1, min(5, int(getattr(s, "SCREENSHOT_CAPTURE_ATTEMPTS", 2))))
    delay = float(getattr(s, "SCREENSHOT_RETRY_DELAY_S", 0.2))
    if not math.isfinite(delay) or not 0 <= delay <= 10:
        raise ValueError("SCREENSHOT_RETRY_DELAY_S must be between 0 and 10")
    request_id = uuid.uuid4().hex
    started = time.monotonic()
    with _path_lock(path):
        for attempt in range(1, attempts + 1):
            capture_id = uuid.uuid4().hex
            device = get_active_device()
            remote_dir = posixpath.dirname(getattr(s, "REMOTE_SCREEN", "/sdcard/__scr.png"))
            remote = posixpath.join(remote_dir, f"__obelisk_{slot}_{capture_id}.png")
            staging = f"{path}.{capture_id}.part"
            context = (f"slot={slot} request={request_id} capture={capture_id} "
                       f"device={device} attempt={attempt}/{attempts}")
            phase = "prepare"
            img = None

            def adb_log(message):
                _log(f"{context} phase={phase} {message}")

            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                phase = "capture"
                _log(f"{context} phase=capture begin remote={remote} "
                     f"thread={threading.current_thread().name}")
                adb("shell", "screencap", "-p", remote, device=device, log_fn=adb_log)
                phase = "pull"
                adb("pull", remote, staging, device=device, log_fn=adb_log)
                phase = "decode"
                with open(staging, "rb") as stream:
                    data = stream.read()
                img = _decode(data, color)
                phase = "device_check"
                if get_active_device() != device:
                    raise RuntimeError(f"active device changed to {get_active_device()}")
                phase = "publish"
                # Freshness reflects this capture, not an ADB-preserved mtime.
                os.utime(staging, None)
                os.replace(staging, path)
                h, w = img.shape[:2]
                _log(f"{context} phase=complete size={w}x{h} bytes={len(data)} "
                     f"elapsed={time.monotonic() - started:.3f}s recovered={attempt > 1}")
            except Exception as exc:
                img = None
                _log(f"{context} phase={phase} failed: {type(exc).__name__}: {exc} "
                     f"elapsed={time.monotonic() - started:.3f}s")
            finally:
                phase = "remote_cleanup"
                try:
                    adb("shell", "rm", "-f", remote, device=device, log_fn=adb_log)
                except Exception as exc:
                    _log(f"{context} phase=remote_cleanup remote={remote} failed: "
                         f"{type(exc).__name__}: {exc}")
                try:
                    os.remove(staging)
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    _log(f"{context} phase=local_cleanup failed: {type(exc).__name__}: {exc}")
            if img is not None:
                return img, w, h
            if attempt < attempts:
                _log(f"{context} retry_in={delay:.3f}s (new full screenshot)")
                time.sleep(delay)
    _log(f"slot={slot} request={request_id} exhausted attempts={attempts} "
         f"elapsed={time.monotonic() - started:.3f}s; no usable screenshot; stale fallback disabled")
    return None, 0, 0


def get_screen(slot: str, max_age: float = 5.0, force: bool = False, color: bool = False):
    """Return (image, width, height); force requires a successful new capture.

    Failure returns (None, 0, 0), preserving the previous file for diagnostics.
    """
    path = screen_path(slot)
    with _path_lock(path):
        if not force:
            img, w, h = get_cached_screen(slot, max_age, color)
            if img is not None:
                return img, w, h
        return capture_screen(path, slot, color)
