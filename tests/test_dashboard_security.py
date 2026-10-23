"""LAN browser access, HTTP, Engine.IO transports and Socket.IO commands."""
import os
from queue import Empty
import unittest
from unittest.mock import patch

from flask import Flask, jsonify
from web import security
import test_founders as helpers


class AccessPolicyTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.before_request(security.enforce_dashboard_access_policy)
        self.app.add_url_rule("/api/probe", view_func=lambda: jsonify(ok=True), methods=["GET", "POST"])
        self.client = self.app.test_client()
        self.env = patch.dict(os.environ, {"OBELISKBOT_ALLOW_PUBLIC": "0"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def probe(self, origin=None, ip="192.168.178.23", base="http://192.168.178.50:6001", **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        if origin is not None:
            headers["Origin"] = origin
        return self.client.post("/api/probe", base_url=base, json={}, headers=headers,
                                environ_overrides={"REMOTE_ADDR": ip}, **kwargs)

    def test_multiple_lan_devices_use_server_origin_and_remain_allowed(self):
        for ip in ("192.168.178.23", "192.168.178.24", "10.0.0.5", "127.0.0.1", "::1", "fd00::123"):
            with self.subTest(ip=ip):
                self.assertEqual(self.probe("http://192.168.178.50:6001", ip).status_code, 200)
        self.assertEqual(self.probe("http://bot-pc:6001", base="http://bot-pc:6001").status_code, 200)
        self.assertEqual(self.probe("http://[fd00::50]:6001", base="http://[fd00::50]:6001").status_code, 200)

    def test_rejects_other_lan_origins_ports_schemes_null_and_invalid_urls(self):
        for origin in ("http://192.168.178.24:6001", "http://192.168.178.50:6002",
                       "https://192.168.178.50:6001", "null", "", "https://evil.example",
                       "http://user@192.168.178.50:6001", "http://[broken", "http://192.168.178.50:bad",
                       "http://192.168.178.50:6001/path", "http://192.168.178.50:6001?x=1"):
            with self.subTest(origin=origin):
                self.assertEqual(self.probe(origin).status_code, 403)

    def test_originless_scripts_require_json_for_mutations_and_referer_is_checked(self):
        self.assertEqual(self.probe().status_code, 200)
        response = self.client.post("/api/probe", base_url="http://192.168.178.50:6001", data={},
                                    environ_overrides={"REMOTE_ADDR": "192.168.178.23"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.probe(headers={"Referer": "http://evil.example/page"}).status_code, 403)
        self.assertEqual(self.probe(headers={"Referer": "http://192.168.178.50:6001/page"}).status_code, 200)
        self.assertEqual(self.probe(headers={"Sec-Fetch-Site": "cross-site"}).status_code, 403)

    def test_forwarded_headers_cannot_grant_access_or_break_direct_lan_clients(self):
        self.assertEqual(self.probe(ip="8.8.8.8", headers={"X-Forwarded-For": "192.168.1.5"}).status_code, 403)
        self.assertEqual(self.probe(headers={"X-Forwarded-For": "8.8.8.8"}).status_code, 200)
        self.assertEqual(self.probe("https://evil.example", headers={"X-Forwarded-Host": "evil.example",
                         "X-Forwarded-Proto": "https"}).status_code, 403)

    def test_public_ip_override_does_not_disable_origin_validation(self):
        with patch.dict(os.environ, {"OBELISKBOT_ALLOW_PUBLIC": "1"}):
            self.assertEqual(self.probe("http://192.168.178.50:6001", ip="8.8.8.8").status_code, 200)
            self.assertEqual(self.probe("null", ip="8.8.8.8").status_code, 403)

    def test_engineio_callback_normalizes_default_ports_and_ignores_forwarded_host(self):
        callback = security.socketio_origin_allowed
        environ = {"wsgi.url_scheme": "http", "HTTP_HOST": "bot-pc"}
        self.assertTrue(callback("http://BOT-PC:80", environ))
        self.assertFalse(callback("http://bot-pc:0", environ))
        self.assertFalse(callback("http://bot-pc:6001", environ))
        environ["HTTP_X_FORWARDED_HOST"] = "evil.example"
        self.assertFalse(callback("http://evil.example", environ))
        for ip in ("0.0.0.0", "::", "224.0.0.1", "ff02::1", "8.8.8.8", "invalid"):
            self.assertFalse(security._is_private_or_local_ip(ip))


class SocketIntegrationTests(unittest.TestCase):
    def setUp(self):
        with patch("web.secret_key.load_or_create_secret_key", return_value="test-only-secret"):
            self.web = helpers.load_module("security_web_under_test", "web/app.py")
        self.env = patch.dict(os.environ, {"OBELISKBOT_ALLOW_PUBLIC": "0"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.state = patch.object(self.web, "build_state_dict", return_value={"started": False})
        self.state.start()
        self.addCleanup(self.state.stop)

    def connect(self, ip, origin):
        client = self.web.app.test_client()
        client.environ_base["REMOTE_ADDR"] = ip
        return self.web.socketio.test_client(self.web.app, flask_test_client=client,
            headers={"Host": "192.168.178.50:6001", "Origin": origin})

    def test_lan_connections_can_command_and_unauthorized_connections_cannot(self):
        for ip in ("192.168.178.23", "192.168.178.24"):
            socket = self.connect(ip, "http://192.168.178.50:6001")
            try:
                self.assertTrue(socket.is_connected())
                socket.emit("command", {"cmd": "reload_cfg"})
                self.assertEqual(self.web.command_queue.get_nowait(), "reload_cfg")
            finally:
                if socket.is_connected():
                    socket.disconnect()
        for ip, origin in (("192.168.178.23", "http://192.168.178.24:6001"),
                           ("192.168.178.23", "null"), ("8.8.8.8", "http://192.168.178.50:6001")):
            socket = self.connect(ip, origin)
            self.assertFalse(socket.is_connected())
        with self.assertRaises(Empty):
            self.web.command_queue.get_nowait()
        self.assertIsNone(self.web._bot_thread)

    def test_engineio_polling_handshake_enforces_same_origin_without_wildcard(self):
        client = self.web.app.test_client()
        for origin, expected in (("http://192.168.178.50:6001", 200),
                                 ("http://192.168.178.23:6001", 400), ("null", 400)):
            response = client.get("/socket.io/?EIO=4&transport=polling", base_url="http://192.168.178.50:6001",
                                  headers={"Origin": origin}, environ_overrides={"REMOTE_ADDR": "192.168.178.23"})
            self.assertEqual(response.status_code, expected)
            self.assertNotEqual(response.headers.get("Access-Control-Allow-Origin"), "*")
            if expected == 200:
                self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), origin)
        self.web.socketio.server.eio.shutdown()


if __name__ == "__main__":
    unittest.main()
