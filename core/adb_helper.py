# adb_helper.py - ADB connection management with auto-connect & reconnect
"""
Handles the full ADB lifecycle:
  1. Start ADB server (if not running)
  2. Connect to configured DEVICE
  3. If unreachable -> scan common emulator ports
  4. On runtime failure -> auto-reconnect before retrying
"""
import subprocess
import sys
import time

from config.settings import (
    ADB, DEVICE,
    ADB_AUTO_CONNECT, ADB_SCAN_PORTS, ADB_CONNECT_TIMEOUT, ADB_MAX_RETRIES,
)

# Active device (may differ from settings.DEVICE if auto-detected)
_active_device = DEVICE
_connected = False

# On Windows, prevent subprocess from creating a visible console window.
_CREATE_FLAGS = 0
if sys.platform == "win32":
    _CREATE_FLAGS = subprocess.CREATE_NO_WINDOW


def get_active_device() -> str:
    return _active_device


def _run_adb_raw(*args, timeout: int = 10) -> subprocess.CompletedProcess:
    cmd = [ADB, *args]
    return subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=timeout, creationflags=_CREATE_FLAGS,
    )


def _run_adb_device(*args, device: str = None, timeout: int = 30) -> subprocess.CompletedProcess:
    dev = device or _active_device
    cmd = [ADB, "-s", dev, *args]
    return subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=timeout, creationflags=_CREATE_FLAGS,
    )


def _list_devices() -> list:
    try:
        p = _run_adb_raw("devices", timeout=ADB_CONNECT_TIMEOUT)
        devices = []
        for line in p.stdout.strip().splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                devices.append((parts[0], parts[1]))
        return devices
    except Exception:
        return []


def _is_device_online(serial: str) -> bool:
    for dev_serial, dev_state in _list_devices():
        if dev_serial == serial and dev_state == "device":
            return True
    return False


def _try_connect(target: str) -> bool:
    try:
        p = _run_adb_raw("connect", target, timeout=ADB_CONNECT_TIMEOUT)
        output = (p.stdout + p.stderr).lower()
        if "connected" in output and "cannot" not in output and "refused" not in output:
            time.sleep(0.3)
            return _is_device_online(target)
    except Exception:
        pass
    return False


def _start_server() -> bool:
    try:
        p = _run_adb_raw("start-server", timeout=ADB_CONNECT_TIMEOUT)
        return p.returncode == 0
    except Exception:
        return False


def _scan_ports() -> str | None:
    for port in ADB_SCAN_PORTS:
        target = f"127.0.0.1:{port}"
        if target == _active_device:
            continue
        if _try_connect(target):
            return target
    return None


def _find_any_online_device() -> str | None:
    for serial, state in _list_devices():
        if state == "device":
            return serial
    return None


def ensure_connected(log_fn=None) -> bool:
    global _active_device, _connected

    def _log(msg):
        if log_fn:
            log_fn(msg)
        print(msg, flush=True)

    if not ADB_AUTO_CONNECT:
        _connected = True
        return True

    _log("[ADB] Starting ADB server...")
    _start_server()

    _log(f"[ADB] Connecting to {DEVICE}...")
    if _try_connect(DEVICE):
        _active_device = DEVICE
        _connected = True
        _log(f"[ADB] Connected: {DEVICE}")
        return True

    if _is_device_online(DEVICE):
        _active_device = DEVICE
        _connected = True
        _log(f"[ADB] Already connected: {DEVICE}")
        return True

    _log(f"[ADB] {DEVICE} unreachable, scanning ports...")

    found = _scan_ports()
    if found:
        _active_device = found
        _connected = True
        _log(f"[ADB] Found emulator on: {found}")
        return True

    any_dev = _find_any_online_device()
    if any_dev:
        _active_device = any_dev
        _connected = True
        _log(f"[ADB] Using existing device: {any_dev}")
        return True

    _connected = False
    _log(f"[ADB] No device found! Is the emulator running?")
    _log(f"[ADB] Tried: {DEVICE} + ports {ADB_SCAN_PORTS}")
    return False


def _reconnect_if_needed(error_msg: str) -> bool:
    connection_errors = [
        "device not found", "no devices", "offline",
        "closed", "connection refused", "cannot connect",
        "device offline", "error: protocol fault",
    ]
    err_lower = error_msg.lower()
    if not any(e in err_lower for e in connection_errors):
        return False
    return ensure_connected()


def adb(*args) -> str:
    """Run ADB shell/command with auto-reconnect on failure."""
    global _active_device

    for attempt in range(ADB_MAX_RETRIES):
        try:
            cmd = [ADB, "-s", _active_device, *args]
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, timeout=30, creationflags=_CREATE_FLAGS)
            if p.returncode != 0:
                err = (p.stderr or p.stdout).strip()
                if attempt < ADB_MAX_RETRIES - 1 and _reconnect_if_needed(err):
                    continue
                raise RuntimeError(err)
            return p.stdout
        except subprocess.TimeoutExpired:
            if attempt < ADB_MAX_RETRIES - 1 and _reconnect_if_needed("connection refused"):
                continue
            raise RuntimeError("ADB command timed out")

    raise RuntimeError(f"ADB command failed after {ADB_MAX_RETRIES} retries")


def adb_bin(*args) -> bytes:
    """Run ADB command returning raw bytes, with auto-reconnect on failure."""
    global _active_device

    for attempt in range(ADB_MAX_RETRIES):
        try:
            cmd = [ADB, "-s", _active_device, *args]
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=30, creationflags=_CREATE_FLAGS)
            if p.returncode != 0:
                err = (p.stderr or p.stdout or b"").decode(errors="ignore").strip()
                if attempt < ADB_MAX_RETRIES - 1 and _reconnect_if_needed(err):
                    continue
                raise RuntimeError(err)
            return p.stdout
        except subprocess.TimeoutExpired:
            if attempt < ADB_MAX_RETRIES - 1 and _reconnect_if_needed("connection refused"):
                continue
            raise RuntimeError("ADB command timed out")

    raise RuntimeError(f"ADB command failed after {ADB_MAX_RETRIES} retries")
