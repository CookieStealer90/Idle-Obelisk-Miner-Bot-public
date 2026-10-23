# web/security.py - LAN access control & origin checking
import os
import ipaddress
from urllib.parse import urlparse
from flask import request, jsonify


def _get_client_ip() -> str:
    remote = (request.remote_addr or "").strip()
    try:
        if remote:
            ip = ipaddress.ip_address(remote)
            peer_is_local = ip.is_private or ip.is_loopback or ip.is_link_local
        else:
            peer_is_local = False
    except Exception:
        peer_is_local = False

    if peer_is_local:
        xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if xff:
            return xff
    return remote


def _is_private_or_local_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        if ip.version == 4:
            return bool(ip.is_private or ip.is_loopback or ip.is_link_local)
        return bool(ip.is_loopback or ip.is_link_local or ip.is_private)
    except Exception:
        return False


def _is_same_origin() -> bool:
    origin = request.headers.get("Origin")
    if not origin:
        return True
    if origin == "null":
        return True
    try:
        o = urlparse(origin)
        if o.scheme not in ("http", "https"):
            return False
        origin_host = (o.hostname or "").lower()
        req_host = (request.host or "").rsplit(":", 1)[0].lower()
        if origin_host == req_host:
            return True
        if _is_private_or_local_ip(origin_host):
            return True
        return False
    except Exception:
        return False


def _public_access_enabled() -> bool:
    return os.environ.get("OBELISKBOT_ALLOW_PUBLIC", "").strip() in ("1", "true", "True", "yes", "YES")


def enforce_dashboard_access_policy():
    p = request.path or ""
    protect = p.startswith("/api/") or p.startswith("/socket.io")
    if not protect:
        return None
    if not _is_same_origin():
        return jsonify({"ok": False, "error": "forbidden (origin)"}), 403
    if _public_access_enabled():
        return None
    client_ip = _get_client_ip()
    if not _is_private_or_local_ip(client_ip):
        return jsonify({"ok": False, "error": "forbidden (ip)"}), 403
    return None


def check_socketio_access() -> bool:
    try:
        if (not _public_access_enabled()) and (not _is_private_or_local_ip(_get_client_ip())):
            return False
        if not _is_same_origin():
            return False
    except Exception:
        return False
    return True
