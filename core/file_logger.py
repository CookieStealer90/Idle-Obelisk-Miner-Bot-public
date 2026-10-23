# file_logger.py - File logging with rotation + WebUI bridge
"""
Central logging for the Idle Obelisk Miner Bot.

Log levels:
  "FULL" (default) — write to bot.log AND push to WebUI log stream
  "TXT"            — write to bot.log only
  "UI"             — push to WebUI log stream only

Usage:
  from core.file_logger import bot_log, file_log, log_exception
  bot_log("[CLICKER] Gem collected!")          # FULL (both)
  bot_log("[DEBUG] Score: 0.82", "UI")         # WebUI only
  bot_log("[AUDIT] Session saved", "TXT")      # file only
  file_log("legacy call")                      # same as bot_log(msg, "FULL")
"""
import os
import traceback
import threading
from datetime import datetime

import config.runtime_flags as runtime_flags
import config.app_state as state
from config.settings import LOG_MAX_SIZE_MB, LOG_BACKUP_COUNT

_log_lock = threading.Lock()

# WebUI bridge — lazy-resolved to avoid circular imports
_push_log_fn = None
_pending_ui_msgs = []       # buffered before server is ready
_pending_lock = threading.Lock()


# ============================================================
#  Log rotation
# ============================================================

def _rotate_log_if_needed(log_path: str):
    try:
        if not os.path.exists(log_path):
            return
        size_bytes = os.path.getsize(log_path)
        size_mb = size_bytes / (1024 * 1024)
        if size_mb < LOG_MAX_SIZE_MB:
            return

        oldest_backup = f"{log_path}.{LOG_BACKUP_COUNT}"
        if os.path.exists(oldest_backup):
            os.remove(oldest_backup)

        for i in range(LOG_BACKUP_COUNT - 1, 0, -1):
            src = f"{log_path}.{i}"
            dst = f"{log_path}.{i + 1}"
            if os.path.exists(src):
                os.rename(src, dst)

        os.rename(log_path, f"{log_path}.1")

        with open(log_path, "w", encoding="utf-8") as f:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] [LOG-ROTATION] Log rotated - previous size: {size_mb:.2f} MB\n")
    except Exception:
        if not runtime_flags.SUPPRESS_EXCEPTIONS:
            raise


# ============================================================
#  Internal targets
# ============================================================

def _write_to_file(msg: str):
    """Write a timestamped line to bot.log (with rotation)."""
    try:
        if not getattr(state.cfg, "ENABLE_FILE_LOG", False):
            return
        path = getattr(state.cfg, "FILE_LOG_PATH", "bot.log")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with _log_lock:
            _rotate_log_if_needed(path)
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {msg}\n")
    except Exception:
        if not runtime_flags.SUPPRESS_EXCEPTIONS:
            raise


def _resolve_push_log():
    """Lazy-resolve web.app.push_log to avoid circular imports."""
    global _push_log_fn
    if _push_log_fn is not None:
        return _push_log_fn
    try:
        from web.app import push_log
        _push_log_fn = push_log
        return push_log
    except Exception:
        return None


def _push_to_webui(msg: str):
    """Push a log line to the WebUI log stream via SocketIO.
    Buffers messages until the server is ready, then flushes."""
    global _pending_ui_msgs
    fn = _resolve_push_log()
    if fn is None:
        # Server not ready — buffer for later
        with _pending_lock:
            _pending_ui_msgs.append(msg)
        return

    # Flush any pending messages first
    with _pending_lock:
        pending = _pending_ui_msgs
        _pending_ui_msgs = []
    for m in pending:
        try:
            fn(m)
        except Exception:
            pass

    # Push current message
    try:
        fn(msg)
    except Exception:
        pass


def flush_pending():
    """Explicit flush — drains the pending UI buffer into push_log.
    Safe to call repeatedly (no-op if buffer empty or server not ready).
    Called by web.app's state pusher to guarantee startup logs reach the UI."""
    global _pending_ui_msgs
    with _pending_lock:
        if not _pending_ui_msgs:
            return
    fn = _resolve_push_log()
    if fn is None:
        return
    with _pending_lock:
        pending = _pending_ui_msgs
        _pending_ui_msgs = []
    for m in pending:
        try:
            fn(m)
        except Exception:
            pass


# ============================================================
#  Public API
# ============================================================

def bot_log(msg: str, level: str = "FULL"):
    """Central log function.

    level:
      "FULL" — bot.log + WebUI  (default)
      "TXT"  — bot.log only
      "UI"   — WebUI only
    """
    if level in ("TXT", "FULL"):
        _write_to_file(msg)
    if level in ("UI", "FULL"):
        _push_to_webui(msg)


def file_log(msg: str):
    """Legacy wrapper — logs to both file and WebUI (level=FULL)."""
    bot_log(msg, "FULL")


def log_exception(e: Exception, context: str = ""):
    """Log an exception with traceback (level=FULL)."""
    try:
        tb = traceback.format_exc()
        ctx = f" {context} |" if context else ""
        bot_log(f"[EXCEPTION]{ctx} {type(e).__name__}: {e}", "FULL")
        bot_log(f"[TRACEBACK] {tb.strip()}", "FULL")
    except Exception:
        pass

    if not runtime_flags.SUPPRESS_EXCEPTIONS:
        raise
