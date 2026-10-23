"""Founders regression tests; no ADB calls, bot startup or real game actions.

Run: python -B -m unittest discover -s tests -v
"""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

from flask import Flask
from config.user_overrides import migrate_founders_settings, apply_overrides_to_settings

ROOT = Path(__file__).resolve().parent.parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.legacy = {
            "startup_defaults": {"lootbug_enabled": False},
            "lootbug": {"LOOTBUG_CHECK_INTERVAL_S": 90, "LOOTBUG_MATCH_THRESHOLD": 0.87,
                        "LOOTBUG_CLOSE_ROI": [1, 2, 3, 4]},
            "lootbug_founders": {"LOOTBUG_FOUNDERS_ENABLED": True,
                                "LOOTBUG_FOUNDERS_LOG_LEVEL": "TXT"},
        }

    def test_migration_preserves_values_and_input(self):
        original = copy.deepcopy(self.legacy)
        result = migrate_founders_settings(self.legacy)
        self.assertNotIn("lootbug_founders", result)
        self.assertEqual(result["founders"]["FOUNDERS_CHECK_INTERVAL_S"], 90)
        self.assertEqual(result["founders"]["FOUNDERS_LOG_LEVEL"], "TXT")
        self.assertTrue(result["startup_defaults"]["FOUNDERS_ENABLED"])
        self.assertNotIn("FOUNDERS_ENABLED", result["founders"])
        self.assertEqual(self.legacy, original)
        self.assertEqual(migrate_founders_settings(result), result)

    def test_explicit_founders_settings_win_and_no_longer_follow_lootbug(self):
        self.legacy["founders"] = {"FOUNDERS_CHECK_INTERVAL_S": 120}
        result = migrate_founders_settings(self.legacy)
        result["lootbug"]["LOOTBUG_CHECK_INTERVAL_S"] = 5
        self.assertEqual(migrate_founders_settings(result)["founders"]["FOUNDERS_CHECK_INTERVAL_S"], 120)

    def test_override_loader_converts_roi_and_keeps_independent_activation(self):
        self.legacy["founders"] = {"FOUNDERS_DETECT_ROI": [10, 20, 30, 40]}
        settings = {}
        apply_overrides_to_settings(settings, self.legacy)
        self.assertEqual(settings["FOUNDERS_DETECT_ROI"], (10, 20, 30, 40))
        self.assertNotIn("FOUNDERS_CLOSE_ROI", settings)
        self.assertEqual(settings["FOUNDERS_MATCH_THRESHOLD"], 0.87)
        self.assertTrue(settings["FOUNDERS_ENABLED"])
        self.assertFalse(settings["LOOTBUG_ENABLED_DEFAULT"])

    def test_startup_setting_wins_and_obsolete_popup_fields_are_removed(self):
        self.legacy["startup_defaults"]["FOUNDERS_ENABLED"] = False
        self.legacy["founders"] = {
            "FOUNDERS_ENABLED": True, "FOUNDERS_CLOSE_ROI": [1, 2, 3, 4],
            "FOUNDERS_CLOSE_TEMPLATE": "unused.png", "FOUNDERS_POST_CLICK_DELAY_S": 1.2,
        }
        result = migrate_founders_settings(self.legacy)
        self.assertFalse(result["startup_defaults"]["FOUNDERS_ENABLED"])
        for key in self.legacy["founders"]:
            self.assertNotIn(key, result["founders"])
        settings = {}
        apply_overrides_to_settings(settings, result)
        self.assertFalse(settings["FOUNDERS_ENABLED"])


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.state = types.ModuleType("config.app_state")
        self.state.founders_enabled = True
        self.state.founders_clicked_count = 0
        self.state.founders_last_click_ts = 0.0
        self.state.founders_next_check_ts = 0.0
        self.state.lootbug_enabled = False
        self.state.ingame_action_lock = threading.Lock()
        self.settings = types.ModuleType("config.settings")
        for key, value in {
            "FOUNDERS_MATCH_THRESHOLD": 0.91, "FOUNDERS_DETECT_ROI": (10, 20, 30, 40),
            "FOUNDERS_TAP_JITTER_PX": 2,
            "FOUNDERS_CHECK_INTERVAL_S": 42, "FOUNDERS_BUSY_RETRY_S": 7,
        }.items():
            setattr(self.settings, key, value)
        stubs = {"config.app_state": self.state, "config.settings": self.settings}
        for name, attrs in {
            "core.file_logger": {"bot_log": Mock()},
            "core.screen_cache": {"get_screen": Mock(return_value=(object(), 900, 1600)),
                                  "get_cached_screen": Mock(return_value=(object(), 900, 1600))},
            "core.vision": {"find_template": Mock()},
            "core.tapper": {"tap": Mock()},
            "core.game_state": {"is_game_running": Mock(return_value=True)},
        }.items():
            module = types.ModuleType(name)
            module.__dict__.update(attrs)
            stubs[name] = module
        with patch.dict(sys.modules, stubs):
            self.feature = load_module("founders_under_test", "features/founders.py")
        # A prior API test may have attached real modules to the config package.
        self.feature.s = self.settings
        self.feature.state = self.state
        self.feature.time = types.SimpleNamespace(sleep=Mock(), time=lambda: 100.0)

    def test_claim_is_one_click_without_delay_or_popup_with_lootbug_disabled(self):
        self.feature.find_template.return_value = {"found": True, "score": 0.99, "cx": 21, "cy": 22}
        self.assertEqual(self.feature._try_run_with_lock(), "ok")
        self.feature.tap.assert_called_once_with(21, 22, jitter=2)
        matches = self.feature.find_template.call_args_list
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].kwargs, {"roi": (10, 20, 30, 40), "threshold": 0.91})
        self.assertEqual(self.state.founders_clicked_count, 1)
        self.assertEqual(self.state.founders_last_click_ts, 100)
        self.assertFalse(self.state.ingame_action_lock.locked())
        self.feature.get_cached_screen.assert_called_once_with("game_scr", max_age=5.0)
        self.feature.get_screen.assert_not_called()
        self.feature.time.sleep.assert_not_called()

    def test_no_detection_does_not_click_or_count(self):
        self.feature.find_template.return_value = {"found": False, "score": 0.1}
        self.assertFalse(self.feature._run_scan_cycle())
        self.feature.tap.assert_not_called()
        self.assertEqual(self.state.founders_clicked_count, 0)

    def test_missing_shared_cache_captures_only_own_slot(self):
        self.feature.get_cached_screen.return_value = (None, 0, 0)
        self.feature._get_screen_for_scan()
        self.feature.get_screen.assert_called_once_with("founders_scr", max_age=0.0, force=True)

    def test_busy_lock_and_absent_game_do_not_capture_or_click(self):
        self.state.ingame_action_lock.acquire()
        try:
            self.assertEqual(self.feature._try_run_with_lock(), "busy")
        finally:
            self.state.ingame_action_lock.release()
        self.feature.is_game_running.return_value = False
        self.assertEqual(self.feature._try_run_with_lock(), "no_game")
        self.feature.get_screen.assert_not_called()
        self.feature.tap.assert_not_called()

    def test_lock_is_released_on_error(self):
        self.feature.find_template.side_effect = RuntimeError("simulated failure")
        with self.assertRaises(RuntimeError):
            self.feature._try_run_with_lock()
        self.assertFalse(self.state.ingame_action_lock.locked())

    def test_toggle_changes_only_founders(self):
        self.assertFalse(self.feature.toggle())
        self.assertTrue(self.feature.toggle())
        self.assertTrue(self.feature._wake_evt.is_set())
        self.assertFalse(self.state.lootbug_enabled)

    def test_worker_uses_own_interval_and_retry_policy(self):
        for result, delay in (("ok", 42), ("busy", 7), ("no_game", 30)):
            with self.subTest(result=result):
                self.feature._stop_evt.clear()
                sleeps = []

                def sleep_once(seconds):
                    sleeps.append(seconds)
                    if len(sleeps) == 2:
                        self.feature._stop_evt.set()

                with patch.object(self.feature, "_try_run_with_lock", return_value=result), \
                     patch.object(self.feature, "_sleep_interruptible", side_effect=sleep_once):
                    self.feature._worker()
                self.assertEqual(sleeps, [3.0, delay])
                self.assertEqual(self.state.founders_next_check_ts, 100 + delay)

    def test_disabled_worker_never_runs_a_cycle(self):
        self.state.founders_enabled = False
        with patch.object(self.feature, "_try_run_with_lock") as run, \
             patch.object(self.feature, "_sleep_interruptible") as sleep:
            sleep.side_effect = lambda seconds: self.feature._stop_evt.set() if seconds != 3.0 else None
            self.feature._worker()
        run.assert_not_called()


