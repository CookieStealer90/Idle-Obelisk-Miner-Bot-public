"""Tap duration, compatibility and settings round trips without real ADB."""
import random
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask
from config.user_overrides import apply_overrides_to_settings, normalize_user_settings
from test_founders import ROOT, load_module


class TapperTests(unittest.TestCase):
    def setUp(self):
        adb_stub = types.ModuleType("core.adb_helper")
        adb_stub.adb = Mock()
        with patch.dict(sys.modules, {"core.adb_helper": adb_stub}):
            self.tapper = load_module("isolated_tapper", "core/tapper.py")
        self.tapper.s = types.SimpleNamespace(
            TAP_JITTER_PX=4, TAP_HOLD_MS=100,
            TAP_HUMANIZE_ENABLED=True, TAP_HOLD_VARIANCE_PCT=30)
        self.tapper.random = random.Random(42)
        self.adb = adb_stub.adb

    def test_varied_holds_and_positions_stay_in_bounds(self):
        for _ in range(300):
            self.assertTrue(self.tapper.tap(100, 200))
        durations = set()
        for call in self.adb.call_args_list:
            args = call.args
            self.assertEqual(args[:3], ("shell", "input", "swipe"))
            x, y, end_x, end_y, hold = map(int, args[3:])
            self.assertTrue(96 <= x <= 104 and 196 <= y <= 204)
            self.assertEqual((x, y), (end_x, end_y))
            self.assertTrue(70 <= hold <= 130)
            durations.add(hold)
        self.assertGreater(len(durations), 20)

    def test_explicit_hold_and_zero_remain_exact(self):
        for hold in (0, 1, 100, 1500):
            with self.subTest(hold=hold):
                self.adb.reset_mock()
                self.assertTrue(self.tapper.tap(100, 200, jitter=0, hold_ms=hold))
                expected = ("shell", "input", "tap", "100", "200") if hold == 0 else (
                    "shell", "input", "swipe", "100", "200", "100", "200", str(hold))
                self.adb.assert_called_once_with(*expected)

    def test_disabled_variation_zero_variance_and_plain_tap(self):
        for enabled, variance, base in ((False, 30, 100), (True, 0, 100), (True, 100, 0)):
            with self.subTest(enabled=enabled, variance=variance, base=base):
                self.tapper.s.TAP_HUMANIZE_ENABLED = enabled
                self.tapper.s.TAP_HOLD_VARIANCE_PCT = variance
                self.tapper.s.TAP_HOLD_MS = base
                self.adb.reset_mock()
                self.assertTrue(self.tapper.tap(10, 20, jitter=0))
                args = self.adb.call_args.args
                self.assertEqual(args[2], "tap" if base == 0 else "swipe")
                if base:
                    self.assertEqual(args[-1], str(base))

    def test_max_variance_never_turns_positive_hold_into_plain_tap(self):
        self.tapper.s.TAP_HOLD_MS = 1
        self.tapper.s.TAP_HOLD_VARIANCE_PCT = 100
        for _ in range(50):
            self.assertTrue(self.tapper.tap(10, 20))
            self.assertGreaterEqual(int(self.adb.call_args.args[-1]), 1)

    def test_adb_failure_is_reported(self):
        self.adb.side_effect = RuntimeError("simulated input failure")
        self.assertFalse(self.tapper.tap(10, 20))


class TapSettingsTests(unittest.TestCase):
    def test_invalid_values_rejected(self):
        for key, value in (("TAP_HUMANIZE_ENABLED", 1), ("TAP_HOLD_MS", -1),
                           ("TAP_HOLD_MS", 2001), ("TAP_HOLD_MS", 1.5),
                           ("TAP_HOLD_VARIANCE_PCT", 101),
                           ("TAP_HOLD_VARIANCE_PCT", float("nan")),
                           ("TAP_JITTER_PX", -1), ("TAP_JITTER_PX", 101)):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                normalize_user_settings({"tapping": {key: value}})

    def test_old_configs_need_no_migration(self):
        self.assertEqual(normalize_user_settings({"freebies": {"FREEBIES_TAP_JITTER_PX": 7}}),
                         {"freebies": {"FREEBIES_TAP_JITTER_PX": 7}})

    def test_api_save_read_and_runtime_application(self):
        api = load_module("tap_config_api", "web/config_api.py")
        app = Flask(__name__)
        app.register_blueprint(api.config_bp)
        values = dict(TAP_HUMANIZE_ENABLED=False, TAP_HOLD_MS=120,
                      TAP_HOLD_VARIANCE_PCT=25, TAP_JITTER_PX=6)
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root = Path(folder)
            (root / "config").mkdir()
            with patch.object(api, "BASE_DIR", root), patch.object(api, "_push_log"):
                client = app.test_client()
                defaults = client.get("/api/config/settings")
                self.assertEqual(defaults.status_code, 200)
                self.assertIn("TAP_HUMANIZE_ENABLED", defaults.json["tapping"])
                response = client.post("/api/config/settings", json={"tapping": values})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["apply"], "restart")
                self.assertEqual(client.get("/api/config/settings").json["tapping"], values)
                runtime = {}
                apply_overrides_to_settings(runtime, {"tapping": values})
                self.assertEqual(runtime, values)
