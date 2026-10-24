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
    def test_new_intervals_win_and_legacy_key_is_removed(self):
        original = {"founders": {"FOUNDERS_CHECK_INTERVAL_S": 90,
                    "FOUNDERS_CHECK_INTERVAL_S_FIRST": 12,
                    "FOUNDERS_CHECK_INTERVAL_S_SLOW": 7200}}
        result = migrate_founders_settings(original)
        self.assertEqual(result["founders"], {"FOUNDERS_CHECK_INTERVAL_S_FIRST": 12,
                                            "FOUNDERS_CHECK_INTERVAL_S_SLOW": 7200})
        settings = {}
        apply_overrides_to_settings(settings, original)
        self.assertEqual(settings, result["founders"])
        self.assertIn("FOUNDERS_CHECK_INTERVAL_S", original["founders"])

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
        self.assertEqual(result["founders"]["FOUNDERS_CHECK_INTERVAL_S_FIRST"], 90)
        self.assertEqual(result["founders"]["FOUNDERS_LOG_LEVEL"], "TXT")
        self.assertTrue(result["startup_defaults"]["FOUNDERS_ENABLED"])
        self.assertNotIn("FOUNDERS_ENABLED", result["founders"])
        self.assertEqual(self.legacy, original)
        self.assertEqual(migrate_founders_settings(result), result)

    def test_explicit_founders_settings_win_and_no_longer_follow_lootbug(self):
        self.legacy["founders"] = {"FOUNDERS_CHECK_INTERVAL_S": 120}
        result = migrate_founders_settings(self.legacy)
        result["lootbug"]["LOOTBUG_CHECK_INTERVAL_S"] = 5
        self.assertEqual(migrate_founders_settings(result)["founders"]["FOUNDERS_CHECK_INTERVAL_S_FIRST"], 120)

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
            "FOUNDERS_CHECK_INTERVAL_S_FIRST": 42, "FOUNDERS_CHECK_INTERVAL_S_SLOW": 3600, "FOUNDERS_BUSY_RETRY_S": 7,
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
        self.feature.find_template.side_effect = [
            {"found": True, "score": 0.99, "cx": 21, "cy": 22},
            {"found": False, "score": 0.1}]
        self.assertEqual(self.feature._try_run_with_lock(), "ok")
        self.feature.tap.assert_called_once_with(21, 22, jitter=2)
        matches = self.feature.find_template.call_args_list
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].kwargs, {"roi": (10, 20, 30, 40), "threshold": 0.91})
        self.assertEqual(self.state.founders_clicked_count, 1)
        self.assertEqual(self.state.founders_last_click_ts, 100)
        self.assertFalse(self.state.ingame_action_lock.locked())
        self.feature.get_cached_screen.assert_called_once_with("game_scr", max_age=5.0)
        self.feature.get_screen.assert_called_once_with("founders_scr", max_age=0.0, force=True)
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

    def test_double_spawn_uses_fresh_frames_after_each_click_under_lock(self):
        hit = {"found": True, "score": .99, "cx": 21, "cy": 22}
        miss = {"found": False, "score": .1}
        self.feature.find_template.side_effect = [hit, hit, miss]
        def capture(*args, **kwargs):
            self.assertTrue(self.state.ingame_action_lock.locked())
            return object(), 900, 1600
        self.feature.get_screen.side_effect = capture
        self.assertEqual(self.feature._try_run_with_lock(), "ok")
        self.assertEqual(self.feature.tap.call_count, 2)
        self.assertEqual(self.state.founders_clicked_count, 2)
        self.assertEqual(self.feature.get_screen.call_count, 2)
        for call in self.feature.get_screen.call_args_list:
            self.assertEqual(call.args, ("founders_scr",))
            self.assertEqual(call.kwargs, {"max_age": 0.0, "force": True})
        self.assertFalse(self.state.ingame_action_lock.locked())
        self.assertFalse(self.state.founders_followup_pending)

    def test_persistent_detection_is_bounded_and_keeps_short_followup(self):
        self.settings.FOUNDERS_MAX_CLAIMS_PER_CYCLE = 2
        self.feature.find_template.return_value = {"found": True, "score": .99, "cx": 21, "cy": 22}
        self.assertEqual(self.feature._try_run_with_lock(), "pending")
        self.assertEqual(self.feature.tap.call_count, 2)
        self.assertEqual(self.feature.find_template.call_count, 3)
        self.assertEqual(self.feature.get_screen.call_count, 2)
        self.assertTrue(self.state.founders_followup_pending)
        self.assertFalse(self.state.ingame_action_lock.locked())
        self.feature.find_template.return_value = {"found": False, "score": .1}
        self.assertEqual(self.feature._try_run_with_lock(), "ok")
        self.assertFalse(self.state.founders_followup_pending)

    def test_missing_fresh_followup_never_reuses_cache_and_requests_retry(self):
        self.feature.find_template.return_value = {"found": True, "score": .99, "cx": 21, "cy": 22}
        self.feature.get_screen.return_value = (None, 0, 0)
        self.assertEqual(self.feature._try_run_with_lock(), "pending")
        self.feature.tap.assert_called_once()
        self.feature.get_cached_screen.assert_called_once()
        self.assertFalse(self.state.ingame_action_lock.locked())

    def test_failed_second_bundle_tap_requests_short_retry_without_counting_it(self):
        self.feature.find_template.return_value = {"found": True, "score": .99, "cx": 21, "cy": 22}
        self.feature.tap.side_effect = [True, False]
        self.assertEqual(self.feature._try_run_with_lock(), "pending")
        self.assertEqual(self.state.founders_clicked_count, 1)
        self.assertTrue(self.state.founders_followup_pending)
        self.assertEqual(self.feature.get_screen.call_count, 1)
        self.assertFalse(self.state.ingame_action_lock.locked())

    def test_disable_after_success_prevents_clicking_second_bundle(self):
        self.feature.find_template.return_value = {"found": True, "score": .99, "cx": 21, "cy": 22}
        def click(*args, **kwargs):
            self.state.founders_enabled = False
            return True
        self.feature.tap.side_effect = click
        self.feature._try_run_with_lock()
        self.feature.tap.assert_called_once()
        self.assertFalse(self.state.ingame_action_lock.locked())

    def test_worker_uses_own_interval_and_retry_policy(self):
        for result, delay in (("ok", 42), ("busy", 7), ("pending", 7), ("no_game", 30)):
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
                self.feature.bot_log.assert_any_call(
                    f"[FOUNDERS] next check in {delay:g}s (mode=FIRST, reason={result})", "FULL")

    def test_first_detection_switches_immediately_and_misses_keep_slow_mode(self):
        self.assertEqual(self.feature._check_interval(), 42)
        self.feature.find_template.side_effect = [
            {"found": True, "score": .99, "cx": 21, "cy": 22},
            {"found": False, "score": .1}]
        sleeps = []

        def sleep_once(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 2:
                self.feature._stop_evt.set()

        with patch.object(self.feature, "_sleep_interruptible", side_effect=sleep_once):
            self.feature._worker()
        self.assertEqual(sleeps, [3.0, 3600])
        self.assertEqual(self.state.founders_next_check_ts, 3700)
        self.feature.find_template.side_effect = None
        self.feature.find_template.return_value = {"found": False, "score": .1}
        self.assertFalse(self.feature._run_scan_cycle())
        self.assertEqual(self.feature._check_interval(), 3600)
        self.assertFalse(self.feature.toggle())
        self.assertTrue(self.feature.toggle())
        self.assertEqual(self.feature._check_interval(), 42)
        self.assertEqual(self.state.founders_next_check_ts, 0)

    def test_reactivation_during_scan_keeps_first_mode(self):
        def match(*args, **kwargs):
            self.feature.toggle()
            self.feature.toggle()
            return {"found": True, "score": .99, "cx": 21, "cy": 22}

        self.feature.find_template.side_effect = match
        self.feature._run_scan_cycle()
        self.assertEqual(self.feature._check_interval(), 42)

    def test_detection_with_failed_click_changes_mode_without_counting(self):
        self.feature.find_template.return_value = {"found": True, "score": .99, "cx": 21, "cy": 22}
        self.feature.tap.return_value = False
        self.assertFalse(self.feature._run_scan_cycle())
        self.assertEqual(self.feature._check_interval(), 3600)
        self.assertEqual(self.state.founders_clicked_count, 0)

    def test_start_resets_phase_without_starting_a_real_worker_in_test(self):
        self.feature._detected_generation = self.feature._activation_generation
        self.assertEqual(self.feature._check_interval(), 3600)
        with patch.object(self.feature.threading, "Thread") as thread:
            self.feature.start()
            self.feature.start()
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()
        self.assertEqual(self.feature._check_interval(), 42)

    def test_logs_explain_phase_changes_reactivation_and_next_check(self):
        self.feature.find_template.side_effect = [
            {"found": True, "score": .99, "cx": 21, "cy": 22},
            {"found": False, "score": .1}]
        sleeps = []

        def sleep_once(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 2:
                self.feature._stop_evt.set()

        with patch.object(self.feature, "_sleep_interruptible", side_effect=sleep_once):
            self.feature._worker()
        self.feature.find_template.side_effect = None
        self.feature.find_template.return_value = {"found": True, "score": .99, "cx": 21, "cy": 22}
        self.feature._run_scan_cycle()
        self.feature.toggle()
        self.feature.toggle()
        messages = [call.args[0] for call in self.feature.bot_log.call_args_list]
        self.assertIn("[FOUNDERS] worker thread started (enabled=True, mode=FIRST, FIRST=42s, SLOW=3600s)", messages)
        transition = "[FOUNDERS] first bundle detected -> mode=SLOW (interval=3600s)"
        self.assertEqual(messages.count(transition), 1)
        self.assertIn("[FOUNDERS] next check in 3600s (mode=SLOW, reason=ok)", messages)
        self.assertIn("[FOUNDERS] toggled -> OFF", messages)
        self.assertIn("[FOUNDERS] toggled -> ON (mode=FIRST, interval=42s; checking now)", messages)

    def test_worker_uses_own_interval_and_retry_policy_for_slow(self):
        self.feature._detected_generation = self.feature._activation_generation
        for result, delay in (("ok", 3600), ("busy", 7), ("no_game", 30)):
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
    def test_priority_and_retry_settings_api_roundtrip_and_validation(self):
        api = load_module("priority_config_api_under_test", "web/config_api.py")
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root = Path(folder)
            (root / "config").mkdir()
            app = Flask(__name__)
            app.register_blueprint(api.config_bp)
            with patch.object(api, "BASE_DIR", root), patch.object(api, "_push_log"):
                client = app.test_client()
                response = client.get("/api/config/settings")
                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                for section, key, default, chosen in (
                    ("lootbug", "LOOTBUG_BUY_MAX_ATTEMPTS", 5, 4),
                    ("lootbug", "LOOTBUG_FOUNDERS_LOOKAHEAD_S", 5, 7),
                    ("founders", "FOUNDERS_MAX_CLAIMS_PER_CYCLE", 3, 2),
                ):
                    self.assertEqual(data[section][key], default)
                    data[section][key] = chosen
                self.assertEqual(client.post("/api/config/settings", json=data).status_code, 200)
                self.assertEqual(client.get("/api/config/settings").get_json(), data)
                target = {}
                apply_overrides_to_settings(target, data)
                self.assertEqual(target["LOOTBUG_BUY_MAX_ATTEMPTS"], 4)
                self.assertEqual(target["LOOTBUG_FOUNDERS_LOOKAHEAD_S"], 7)
                self.assertEqual(target["FOUNDERS_MAX_CLAIMS_PER_CYCLE"], 2)
                path = root / "config/user_settings.json"
                saved = path.read_bytes()
                for section, key in (("lootbug", "LOOTBUG_BUY_MAX_ATTEMPTS"),
                                     ("founders", "FOUNDERS_MAX_CLAIMS_PER_CYCLE")):
                    for invalid in (0, -1, 1.5, True, "3", 101):
                        bad = copy.deepcopy(data)
                        bad[section][key] = invalid
                        self.assertEqual(client.post("/api/config/settings", json=bad).status_code, 400)
                        self.assertEqual(path.read_bytes(), saved)
                for invalid in (-1, True, "5", float("inf")):
                    bad = copy.deepcopy(data)
                    bad["lootbug"]["LOOTBUG_FOUNDERS_LOOKAHEAD_S"] = invalid
                    self.assertEqual(client.post("/api/config/settings", json=bad).status_code, 400)
                    self.assertEqual(path.read_bytes(), saved)
                data["lootbug"]["LOOTBUG_FOUNDERS_LOOKAHEAD_S"] = 0
                self.assertEqual(client.post("/api/config/settings", json=data).status_code, 200)

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
                self.assertEqual(data["founders"]["FOUNDERS_CHECK_INTERVAL_S_FIRST"], 90)
                self.assertGreater(data["founders"]["FOUNDERS_CHECK_INTERVAL_S_SLOW"], 0)
                self.assertNotIn("FOUNDERS_CHECK_INTERVAL_S", data["founders"])
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
                for key in ("FOUNDERS_CHECK_INTERVAL_S_FIRST", "FOUNDERS_CHECK_INTERVAL_S_SLOW"):
                    for invalid in (0, -1, "invalid"):
                        bad = copy.deepcopy(data)
                        bad["founders"][key] = invalid
                        self.assertEqual(client.post("/api/config/settings", json=bad).status_code, 400)
                        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), saved)
                settings = {}
                apply_overrides_to_settings(settings, saved)
                self.assertFalse(settings["FOUNDERS_ENABLED"])


if __name__ == "__main__":
    unittest.main()