class ConfigApiTests(unittest.TestCase):
    def test_api_migrates_and_saves_only_the_new_founders_section(self):
        api = load_module("config_api_under_test", "web/config_api.py")
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root = Path(folder)
            (root / "config").mkdir()
            path = root / "config/user_settings.json"
            path.write_text(json.dumps({
                "lootbug": {"LOOTBUG_CHECK_INTERVAL_S": 90},
                "lootbug_founders": {"LOOTBUG_FOUNDERS_ENABLED": True},
            }), encoding="utf-8")
            app = Flask(__name__)
            app.register_blueprint(api.config_bp)
            with patch.object(api, "BASE_DIR", root), patch.object(api, "_push_log"):
                client = app.test_client()
                response = client.get("/api/config/settings")
                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                self.assertNotIn("lootbug_founders", data)
                self.assertEqual(data["founders"]["FOUNDERS_CHECK_INTERVAL_S"], 90)
                self.assertTrue(data["startup_defaults"]["FOUNDERS_ENABLED"])
                self.assertNotIn("FOUNDERS_ENABLED", data["founders"])
                self.assertNotIn("FOUNDERS_CLOSE_TEMPLATE", data["founders"])
                self.assertNotIn("FOUNDERS_CLOSE_ROI", data["founders"])
                self.assertNotIn("FOUNDERS_POST_CLICK_DELAY_S", data["founders"])
                data["startup_defaults"]["FOUNDERS_ENABLED"] = False
                response = client.post("/api/config/settings", json=data)
                self.assertEqual(response.status_code, 200)
                saved = json.loads(path.read_text(encoding="utf-8"))
                self.assertNotIn("lootbug_founders", saved)
                self.assertEqual(saved["founders"], data["founders"])
                settings = {}
                apply_overrides_to_settings(settings, saved)
                self.assertFalse(settings["FOUNDERS_ENABLED"])


if __name__ == "__main__":
    unittest.main()
