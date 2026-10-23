"""LAN access and exact browser origins; forwarded headers are untrusted."""
import os
import ipaddress
from urllib.parse import urlsplit
from flask import request, jsonify


def _get_client_ip() -> str:
    return (request.remote_addr or "").strip()


def _is_private_or_local_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        if getattr(ip, "ipv4_mapped", None) is not None:
            ip = ip.ipv4_mapped
        return bool(ip.is_loopback or ip.is_link_local or ip.is_private) and not (ip.is_unspecified or ip.is_multicast)
    except ValueError:
        return False


def _origin_tuple(url):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            return None
        return (parsed.scheme, parsed.hostname.lower(),
                parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80))
    except (ValueError, TypeError):
        return None


def socketio_origin_allowed(origin, environ):
    """Engine.IO callback, also used by HTTP and Socket.IO event checks.

    LAN clients open the server's URL; their own IPs are not origins.
    Missing Origin is allowed for local scripts, subject to IP restrictions.
    """
    if environ.get("HTTP_SEC_FETCH_SITE") == "cross-site":
        return False
    if origin is None:
        return True
    expected = _origin_tuple(f"{environ.get('wsgi.url_scheme', 'http')}://{environ.get('HTTP_HOST', '')}")
    actual = _origin_tuple(origin)
    return actual is not None and expected is not None and actual == expected


def _is_same_origin() -> bool:
    if not socketio_origin_allowed(request.headers.get("Origin"), request.environ):
        return False
    if "Origin" not in request.headers:
        referer = request.headers.get("Referer")
        if referer:
            try:
                parsed = urlsplit(referer)
                origin = f"{parsed.scheme}://{parsed.netloc}"
            except ValueError:
                return False
            if not socketio_origin_allowed(origin, request.environ):
                return False
        # Refuse originless HTML form mutations. JSON scripts remain usable.
        if request.method not in ("GET", "HEAD", "OPTIONS") and not request.is_json:
            return False
    return True


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
