"""Regression tests for the single-click Lootbug buy-box flow (no ADB)."""
import copy
import sys
import unittest
from unittest.mock import patch

import test_founders as helpers
from config.user_overrides import normalize_user_settings, apply_overrides_to_settings


class LootbugTests(unittest.TestCase):
    def setUp(self):
        helpers.FeatureTests.setUp(self)
        self.settings.BASE_DIR = helpers.ROOT
        self.settings.LOOTBUG_TEMPLATE_GLOB = "Lootbug/lootbug_tpl_*.png"
        self.settings.LOOTBUG_BONUS_BUY_ROI = (310, 370, 505, 672)
        self.settings.LOOTBUG_BONUS_BUY_TEMPLATE = "Lootbug/lootbug_buy_bonus.png"
        self.settings.LOOTBUG_BONUS_TAP_JITTER_PX = 3
        self.settings.LOOTBUG_BUY_RETRY_S = 3.0
        self.settings.LOOTBUG_CHECK_INTERVAL_S = 90.0
        self.settings.LOOTBUG_BUSY_RETRY_S = 15.0
        self.settings.LOOTBUG_INTERVAL_VARIANCE_PCT = 15.0
        self.settings.LOOTBUG_POST_CLICK_DELAY_S = 1.2
        self.state.lootbug_enabled = True
        self.state.lootbug_bonus_count = 0
        stubs = {"config.settings": self.settings, "config.app_state": self.state}
        # Reuse the isolated core dependencies; never import the real ADB helper.
        import types
        for name, attr in (("core.file_logger", "bot_log"), ("core.screen_cache", "get_screen"),
                           ("core.vision", "find_template"), ("core.tapper", "tap"),
                           ("core.game_state", "is_game_running")):
            stub = types.ModuleType(name)
            setattr(stub, attr, getattr(self.feature, attr))
            if name == "core.screen_cache":
                stub.get_cached_screen = self.feature.get_cached_screen
            stubs[name] = stub
        with patch.dict(sys.modules, stubs):
            self.feature = helpers.load_module("lootbug_under_test", "features/lootbug.py")
        self.feature.s = self.settings
        self.feature.state = self.state
        self.feature.time = types.SimpleNamespace(sleep=helpers.Mock(), time=lambda: 100.0)
        self.feature._sleep_interruptible = helpers.Mock()
        self.feature.tap.return_value = True
        self.hit = {"found": True, "score": 0.99, "cx": 400, "cy": 500}
        self.miss = {"found": False, "score": 0.1}

    def test_buy_box_is_detected_and_clicked_once_without_bonus_mode(self):
        self.feature.find_template.side_effect = [dict(self.hit), dict(self.hit)]
        self.assertTrue(self.feature._run_scan_cycle())
        self.assertEqual(self.feature.tap.call_count, 2)  # Lootbug + one Buy click
        self.feature.tap.assert_called_with(400, 500, jitter=3)
        self.assertEqual(self.state.lootbug_bonus_count, 1)
        self.feature._sleep_interruptible.assert_called_once_with(1.2)
        self.feature.find_template.assert_called_with(
            self.feature.get_screen.return_value[0], "Lootbug/lootbug_buy_bonus.png",
            roi=(310, 370, 505, 672), threshold=0.8)
        self.assertEqual(self.feature.get_screen.call_args.args, ("lootbug_scr",))
        self.assertTrue(self.feature.get_screen.call_args.kwargs["force"])

    def test_obscured_buy_box_retries_with_lock_and_never_closes(self):
        self.feature.find_template.side_effect = [dict(self.hit), dict(self.miss), dict(self.miss), dict(self.hit)]
        waits = []

        def wait(seconds):
            self.assertTrue(self.state.ingame_action_lock.locked())
            waits.append(seconds)

        self.feature._sleep_interruptible.side_effect = wait
        self.assertEqual(self.feature._try_run_with_lock(), "ok")
        self.assertEqual(waits, [1.2, 3.0, 3.0])
        self.assertEqual(self.feature.tap.call_count, 2)
        self.assertEqual(self.state.lootbug_bonus_count, 1)
        self.assertEqual(self.feature.get_screen.call_count, 3)
        self.feature.get_cached_screen.assert_called_once_with("game_scr", max_age=5.0)
        for call in self.feature.find_template.call_args_list[1:]:
            self.assertEqual(call.args[1], "Lootbug/lootbug_buy_bonus.png")
        for call in self.feature.get_screen.call_args_list:
            self.assertEqual(call.args, ("lootbug_scr",))
            self.assertTrue(call.kwargs["force"])
        self.assertFalse(self.state.ingame_action_lock.locked())

    def test_disable_during_retry_stops_without_close_and_releases_lock(self):
        self.feature.find_template.side_effect = [dict(self.hit), dict(self.miss)]

        def wait(seconds):
            if seconds == 3.0:
                self.feature.toggle()

        self.feature._sleep_interruptible.side_effect = wait
        self.feature._try_run_with_lock()
        self.feature.tap.assert_called_once()
        self.assertEqual(self.state.lootbug_bonus_count, 0)
        self.assertFalse(self.state.ingame_action_lock.locked())
        self.assertTrue(self.feature._wake_evt.is_set())

    def test_failed_buy_is_retried_and_only_success_is_counted(self):
        self.feature.find_template.side_effect = [dict(self.hit), dict(self.hit), dict(self.hit)]
        self.feature.tap.side_effect = [True, False, True]
        self.feature._run_scan_cycle()
        self.assertEqual(self.feature.tap.call_count, 3)
        self.assertEqual(self.state.lootbug_bonus_count, 1)
        self.assertEqual([call.args[0] for call in self.feature._sleep_interruptible.call_args_list], [1.2, 3.0])

    def test_no_lootbug_does_not_click(self):
        self.feature.find_template.return_value = dict(self.miss)
        self.assertFalse(self.feature._run_scan_cycle())
        self.feature.tap.assert_not_called()

    def test_missing_shared_cache_captures_only_own_slot(self):
        self.feature.get_cached_screen.return_value = (None, 0, 0)
        self.feature._get_screen_for_scan()
        self.feature.get_screen.assert_called_once_with("lootbug_scr", max_age=0.0, force=True)

    def test_missing_popup_screenshot_is_retried(self):
        self.feature.find_template.side_effect = [dict(self.hit), dict(self.hit)]
        with patch.object(self.feature, "_fresh_own_screen", side_effect=[None, object()]):
            self.feature._run_scan_cycle()
        self.assertEqual(self.feature.tap.call_count, 2)
        self.assertEqual(self.state.lootbug_bonus_count, 1)
        self.assertEqual([call.args[0] for call in self.feature._sleep_interruptible.call_args_list], [1.2, 3.0])

    def test_disable_before_buy_does_not_click_buy(self):
        self.feature.find_template.return_value = dict(self.hit)
        self.feature._sleep_interruptible.side_effect = lambda seconds: self.feature.toggle()
        self.feature._run_scan_cycle()
        self.feature.tap.assert_called_once()
        self.assertEqual(self.state.lootbug_bonus_count, 0)

    def test_toggle_is_binary_and_leaves_founders_unchanged(self):
        self.assertFalse(self.feature.toggle())
        self.assertTrue(self.feature.toggle())
        self.assertTrue(self.state.founders_enabled)
        self.assertEqual(self.state.lootbug_next_check_ts, 0)

    def test_variance_bounds_zero_and_percentage_limits(self):
        for pct, draw, expected, bounds in (
            (15, -15, 76.5, (-15.0, 15.0)),
            (15, 15, 103.5, (-15.0, 15.0)),
            (1000, -100, 0.1, (-100.0, 100.0)),
        ):
            with self.subTest(pct=pct, draw=draw):
                self.settings.LOOTBUG_INTERVAL_VARIANCE_PCT = pct
                with patch.object(self.feature.random, "uniform", return_value=draw) as rng:
                    self.assertAlmostEqual(self.feature._next_scan_delay(90), expected)
                    rng.assert_called_once_with(*bounds)
        for pct in (0, -15):
            self.settings.LOOTBUG_INTERVAL_VARIANCE_PCT = pct
            with patch.object(self.feature.random, "uniform") as rng:
                self.assertEqual(self.feature._next_scan_delay(90), 90)
                rng.assert_not_called()

    def test_worker_sleep_and_published_deadline_use_the_same_single_draw(self):
        sleeps = []

        def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 2:
                self.assertAlmostEqual(self.state.lootbug_next_check_ts, 100 + seconds)
                self.feature._stop_evt.set()

        self.feature._sleep_interruptible.side_effect = sleep
        with patch.object(self.feature, "_try_run_with_lock", return_value="ok"), \
             patch.object(self.feature.random, "uniform", return_value=15) as rng:
            self.feature._worker()
        self.assertEqual(sleeps[0], 3.0)
        self.assertAlmostEqual(sleeps[1], 103.5)
        rng.assert_called_once_with(-15.0, 15.0)

    def test_busy_and_no_game_retries_do_not_randomize(self):
        for result, expected in (("busy", 15.0), ("no_game", 30.0)):
            with self.subTest(result=result):
                self.feature._stop_evt.clear()
                sleeps = []

                def sleep(seconds):
                    sleeps.append(seconds)
                    if len(sleeps) == 2:
                        self.assertEqual(self.state.lootbug_next_check_ts, 100 + seconds)
                        self.feature._stop_evt.set()

                self.feature._sleep_interruptible.side_effect = sleep
                with patch.object(self.feature, "_try_run_with_lock", return_value=result), \
                     patch.object(self.feature.random, "uniform") as rng:
                    self.feature._worker()
                self.assertEqual(sleeps, [3.0, expected])
                rng.assert_not_called()

    def test_status_countdown_uses_deadline_and_does_not_draw_again(self):
        import config
        import types
        complete_state = helpers.load_module("state_for_countdown", "config/app_state.py")
        for key, value in vars(complete_state).items():
            if not hasattr(self.state, key):
                setattr(self.state, key, value)
        self.state.lootbug_next_check_ts = 203.5
        adb_stub = types.ModuleType("core.adb_helper")
        adb_stub._connected = True
        adb_stub.get_active_device = lambda: "test-device"
        workflows_stub = types.ModuleType("config.config_workflows")
        workflows_stub.WORKFLOWS = {}
        builder = helpers.load_module("builder_for_countdown", "web/state_builder.py")
        builder.time = types.SimpleNamespace(time=lambda: 100.0)
        with patch.object(config, "app_state", self.state, create=True), \
             patch.dict(sys.modules, {"config.app_state": self.state, "core.adb_helper": adb_stub, "config.config_workflows": workflows_stub}), \
             patch.object(builder, "_get_gem_statistics", return_value={}), \
             patch.object(self.feature.random, "uniform") as rng:
            first = builder.build_state_dict()
            builder.time.time = lambda: 110.0
            second = builder.build_state_dict()
        self.assertTrue(first["started"], first)
        self.assertEqual(first["lootbug"]["next_check_remaining"], 103)
        self.assertEqual(second["lootbug"]["next_check_remaining"], 93)
        self.assertEqual(first["lootbug"]["next_check_ts"], second["lootbug"]["next_check_ts"])
        rng.assert_not_called()


