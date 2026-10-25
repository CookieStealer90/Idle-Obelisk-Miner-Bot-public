"""Freebie FIRST/SLOW scheduling, logs and configuration without game access."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from flask import Flask

from config.user_overrides import normalize_user_settings, apply_overrides_to_settings
import test_action_results as action_results
from test_founders import ROOT, load_module


class FreebieScheduleTests(unittest.TestCase):
    def setUp(self):
        action_results.FreebieResultTests.setUp(self)
        self.state.freebies_enabled = True
        self.state.freebies_next_check_ts = 0
        self.state.ingame_action_lock = threading.Lock()
        self.feature.is_game_running.return_value = True

    def test_disable_or_reactivation_after_open_prevents_claim_and_close(self):
        for reactivate in (False, True):
            with self.subTest(reactivate=reactivate):
                self.state.freebies_enabled = True
                self.feature.tap.reset_mock()
                def disable(*args, **kwargs):
                    self.feature.toggle()
                    if reactivate:
                        self.feature.toggle()
                    return True
                self.feature.tap.side_effect = disable
                self.assertFalse(self.feature._run_claim_cycle())
                self.feature.tap.assert_called_once()
                self.assertEqual(self.state.freebies_claimed_count, 0)

    def test_disable_during_long_animation_wait_stops_before_next_action(self):
        self.feature.s.FREEBIES_POST_OPEN_DELAY_S = 60
        def disable(seconds):
            self.assertLessEqual(seconds, 0.1)
            self.feature.toggle()
        self.feature.time.sleep.side_effect = disable
        self.assertFalse(self.feature._run_claim_cycle())
        self.feature.time.sleep.assert_called_once()
        self.feature.tap.assert_called_once()

    def test_disable_during_search_prevents_scroll_and_claim(self):
        calls = 0
        def match(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.feature.toggle()
                return {"found": False, "score": 0}
            return self.hit
        self.feature.find_template.side_effect = match
        self.assertFalse(self.feature._run_claim_cycle())
        self.feature.tap.assert_called_once()
        self.feature.scroll_down.assert_not_called()
        self.feature.scroll_up.assert_not_called()

    def test_disabled_statistics_does_not_track_enabled_freebies(self):
        self.state.gem_statistics_enabled = False
        self.feature._sync_statistics(True)
        self.stats.get_gem_statistics.return_value.set_active.assert_called_once_with(False)
        self.feature._run_claim_cycle()
        self.stats.get_gem_statistics.return_value.record_claim.assert_not_called()

    def test_disable_during_claim_counts_sent_tap_but_prevents_close(self):
        calls = 0
        def tap(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.feature.toggle()
            return True
        self.feature.tap.side_effect = tap
        self.assertFalse(self.feature._run_claim_cycle())
        self.assertEqual(calls, 2)
        self.assertEqual(self.state.freebies_claimed_count, 1)
        self.stats.get_gem_statistics.return_value.record_claim.assert_called_once_with(
            "gem", amount=28, in_flight=True)

    def run_checks(self, count=1):
        sleeps = []

        def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == count + 1:
                self.feature._stop_evt.set()

        with patch.object(self.feature, "_sleep_interruptible", side_effect=sleep):
            self.feature._worker()
        return sleeps

    def messages(self):
        return [call.args[0] for call in self.feature.bot_log.call_args_list]

    def test_first_detection_immediately_schedules_slow_and_logs_once(self):
        self.assertEqual(self.feature._check_interval(), 300)
        self.assertEqual(self.run_checks(), [3, 2700])
        self.assertEqual(self.state.freebies_next_check_ts, 2800)
        self.assertEqual(self.state.freebies_claimed_count, 1)
        self.assertFalse(self.state.ingame_action_lock.locked())
        self.feature._run_claim_cycle()
        messages = self.messages()
        self.assertIn("[FREEBIES] worker thread started (enabled=True, mode=FIRST, FIRST=300s, SLOW=2700s)", messages)
        self.assertEqual(messages.count("[FREEBIES] first freebie detected -> mode=SLOW (interval=2700s)"), 1)
        self.assertIn("[FREEBIES] next check in 2700s (mode=SLOW, reason=ok)", messages)

    def test_icon_miss_resets_fast_but_missing_screenshots_keep_current_phase(self):
        self.feature.find_template.return_value = {"found": False, "score": .1}
        self.assertEqual(self.run_checks(), [3, 300])
        self.assertEqual(self.state.freebies_next_check_ts, 400)
        self.feature.tap.assert_not_called()
        self.feature._stop_evt.clear()
        self.feature.get_screen.return_value = (None, 0, 0)
        self.assertFalse(self.feature._run_claim_cycle())
        self.assertEqual(self.feature._check_interval(), 300)
        self.feature._detected_generation = self.feature._activation_generation
        self.assertFalse(self.feature._run_claim_cycle())
        self.assertEqual(self.feature._check_interval(), 2700)
        self.feature.get_screen.return_value = (object(), 900, 1600)
        self.assertFalse(self.feature._run_claim_cycle())
        self.assertEqual(self.feature._check_interval(), 300)
        self.assertIn("[FREEBIES] no freebie detected -> mode=FIRST (fast checks, interval=300s)",
                      self.messages())

    def test_worker_resumes_fast_checks_until_either_icon_is_detected_again(self):
        miss = {"found": False, "score": .1}
        # Claim, two scans missing both icons, then claim via the second icon.
        self.feature.find_template.side_effect = [
            self.hit, self.hit, self.hit, miss, miss, miss, miss,
            miss, self.hit, self.hit, self.hit]
        deadlines = []
        sleeps = []

        def sleep(seconds):
            sleeps.append(seconds)
            deadlines.append(self.state.freebies_next_check_ts)
            if len(sleeps) == 5:
                self.feature._stop_evt.set()

        with patch.object(self.feature, "_sleep_interruptible", side_effect=sleep):
            self.feature._worker()
        self.assertEqual(sleeps, [3, 2700, 300, 300, 2700])
        self.assertEqual(deadlines, [0, 2800, 400, 400, 2800])
        self.assertEqual(self.state.freebies_claimed_count, 2)
        self.assertFalse(self.state.ingame_action_lock.locked())
        self.assertEqual(self.messages().count(
            "[FREEBIES] no freebie detected -> mode=FIRST (fast checks, interval=300s)"), 1)

    def test_cancelled_icon_miss_does_not_change_phase(self):
        for reactivate in (False, True):
            with self.subTest(reactivate=reactivate):
                self.state.freebies_enabled = True
                self.feature._detected_generation = self.feature._activation_generation

                def match(*args, **kwargs):
                    if self.state.freebies_enabled:
                        self.feature.toggle()
                        if reactivate:
                            self.feature.toggle()
                            self.feature._detected_generation = self.feature._activation_generation
                    return {"found": False, "score": .1}

                self.feature.find_template.side_effect = match
                self.assertFalse(self.feature._run_claim_cycle())
                self.assertEqual(self.feature._check_interval(), 2700)
                self.feature.tap.assert_not_called()

    def test_second_icon_also_switches_before_failed_tap_without_counting(self):
        self.feature.find_template.side_effect = [{"found": False, "score": .1}, self.hit]
        self.feature.tap.return_value = False
        self.assertFalse(self.feature._run_claim_cycle())
        self.assertEqual(self.feature._check_interval(), 2700)
        self.assertEqual(self.state.freebies_claimed_count, 0)
        self.assertEqual(self.state.freebies_last_claim_ts, 0)
        self.stats.get_gem_statistics.assert_not_called()

    def test_toggle_resets_phase_countdown_and_wakes_worker(self):
        self.feature._run_claim_cycle()
        self.assertEqual(self.feature._check_interval(), 2700)
        self.state.freebies_next_check_ts = 2800
        self.assertFalse(self.feature.toggle())
        self.assertEqual(self.state.freebies_next_check_ts, 0)
        self.feature._wake_evt.clear()
        self.assertTrue(self.feature.toggle())
        self.assertTrue(self.feature._wake_evt.is_set())
        self.assertEqual(self.feature._check_interval(), 300)
        self.stats.get_gem_statistics.return_value.set_active.assert_called_with(True)
        self.assertIn("[FREEBIES] toggled -> ON (mode=FIRST, interval=300s; checking now)", self.messages())
        self.assertIn("[FREEBIES] toggled -> OFF", self.messages())

    def test_old_scan_cannot_switch_reactivated_session(self):
        def match(*args, **kwargs):
            self.feature.toggle()
            self.feature.toggle()
            return self.hit

        self.feature.find_template.side_effect = match
        self.feature.tap.return_value = False
        self.feature._run_claim_cycle()
        self.assertEqual(self.feature._check_interval(), 300)
        self.assertFalse(any("mode=SLOW" in msg for msg in self.messages()))

    def test_start_resets_phase_once_and_keeps_statistics_hook(self):
        self.feature._detected_generation = self.feature._activation_generation
        with patch.object(self.feature.threading, "Thread") as thread:
            self.feature.start()
            self.feature.start()
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()
        self.assertEqual(self.feature._check_interval(), 300)
        self.stats.get_gem_statistics.return_value.set_active.assert_called_once_with(True)

    def test_game_absent_retries_remain_short_in_both_modes(self):
        self.feature.is_game_running.return_value = False
        for slow in (False, True):
            with self.subTest(slow=slow):
                self.feature._stop_evt.clear()
                if slow:
                    self.feature._detected_generation = self.feature._activation_generation
                self.assertEqual(self.run_checks(), [3, 30])
                self.assertEqual(self.state.freebies_next_check_ts, 130)
                mode = "SLOW" if slow else "FIRST"
                self.assertIn(f"[FREEBIES] next check in 30s (mode={mode}, reason=no_game)", self.messages())
        self.feature.get_screen.assert_not_called()

    def test_disabled_worker_never_captures_or_clicks(self):
        self.state.freebies_enabled = False
        self.assertEqual(self.run_checks(), [3, 5])
        self.assertEqual(self.state.freebies_next_check_ts, 0)
        self.feature.get_screen.assert_not_called()
        self.feature.tap.assert_not_called()

    def test_waiting_for_lock_is_logged_and_disable_prevents_queued_claim(self):
        feature = self.feature

        class BusyLock:
            def locked(self):
                return True

            def __enter__(self):
                feature.state.freebies_enabled = False

            def __exit__(self, *args):
                return False

        self.state.ingame_action_lock = BusyLock()
        self.assertEqual(self.run_checks(), [3, 300])
        self.assertIn("[FREEBIES] another feature is busy -> waiting for action lock", self.messages())
        self.feature.get_screen.assert_not_called()
        self.assertEqual(self.state.freebies_next_check_ts, 0)


class FreebieConfigTests(unittest.TestCase):
    def test_legacy_migration_preserves_input_and_explicit_new_values(self):
        old = {"freebies": {"FREEBIES_CHECK_INTERVAL_S": 75}}
        original = copy.deepcopy(old)
        migrated = normalize_user_settings(old)
        self.assertEqual(old, original)
        self.assertEqual(migrated, {"freebies": {"FREEBIES_CHECK_INTERVAL_S_FIRST": 75}})
        self.assertEqual(normalize_user_settings(migrated), migrated)
        old["freebies"].update(FREEBIES_CHECK_INTERVAL_S_FIRST=12,
                              FREEBIES_CHECK_INTERVAL_S_SLOW=2700)
        settings = {}
        apply_overrides_to_settings(settings, old)
        self.assertEqual(settings, {"FREEBIES_CHECK_INTERVAL_S_FIRST": 12,
                                    "FREEBIES_CHECK_INTERVAL_S_SLOW": 2700})

    def test_api_migrates_saves_and_validates_both_intervals(self):
        api = load_module("freebie_config_api_under_test", "web/config_api.py")
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root = Path(folder)
            (root / "config").mkdir()
            path = root / "config/user_settings.json"
            path.write_text(json.dumps({"freebies": {"FREEBIES_CHECK_INTERVAL_S": 75}}), encoding="utf-8")
            app = Flask(__name__)
            app.register_blueprint(api.config_bp)
            with patch.object(api, "BASE_DIR", root), patch.object(api, "_push_log"):
                client = app.test_client()
                response = client.get("/api/config/settings")
                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                self.assertEqual(data["freebies"]["FREEBIES_CHECK_INTERVAL_S_FIRST"], 75)
                self.assertEqual(data["freebies"]["FREEBIES_CHECK_INTERVAL_S_SLOW"], 2700)
                self.assertNotIn("FREEBIES_CHECK_INTERVAL_S", data["freebies"])
                data["freebies"]["FREEBIES_CHECK_INTERVAL_S_SLOW"] = 2800
                self.assertEqual(client.post("/api/config/settings", json=data).status_code, 200)
                saved = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(saved["freebies"], data["freebies"])
                for key in ("FREEBIES_CHECK_INTERVAL_S_FIRST", "FREEBIES_CHECK_INTERVAL_S_SLOW"):
                    for invalid in (0, -1, True, "45", None, float("inf")):
                        bad = copy.deepcopy(data)
                        bad["freebies"][key] = invalid
                        self.assertEqual(client.post("/api/config/settings", json=bad).status_code, 400)
                        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), saved)
