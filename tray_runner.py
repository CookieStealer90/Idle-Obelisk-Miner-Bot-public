# tray_runner.py - Launch Idle Obelisk Miner Bot as a system-tray application
# Usage:  pythonw tray_runner.py
"""
Starts the Flask/bot server in a background thread and shows a system-tray
icon with quick actions (open WebUI, quit).
"""
import os
import sys
import socket
import threading
import signal
import logging

# ── Project root on sys.path ──────────────────────────────────────────
_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)

# ── Hide any inherited console window ─────────────────────────────────
if os.name == "nt":
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass

# ── Redirect stdout/stderr to log file ───────────────────────────────
_LOG_PATH = os.path.join(_ROOT, "bot.log")


class _SafeLogWriter:
    def __init__(self, path):
        self.path = path

    def write(self, message):
        if not message:
            return
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(message)
        except Exception:
            pass

    def flush(self):
        pass


_log_writer = _SafeLogWriter(_LOG_PATH)
sys.stdout = _log_writer
sys.stderr = _log_writer

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TRAY] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("tray_runner")

# ── Silence Flask/Werkzeug HTTP request logs ─────────────────────────
logging.getLogger("werkzeug").setLevel(logging.ERROR)
logging.getLogger("engineio.server").setLevel(logging.ERROR)
logging.getLogger("socketio.server").setLevel(logging.ERROR)

# ── Third-party imports ──────────────────────────────────────────────
import pystray
from PIL import Image

# ── Constants ────────────────────────────────────────────────────────
_PORT = 6001

# ── Global state ─────────────────────────────────────────────────────
_server_ready = threading.Event()
_server_error: str | None = None
_icon: pystray.Icon | None = None


# ── Network helpers ──────────────────────────────────────────────────
def _local_ipv4_addrs() -> list[str]:
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


def _build_urls() -> list[str]:
    urls = [f"http://localhost:{_PORT}"]
    for ip in _local_ipv4_addrs():
        urls.append(f"http://{ip}:{_PORT}")
    return urls


# ── Helpers ──────────────────────────────────────────────────────────
def _icon_image() -> Image.Image:
    p = os.path.join(_ROOT, "images", "tray_icon.png")
    try:
        return Image.open(p)
    except Exception:
        # Fallback: tiny purple square
        img = Image.new("RGBA", (64, 64), (124, 92, 191, 255))
        return img


def _tooltip() -> str:
    if _server_error:
        return f"Obelisk Miner Bot - ERROR: {_server_error[:60]}"
    if _server_ready.is_set():
        return "Obelisk Miner Bot - Running"
    return "Obelisk Miner Bot - Starting..."


def _open_url(url: str):
    def _handler(icon, item):
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
    return _handler


# ── Config helpers ───────────────────────────────────────────────────
def _config_json_files() -> list[str]:
    cfg_dir = os.path.join(_ROOT, "config")
    try:
        if not os.path.isdir(cfg_dir):
            return []
        files = []
        for name in os.listdir(cfg_dir):
            if name.lower().endswith(".json"):
                p = os.path.join(cfg_dir, name)
                if os.path.isfile(p):
                    files.append(name)
        return sorted(files, key=lambda s: s.lower())
    except Exception:
        return []


def _delete_config_json(filename: str):
    def _handler(icon, item):
        try:
            cfg_dir = os.path.join(_ROOT, "config")
            safe_name = os.path.basename(filename)
            p = os.path.join(cfg_dir, safe_name)
            if os.path.isfile(p) and p.lower().endswith(".json"):
                os.remove(p)
                log.info("Deleted user-config: %s", p)
        except Exception:
            pass
    return _handler


def _on_open_folder(icon, item):
    try:
        if sys.platform == "win32":
            os.startfile(_ROOT)
        elif sys.platform == "darwin":
            import subprocess as _sp
            _sp.Popen(["open", _ROOT])
        else:
            import subprocess as _sp
            _sp.Popen(["xdg-open", _ROOT])
    except Exception:
        pass


def _on_open_log(icon, item):
    try:
        if os.path.isfile(_LOG_PATH):
            if sys.platform == "win32":
                os.startfile(_LOG_PATH)
            elif sys.platform == "darwin":
                import subprocess as _sp
                _sp.Popen(["open", _LOG_PATH])
            else:
                import subprocess as _sp
                _sp.Popen(["xdg-open", _LOG_PATH])
    except Exception:
        pass


# ── Server thread ────────────────────────────────────────────────────
def _run_server():
    global _server_error
    try:
        log.info("Starting server...")
        from main import main as _main
        _server_ready.set()
        _main()
    except Exception as exc:
        _server_error = str(exc)
        log.exception("Server crashed!")
        _server_ready.set()


# ── Menu actions ─────────────────────────────────────────────────────
def _on_restart(icon, item):
    log.info("User requested restart - relaunching process.")
    icon.stop()
    import subprocess as _sp
    _CREATE = 0
    if sys.platform == "win32":
        _CREATE = _sp.CREATE_NO_WINDOW
    _sp.Popen(
        [sys.executable, os.path.join(_ROOT, "tray_runner.py")],
        cwd=_ROOT,
        creationflags=_CREATE,
    )
    os._exit(0)


def _on_quit(icon, item):
    log.info("User requested quit - shutting down.")
    icon.stop()
    os._exit(0)


# ── Build tray menu ─────────────────────────────────────────────────
def _build_menu(urls: list[str]) -> pystray.Menu:
    webui_items = []
    for url in urls:
        if "localhost" in url:
            label = f"localhost:{_PORT}"
        else:
            label = url.replace("http://", "")
        webui_items.append(pystray.MenuItem(label, _open_url(url)))

    reset_items = []
    for fn in _config_json_files():
        reset_items.append(pystray.MenuItem(fn, _delete_config_json(fn)))
    if not reset_items:
        reset_items.append(pystray.MenuItem("(no .json found)", lambda *_: None, enabled=False))

    return pystray.Menu(
        pystray.MenuItem(
            "Open WebUI",
            pystray.Menu(*webui_items),
            default=True,
        ),
        pystray.MenuItem("Open Application Folder", _on_open_folder),
        pystray.MenuItem("Open bot.log", _on_open_log),
        pystray.MenuItem("Reset User-Config", pystray.Menu(*reset_items)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Restart Bot", _on_restart),
        pystray.MenuItem("Quit", _on_quit),
    )


# ── Entry point ──────────────────────────────────────────────────────
def main():
    global _icon

    signal.signal(signal.SIGINT, lambda *_: _on_quit(_icon, None) if _icon else os._exit(0))

    urls = _build_urls()
    log.info("WebUI URLs: %s", ", ".join(urls))

    srv = threading.Thread(target=_run_server, daemon=True, name="ServerThread")
    srv.start()

    _icon = pystray.Icon("ObeliskMinerBot", _icon_image(), _tooltip(), _build_menu(urls))

    def _tooltip_updater():
        import time
        while True:
            time.sleep(5)
            if _icon:
                _icon.title = _tooltip()

    threading.Thread(target=_tooltip_updater, daemon=True, name="TooltipUpdater").start()

    log.info("Tray icon starting.")
    _icon.run()


if __name__ == "__main__":
    main()