class LootbugMigrationTests(unittest.TestCase):
    def test_legacy_fields_removed_and_old_rois_updated(self):
        old = {"lootbug": {
            "LOOTBUG_BUY_GEM_UPGRADES_ENABLED": False,
            "LOOTBUG_BONUS_DETECT_ROI": [1, 2, 3, 4],
            "LOOTBUG_BONUS_DOUBLE_CLICK_DELAY_S": 0.1,
            "LOOTBUG_BONUS_TEMPLATE_GLOB": "Lootbug/bonus_tpl_*.png",
            "LOOTBUG_BONUS_TEMPLATE": "deleted.png",
            "LOOTBUG_BONUS_BUY_ROI": [540, 846, 695, 914],
            "LOOTBUG_CLOSE_ROI": [395, 987, 503, 1085],
        }, "startup_defaults": {"lootbug_buy_bonus": True, "lootbug_enabled": True},
            "founders": {"FOUNDERS_CHECK_INTERVAL_S": 90}}
        original = copy.deepcopy(old)
        result = normalize_user_settings(old)
        self.assertEqual(old, original)
        self.assertEqual(result["lootbug"], {
            "LOOTBUG_BONUS_BUY_ROI": [310, 370, 505, 672],
        })
        self.assertEqual(result["startup_defaults"], {"lootbug_enabled": True})
        self.assertEqual(result["founders"], old["founders"])
        self.assertEqual(normalize_user_settings(result), result)
        settings = {}
        apply_overrides_to_settings(settings, old)
        self.assertEqual(settings["LOOTBUG_BONUS_BUY_ROI"], (310, 370, 505, 672))
        self.assertNotIn("LOOTBUG_BUY_GEM_UPGRADES_ENABLED", settings)

    def test_custom_roi_and_template_are_preserved(self):
        old = {"lootbug": {"LOOTBUG_BONUS_BUY_ROI": [10, 20, 30, 40],
                          "LOOTBUG_BONUS_BUY_TEMPLATE": "custom.png"}}
        self.assertEqual(normalize_user_settings(old), old)
        settings = {}
        apply_overrides_to_settings(settings, old)
        self.assertEqual(settings["LOOTBUG_BONUS_BUY_TEMPLATE"], "custom.png")

    def test_variance_override_is_applied(self):
        settings = {}
        apply_overrides_to_settings(settings, {"lootbug": {"LOOTBUG_INTERVAL_VARIANCE_PCT": 25}})
        self.assertEqual(settings["LOOTBUG_INTERVAL_VARIANCE_PCT"], 25)


if __name__ == "__main__":
    unittest.main()
