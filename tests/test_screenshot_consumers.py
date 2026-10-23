"""Screenshot consumers and config integration, without starting bot workers."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

import config
from flask import Flask
import numpy as np

from config.user_overrides import apply_overrides_to_settings, normalize_user_settings
from test_screen_cache import load, ROOT, png


class GameStateTests(unittest.TestCase):
    def setUp(self):
        self.settings = types.ModuleType("config.settings")
        self.settings.RUNNING_CHECK_CACHE_AGE_S = 15
        self.settings.RUNNING_ROI = (8, 3, 48, 43)
        self.settings.RUNNING_MATCH_THRESHOLD = 0.8
        self.state = types.ModuleType("config.app_state")
        self.state.game_running = True
        self.image = np.zeros((8, 12), dtype=np.uint8)
        self.cache = types.ModuleType("core.screen_cache")
        self.cache.get_screen = Mock(return_value=(self.image, 12, 8))
        self.cache.get_latest_cached_screen = Mock(return_value=(None, 0, 0, None, None))
        vision = types.ModuleType("core.vision")
        vision.find_template = Mock(return_value={"found": True, "score": 1.0})
        logger = types.ModuleType("core.file_logger")
        logger.bot_log = Mock()
        with patch.dict(sys.modules, {"config.settings": self.settings,
                                      "config.app_state": self.state,
                                      "core.screen_cache": self.cache,
                                      "core.vision": vision, "core.file_logger": logger}), \
             patch.object(config, "settings", self.settings, create=True), \
             patch.object(config, "app_state", self.state, create=True):
            self.game = load("game_state_under_test", "core/game_state.py")

    def test_fresh_shared_frame_avoids_capture_and_logs_source_on_transition(self):
        self.state.game_running = False
        self.cache.get_latest_cached_screen.return_value = (self.image, 12, 8, "freebie_scr", 2.5)
        self.assertTrue(self.game.is_game_running())
        self.cache.get_screen.assert_not_called()
        self.game.find_template.assert_called_once_with(self.image, "game_running.png",
                                                       roi=(8, 3, 48, 43), threshold=0.8)
        self.assertIn("source=cache:freebie_scr age=2.500s", self.game.bot_log.call_args.args[0])

    def test_missing_shared_frame_forces_new_own_capture(self):
        self.assertTrue(self.game.is_game_running())
        self.cache.get_screen.assert_called_once_with("game_scr", max_age=15.0, force=True)

    def test_force_bypasses_shared_cache(self):
        self.assertTrue(self.game.is_game_running(force=True))
        self.cache.get_latest_cached_screen.assert_not_called()
        self.cache.get_screen.assert_called_once_with("game_scr", max_age=15.0, force=True)

    def test_exhausted_capture_sets_stopped_without_matching_and_identifies_failure(self):
        self.cache.get_screen.return_value = (None, 0, 0)
        self.assertFalse(self.game.is_game_running())
        self.assertFalse(self.state.game_running)
        self.game.find_template.assert_not_called()
        message = self.game.bot_log.call_args.args[0]
        self.assertIn("after retries", message)
        self.assertIn("game stop unconfirmed", message)
        self.assertFalse(self.game.is_game_running())
        self.game.bot_log.assert_called_once()  # avoid flooding every main tick

    def test_valid_frame_without_match_still_sets_stopped(self):
        self.game.find_template.return_value = {"found": False, "score": 0.3}
        self.assertFalse(self.game.is_game_running())
        self.assertIn("score=0.300", self.game.bot_log.call_args.args[0])
        self.assertIn("source=fresh:game_scr", self.game.bot_log.call_args.args[0])

    def test_parallel_checks_do_not_publish_out_of_order(self):
        entered = threading.Event()
        release = threading.Event()
        second_started = threading.Event()

        def match(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(3))
            return {"found": True, "score": 1.0}

        self.game.find_template.side_effect = match

        def second():
            second_started.set()
            return self.game.is_game_running(force=True)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.game.is_game_running, True)
            self.assertTrue(entered.wait(3))
            other = pool.submit(second)
            self.assertTrue(second_started.wait(3))
            self.assertEqual(self.cache.get_screen.call_count, 1)
            release.set()
            self.assertTrue(first.result(timeout=3))
            self.assertTrue(other.result(timeout=3))
        self.assertEqual(self.cache.get_screen.call_count, 2)


class WorkflowScreenshotTests(unittest.TestCase):
    def setUp(self):
        settings = types.ModuleType("config.settings")
        state = types.ModuleType("config.app_state")
        stubs = {"config.settings": settings, "config.app_state": state}
        for name, attrs in {
            "core.screen_cache": {"get_screen": Mock(return_value=(None, 0, 0))},
            "core.file_logger": {"bot_log": Mock()},
            "core.vision": {"find_template": Mock()},
            "core.rotation_cache": {"find_template_rotating": Mock()},
            "core.tapper": {"tap": Mock()},
            "core.scroll": {"scroll": Mock()},
            "core.adb_helper": {"adb": Mock()},
            "core.game_state": {"is_game_running": Mock()},
            "config.config_workflows": {"WORKFLOWS": {}},
        }.items():
            module = types.ModuleType(name)
            module.__dict__.update(attrs)
            stubs[name] = module
        with patch.dict(sys.modules, stubs), \
             patch.object(config, "settings", settings, create=True), \
             patch.object(config, "app_state", state, create=True):
            self.workflow = load("workflow_capture_under_test", "features/workflows.py")

    def test_rainbow_failed_capture_never_reads_old_png(self):
        with patch.object(self.workflow.cv2, "imread") as imread:
            self.assertFalse(self.workflow._step_rainbow_check({"roi": [0, 0, 12, 8]}, {}))
        self.workflow.get_screen.assert_called_once_with("wf_scr", max_age=0.0, force=True, color=True)
        imread.assert_not_called()

    def test_rainbow_uses_validated_color_snapshot_and_retains_cache_option(self):
        self.workflow.get_screen.return_value = (np.full((8, 12, 3), 50, dtype=np.uint8), 12, 8)
        self.assertTrue(self.workflow._step_rainbow_check(
            {"roi": [0, 0, 12, 8], "use_prev_screenshot": True, "optional": True}, {}))
        self.workflow.get_screen.assert_called_once_with("wf_scr", max_age=2.0, force=False, color=True)

    def test_template_rotating_and_if_keep_workflow_slot(self):
        self.assertFalse(self.workflow._step_click_template({"template": "x"}, {}))
        self.assertFalse(self.workflow._step_click_rotating({"template": "x"}, {}))
        self.assertEqual(self.workflow._eval_condition(
            {"kind": "template_not_visible", "template": "x"}, {}, False, "false"), (False, False))
        self.assertEqual(self.workflow.get_screen.call_count, 3)
        for call in self.workflow.get_screen.call_args_list:
            self.assertEqual(call.args, ("wf_scr",))
            self.assertTrue(call.kwargs["force"])
        self.workflow.tap.assert_not_called()


class ConsumerSlotTests(unittest.TestCase):
    def setUp(self):
        self.settings = types.ModuleType("config.settings")
        state = types.ModuleType("config.app_state")
        self.cache = types.ModuleType("core.screen_cache")
        self.cache.get_screen = Mock(return_value=(None, 0, 0))
        self.cache.get_latest_cached_screen = Mock(return_value=(None, 0, 0, None, None))
        stubs = {"config.settings": self.settings, "config.app_state": state,
                 "core.screen_cache": self.cache}
        for name, attrs in {
            "core.file_logger": {"bot_log": Mock()},
            "core.vision": {"find_template": Mock()},
            "core.tapper": {"tap": Mock()},
            "core.scroll": {"scroll_up": Mock(), "scroll_down": Mock()},
            "core.game_state": {"is_game_running": Mock()},
        }.items():
            module = types.ModuleType(name)
            module.__dict__.update(attrs)
            stubs[name] = module
        with patch.dict(sys.modules, stubs), \
             patch.object(config, "settings", self.settings, create=True), \
             patch.object(config, "app_state", state, create=True):
            self.freebies = load("freebies_capture_under_test", "features/freebies.py")
            self.level = load("level_capture_under_test", "features/detect_level.py")

    def test_freebies_always_requests_fresh_own_full_screenshot(self):
        self.assertIsNone(self.freebies._fresh_screen())
        self.cache.get_screen.assert_called_once_with("freebie_scr", max_age=0.0, force=True)
        self.freebies.tap.assert_not_called()

    def test_level_uses_only_cache_before_capturing_own_slot(self):
        self.assertEqual(self.level._get_screen_for_scan(), (None, "level_scr"))
        self.cache.get_latest_cached_screen.assert_called_once_with(["level_scr"], 15.0)
        self.cache.get_screen.assert_called_once_with("level_scr", max_age=0.0, force=True)

    def test_level_reuses_shared_frame_without_capture(self):
        image = np.zeros((8, 12), dtype=np.uint8)
        self.cache.get_latest_cached_screen.return_value = (image, 12, 8, "freebie_scr", 1.5)
        result, slot = self.level._get_screen_for_scan()
        self.assertIs(result, image)
        self.assertEqual(slot, "freebie_scr")
        self.cache.get_screen.assert_not_called()


class ScreenshotConfigTests(unittest.TestCase):
    def test_valid_overrides_roundtrip_and_defaults_do_not_require_json_migration(self):
        values = {"SCREENSHOT_CAPTURE_ATTEMPTS": 3, "SCREENSHOT_RETRY_DELAY_S": 0.4,
                  "SCREENSHOT_LOG_LEVEL": "FULL", "SCREENSHOT_LOG_CACHE_HITS": True}
        target = {}
        apply_overrides_to_settings(target, {"screenshot_capture": values})
        self.assertEqual(target, values)
        self.assertEqual(normalize_user_settings({}), {})

    def test_invalid_values_are_rejected(self):
        for key, values in {
            "SCREENSHOT_CAPTURE_ATTEMPTS": [0, 6, 1.5, True, "2", float("nan")],
            "SCREENSHOT_RETRY_DELAY_S": [-0.1, 11, True, "0.2", float("inf"), float("nan")],
            "SCREENSHOT_LOG_LEVEL": ["DEBUG", None],
            "SCREENSHOT_LOG_CACHE_HITS": ["false", 1, None],
        }.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    normalize_user_settings({"screenshot_capture": {key: value}})

    def test_api_exposes_options_saves_and_rejects_invalid_without_overwrite(self):
        api = load("screenshot_config_api_under_test", "web/config_api.py")
        # Keep this independent of the user's future screenshot overrides.
        from config import settings as runtime_settings
        settings = types.ModuleType("config.settings")
        settings.__dict__.update(vars(runtime_settings))
        settings.SCREENSHOT_CAPTURE_ATTEMPTS = 2
        settings.SCREENSHOT_RETRY_DELAY_S = 0.2
        settings.SCREENSHOT_LOG_LEVEL = "TXT"
        settings.SCREENSHOT_LOG_CACHE_HITS = False
        (ROOT / "temp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "temp", prefix="screenshot-api-tests-") as folder:
            root = Path(folder)
            (root / "config").mkdir()
            path = root / "config/user_settings.json"
            path.write_text("{}", encoding="utf-8")
            app = Flask(__name__)
            app.register_blueprint(api.config_bp)
            with patch.object(api, "BASE_DIR", root), patch.object(api, "_push_log"), \
                 patch.object(config, "settings", settings, create=True):
                client = app.test_client()
                response = client.get("/api/config/settings")
                self.assertEqual(response.status_code, 200)
                options = response.get_json()["screenshot_capture"]
                self.assertEqual(options, {"SCREENSHOT_CAPTURE_ATTEMPTS": 2, "SCREENSHOT_RETRY_DELAY_S": 0.2,
                                           "SCREENSHOT_LOG_LEVEL": "TXT", "SCREENSHOT_LOG_CACHE_HITS": False})
                options["SCREENSHOT_CAPTURE_ATTEMPTS"] = 3
                self.assertEqual(client.post("/api/config/settings", json={"screenshot_capture": options}).status_code, 200)
                original = path.read_bytes()
                options["SCREENSHOT_CAPTURE_ATTEMPTS"] = 0
                self.assertEqual(client.post("/api/config/settings", json={"screenshot_capture": options}).status_code, 400)
                self.assertEqual(path.read_bytes(), original)


class ViewerRouteTests(unittest.TestCase):
    def test_response_streams_owned_bytes_without_starting_bot_or_using_adb(self):
        cache = types.ModuleType("core.screen_cache")
        cache.latest_cached_png = Mock(return_value=(png(), "game_scr.png"))
        # Importing web.app defines routes; it does not call run_server.
        web = load("screenshot_web_under_test", "web/app.py")
        with patch.dict(sys.modules, {"core.screen_cache": cache}), \
             patch.object(web, "enforce_dashboard_access_policy", return_value=None):
            client = web.app.test_client()
            response = client.get("/api/screenshot")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, png())
            self.assertEqual(response.mimetype, "image/png")
            self.assertEqual(response.cache_control.max_age, 0)
            cache.latest_cached_png.return_value = (None, None)
            self.assertEqual(client.get("/api/screenshot").status_code, 404)
        self.assertIsNone(web._bot_thread)


if __name__ == "__main__":
    unittest.main()
