# web/app.py - Flask + SocketIO web server
"""
Web dashboard server for the Idle Obelisk Miner Bot.
Provides real-time status, controls, and log streaming.
"""
import os
import sys
import time
import socket
import threading
import subprocess
from io import BytesIO
from pathlib import Path
from datetime import datetime
from queue import Queue

from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO

from web.security import enforce_dashboard_access_policy, check_socketio_access, socketio_origin_allowed
from web.secret_key import load_or_create_secret_key
from web.state_builder import build_state_dict
from web.config_api import config_bp

BASE_DIR = Path(__file__).resolve().parent.parent

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "web" / "templates"),
    static_folder=str(BASE_DIR / "web" / "static"),
)
app.config["SECRET_KEY"] = load_or_create_secret_key(BASE_DIR / "config" / "web_secret.json")

socketio = SocketIO(app, async_mode="threading", cors_allowed_origins=socketio_origin_allowed)

app.register_blueprint(config_bp)

_bot_thread = None
_bot_started = False

command_queue = Queue()

_log_buffer = []
_log_buffer_lock = threading.Lock()
_LOG_BUFFER_MAX = 500


# ============ SECURITY HOOK ============

@app.before_request
def _before_request():
    return enforce_dashboard_access_policy()


# ============ LOGGING ============

def push_log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    entry = {"ts": ts, "msg": msg}
    with _log_buffer_lock:
        _log_buffer.append(entry)
        if len(_log_buffer) > _LOG_BUFFER_MAX:
            _log_buffer.pop(0)
    try:
        socketio.emit("log_entry", entry)
    except Exception:
        pass


def emit_state(data: dict):
    try:
        socketio.emit("bot_state", data)
    except Exception:
        pass


def emit_live(event: str, data):
    try:
        socketio.emit(event, data)
    except Exception:
        pass


def push_toast(msg: str, error: bool = False):
    """Push a toast notification to all connected dashboards."""
    try:
        socketio.emit("toast", {"msg": msg, "error": bool(error)})
    except Exception:
        pass


# ============ ROUTES ============

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    try:
        data = build_state_dict()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/command", methods=["POST"])
def api_command():
    cmd = request.json.get("cmd", "")
    if cmd:
        command_queue.put(cmd)
        return jsonify({"ok": True, "cmd": cmd})
    return jsonify({"ok": False, "error": "no cmd"}), 400


@app.route("/api/logs")
def api_logs():
    with _log_buffer_lock:
        return jsonify(_log_buffer[-200:])


@app.route("/api/restart", methods=["POST"])
def api_restart():
    push_log("[WEB] Restart requested - relaunching process.")

    def _do_restart():
        time.sleep(0.5)
        _CREATE = 0
        if sys.platform == "win32":
            _CREATE = subprocess.CREATE_NO_WINDOW
        entry = os.path.join(str(BASE_DIR), "tray_runner.py")
        if not os.path.exists(entry):
            entry = os.path.join(str(BASE_DIR), "main.py")
        subprocess.Popen(
            [sys.executable, entry],
            cwd=str(BASE_DIR),
            creationflags=_CREATE,
        )
        os._exit(0)

    threading.Thread(target=_do_restart, daemon=True).start()
    return jsonify({"ok": True, "msg": "Restarting..."})


@app.route("/api/screenshot")
def api_screenshot():
    """Serve the newest allowed screenshot from ./temp/."""
    from config import settings as s
    from core.screen_cache import latest_cached_png
    allowed = getattr(s, "SCREENSHOT_VIEWER_FILES", ["game_scr.png", "freebie_scr.png"])
    data, filename = latest_cached_png(allowed)
    if data is None:
        return jsonify({"error": "no screenshot"}), 404
    return send_file(BytesIO(data), mimetype="image/png", download_name=filename,
                     max_age=0)


# ============ LOG FILTER SYNC ============

_log_filters = []
_log_filters_lock = threading.Lock()

# ============ GEM STATS VISIBILITY SYNC ============

_gs_visibility = {"gem": True, "actions": True}
_gs_visibility_lock = threading.Lock()


# ============ SOCKETIO EVENTS ============

@socketio.on("connect")
def on_connect():
    if not check_socketio_access():
        return False
    try:
        data = build_state_dict()
        socketio.emit("bot_state", data, to=request.sid)
    except Exception:
        socketio.emit("bot_state", {"started": False}, to=request.sid)
    with _log_filters_lock:
        socketio.emit("log_filters_sync", _log_filters, to=request.sid)
    with _gs_visibility_lock:
        socketio.emit("gs_visibility_sync", _gs_visibility, to=request.sid)


@socketio.on("command")
def on_command(data):
    if not check_socketio_access():
        return
    cmd = data.get("cmd", "") if isinstance(data, dict) else str(data)
    if cmd:
        command_queue.put(cmd)


@socketio.on("log_filters_update")
def on_log_filters_update(data):
    global _log_filters
    if not check_socketio_access():
        return
    if not isinstance(data, list):
        return
    with _log_filters_lock:
        _log_filters = data
    socketio.emit("log_filters_sync", data)


@socketio.on("gs_visibility_update")
def on_gs_visibility_update(data):
    global _gs_visibility
    if not check_socketio_access():
        return
    if not isinstance(data, dict):
        return
    with _gs_visibility_lock:
        _gs_visibility = data
    socketio.emit("gs_visibility_sync", data)


# ============ PERIODIC STATE PUSH ============

def _state_push_loop():
    while True:
        try:
            # Drain any buffered startup logs from file_logger
            try:
                from core.file_logger import flush_pending
                flush_pending()
            except Exception:
                pass
            data = build_state_dict()
            socketio.emit("bot_state", data)
        except Exception:
            pass
        time.sleep(1.0)


def start_state_pusher():
    t = threading.Thread(target=_state_push_loop, daemon=True, name="state-pusher")
    t.start()


# ============ BOT THREAD ============

def start_bot_thread():
    global _bot_thread, _bot_started

    if _bot_started:
        return

    def _run_bot():
        global _bot_started
        _bot_started = True
        try:
            from bot_app import run
            run()
        except Exception as e:
            push_log(f"[BOT] FATAL: {e}")
            _bot_started = False

    _bot_thread = threading.Thread(target=_run_bot, daemon=True, name="bot-main")
    _bot_thread.start()


def _local_ipv4_addrs():
    addrs = set()
    try:
        hostname = socket.gethostname()
        for res in socket.getaddrinfo(hostname, None, family=socket.AF_INET):
            ip = res[4][0]
            if ip and not ip.startswith("127."):
                addrs.add(ip)
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            addrs.add(ip)
    except Exception:
        pass
    return sorted(addrs)


def run_server(host="0.0.0.0", port=6001, debug=False):
    """Start the web server and bot."""
    start_state_pusher()
    start_bot_thread()

    local_ips = _local_ipv4_addrs()

    print(f"\n{'='*60}")
    print("  IDLE OBELISK MINER BOT - Web Dashboard")
    for ip in ["localhost"] + local_ips:
        print(f"  Open in browser: http://{ip}:{port}")
    print("  Press CTRL+C to stop")
    print(f"{'='*60}\n")

    import logging as _logging
    _logging.getLogger("werkzeug").setLevel(_logging.ERROR)
    _logging.getLogger("engineio.server").setLevel(_logging.ERROR)
    _logging.getLogger("socketio.server").setLevel(_logging.ERROR)

    socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True, use_reloader=False)
