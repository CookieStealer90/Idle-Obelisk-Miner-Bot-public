"""Freebie statistics lifecycle and persistence; no bot, ADB or real statistics."""
from concurrent.futures import ThreadPoolExecutor
import datetime
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

from flask import Flask
from test_founders import load_module
import test_screenshot_consumers as consumers


class StatisticsTests(unittest.TestCase):
    def test_paused_ticker_does_not_write_unchanged_statistics(self):
        self.gs.set_active(True)
        self.now += 10
        self.gs.set_active(False)
        ticks = 0
        def sleep(seconds):
            nonlocal ticks
            ticks += 1
            if ticks > 3:
                raise StopIteration
            self.now += seconds
        self.module.time.sleep = sleep
        with patch.object(self.gs, "_save") as save, self.assertRaises(StopIteration):
            self.gs._uptime_ticker()
        save.assert_not_called()

    def test_inflight_claim_is_counted_after_pause_but_manual_claims_stay_blocked(self):
        self.gs.set_active(True)
        self.gs.set_active(False)
        self.assertEqual(self.gs.record_claim(amount=28, in_flight=True), 28)
        self.assertIsNone(self.gs.record_claim(amount=28))
        self.assertFalse(self.gs.get_stats()["active"])
        self.assertEqual(self.gs.get_stats()["gem_alltime"], 28)

    def test_utc_buckets_distinguish_repeated_local_hour_and_migrate_once(self):
        timestamps = [datetime.datetime.fromisoformat(value).timestamp() for value in
                      ("2026-10-25T02:30:00+02:00", "2026-10-25T02:30:00+01:00")]
        self.assertEqual([self.gs._bucket_key(ts) for ts in timestamps],
                         ["2026-10-25-00", "2026-10-25-01"])
        legacy = {"hourly_buckets": {"2026-10-01-12": {"gems": 28, "uptime_s": 60}},
                  "stats_start_ts": self.now, "alltime_gems": 28, "alltime_uptime_s": 60,
                  "alltime_uptime_complete": True}
        self.path.write_text(json.dumps(legacy))
        migrated = self.module.GemStatistics()
        key = migrated._bucket_key(datetime.datetime(2026, 10, 1, 12).timestamp())
        self.assertEqual(migrated._data["hourly_buckets"], {key: {"gems": 28, "uptime_s": 60}})
        migrated.set_active(False)
        original = self.path.read_bytes()
        restarted = self.module.GemStatistics()
        restarted.set_active(False)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(restarted.get_stats()["gem_alltime"], 28)

    def test_system_clock_correction_does_not_inflate_active_uptime(self):
        self.gs.set_active(True)
        monotonic = self.now
        self.module.time.monotonic = lambda: monotonic
        self.now += 86400
        monotonic += 10
        self.assertEqual(self.gs.get_stats()["uptime_alltime_s"], 10)
        self.now -= 2 * 86400
        monotonic += 5
        self.assertEqual(self.gs.get_stats()["uptime_alltime_s"], 15)

    def setUp(self):
        self.module = load_module("gem_statistics_under_test", "features/gem_statistics.py")
        directory = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent.parent)
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "stats.json"
        self.now = datetime.datetime(2026, 10, 1, 12).timestamp()
        self.module._STATS_FILE = self.path
        self.module.time = types.SimpleNamespace(time=lambda: self.now, monotonic=lambda: self.now, sleep=Mock())
        self.module.threading = types.SimpleNamespace(Lock=threading.Lock, Thread=Mock())
        self.gs = self.module.GemStatistics()

    def advance(self, seconds):
        self.now += seconds
        return self.gs.get_stats()

    def test_inactive_initialization_never_starts_period_or_counts_claims(self):
        self.advance(86400 * 8)
        self.assertIsNone(self.gs.record_claim(amount=28))
        stats = self.gs.get_stats()
        self.assertFalse(stats["active"])
        self.assertEqual(stats["stats_start_ts"], 0)
        self.assertEqual(stats["uptime_session_s"], 0)
        self.assertEqual(stats["gem_alltime"], 0)
        self.assertIsNone(stats["gem_last_7d"])

    def test_first_activation_counts_search_time_and_unlocks_without_any_claim(self):
        self.advance(1234)
        start = self.now
        self.gs.set_active(True)
        stats = self.advance(3600)
        self.assertEqual(stats["stats_start_ts"], start)
        self.assertEqual(stats["first_event_ts"], 0)
        self.assertEqual(stats["uptime_session_s"], 3600)
        self.assertEqual(stats["gem_avg_per_hour_alltime"], 0)
        self.assertIsNone(stats["gem_last_24h"])
        self.gs.set_active(False)
        stats = self.advance(86400 - 3600)
        self.assertEqual(stats["gem_last_24h"], 0)
        self.assertEqual(stats["wallclock_remaining_7d_s"], 6 * 86400)
        stats = self.advance(6 * 86400)
        self.assertEqual(stats["gem_last_7d"], 0)
        self.assertEqual(stats["uptime_session_s"], 3600)

    def test_pause_resume_keeps_start_and_uses_different_average_denominators(self):
        self.gs.set_active(True)
        start = self.now
        self.advance(3600)
        self.gs.record_claim(amount=28)
        self.gs.set_active(False)
        self.advance(7200)
        self.assertIsNone(self.gs.record_claim(amount=28))
        self.gs.set_active(True)
        stats = self.advance(3600)
        self.assertEqual(stats["stats_start_ts"], start)
        self.assertEqual(stats["uptime_alltime_s"], 7200)
        self.assertEqual(stats["gem_alltime"], 28)
        self.assertEqual(stats["gem_avg_per_hour_session"], 14)
        self.assertEqual(stats["gem_avg_per_hour_uptime_alltime"], 14)
        self.assertEqual(stats["gem_avg_per_hour_alltime"], 7)

    def test_toggle_between_ticks_accounts_exact_active_intervals(self):
        self.gs.set_active(True)
        self.now += 15
        self.gs.set_active(False)
        self.now += 30
        self.gs.set_active(True)
        stats = self.advance(10)
        self.assertEqual(stats["uptime_alltime_s"], 25)
        self.assertEqual(stats["wallclock_alltime_s"], 55)

    def test_restart_preserves_totals_and_excludes_offline_time_from_uptime(self):
        self.gs.set_active(True)
        start = self.now
        self.advance(3600)
        self.gs.record_claim(amount=28)  # saves current uptime too
        self.now += 86400
        restarted = self.module.GemStatistics()
        stats = restarted.get_stats()
        self.assertFalse(stats["active"])
        self.assertEqual(stats["uptime_session_s"], 0)
        self.assertEqual(stats["gem_since_startup"], 0)
        self.assertEqual(stats["uptime_alltime_s"], 3600)
        self.assertEqual(stats["gem_alltime"], 28)
        self.assertEqual(stats["stats_start_ts"], start)
        restarted.set_active(True)
        self.now += 60
        self.assertEqual(restarted.get_stats()["uptime_alltime_s"], 3660)

    def test_active_reset_clears_session_and_ticks_without_replacing_thread(self):
        self.gs.set_active(True)
        self.advance(36000)
        self.gs.record_claim(amount=280)
        thread = self.gs._tick_thread
        self.gs.reset()
        stats = self.gs.get_stats()
        for key in ("uptime_session_s", "uptime_alltime_s", "gem_since_startup", "gem_alltime"):
            self.assertEqual(stats[key], 0)
        self.assertEqual(stats["stats_start_ts"], self.now)
        self.assertEqual(stats["last_reset_ts"], self.now)
        self.assertIsNone(stats["gem_last_24h"])
        self.assertIs(self.gs._tick_thread, thread)
        self.advance(3600)
        self.gs.record_claim(amount=28)
        self.assertEqual(self.gs.get_stats()["gem_avg_per_hour_session"], 28)
        self.assertEqual(json.loads(self.path.read_text())["alltime_uptime_s"], 3600)

    def test_inactive_reset_waits_for_activation_including_after_restart(self):
        self.gs.set_active(True)
        self.gs.record_claim(amount=28)
        self.gs.set_active(False)
        self.gs.reset()
        self.now += 86400
        self.gs = self.module.GemStatistics()
        self.assertEqual(self.gs.get_stats()["stats_start_ts"], 0)
        self.gs.set_active(True)
        self.assertEqual(self.gs.get_stats()["stats_start_ts"], self.now)
        self.assertEqual(self.gs.get_stats()["wallclock_remaining_24h_s"], 86400)

    def test_fourteen_days_prune_history_but_preserve_alltime_sums(self):
        self.gs.set_active(True)
        for _ in range(14 * 24):
            self.gs.record_claim(amount=28)
            self.advance(3600)
        stats = self.gs.get_stats()
        self.assertLessEqual(len(self.gs._data["hourly_buckets"]), 169)
        self.assertEqual(stats["gem_alltime"], 14 * 24 * 28)
        self.assertEqual(stats["uptime_alltime_s"], 14 * 86400)
        self.assertEqual(stats["gem_avg_per_hour_uptime_alltime"], 28)

    def test_old_claims_expire_while_paused_and_hour_boundary_remains_approximate(self):
        self.gs.set_active(True)
        self.gs.record_claim(amount=28)
        self.gs.set_active(False)
        stats = self.advance(7 * 86400 + 59 * 60)
        self.assertEqual(stats["gem_last_7d"], 28)  # accepted hourly precision
        stats = self.advance(60)
        self.assertEqual(stats["gem_last_7d"], 0)
        self.assertEqual(stats["gem_alltime"], 28)

    def test_concurrent_reads_and_claims_do_not_double_count_uptime(self):
        self.gs.set_active(True)
        self.now += 3600
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.gs.record_claim(amount=28), range(20)))
            list(pool.map(lambda _: self.gs.get_stats(), range(20)))
        self.assertEqual(self.gs.get_stats()["gem_alltime"], 560)
        self.assertEqual(self.gs.get_stats()["uptime_alltime_s"], 3600)

    def test_legacy_migration_keeps_gems_without_claiming_exact_historical_uptime(self):
        legacy = {"hourly_buckets": {"2026-09-30-12": {"gems": 28, "uptime_s": 3600}},
                  "alltime_gems": 2800, "first_event_ts": self.now - 10 * 86400,
                  "last_reset_ts": 0}
        self.path.write_text(json.dumps(legacy))
        self.gs = self.module.GemStatistics()
        stats = self.gs.get_stats()
        self.assertEqual(stats["gem_alltime"], 2800)
        self.assertFalse(stats["alltime_uptime_complete"])
        self.assertIsNone(stats["uptime_alltime_s"])
        self.assertIsNone(stats["gem_avg_per_hour_uptime_alltime"])
        self.gs.set_active(True)
        self.gs = self.module.GemStatistics()
        self.assertFalse(self.gs.get_stats()["alltime_uptime_complete"])
        self.gs.reset()
        self.assertTrue(self.gs.get_stats()["alltime_uptime_complete"])

    def test_invalid_file_and_failed_saves_are_not_silently_accepted(self):
        self.path.write_text('{bad json')
        with self.assertRaises(ValueError):
            self.module.GemStatistics()
        self.assertEqual(self.path.read_text(), '{bad json')
        with patch.object(self.module, "atomic_write_json", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.gs.reset()

    def test_failed_reset_keeps_existing_totals_and_session_in_memory_and_on_disk(self):
        self.gs.set_active(True)
        self.advance(3600)
        self.gs.record_claim(amount=28)
        original = self.path.read_bytes()
        with patch.object(self.module, "atomic_write_json", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.gs.reset()
        stats = self.gs.get_stats()
        self.assertEqual(stats["gem_alltime"], 28)
        self.assertEqual(stats["gem_since_startup"], 28)
        self.assertEqual(stats["uptime_session_s"], 3600)
        self.assertEqual(self.path.read_bytes(), original)

    def test_background_ticker_checkpoints_and_continues_after_a_save_failure(self):
        self.gs.set_active(True)
        calls = 0

        def sleep(seconds):
            nonlocal calls
            calls += 1
            if calls > 2:
                raise StopIteration
            self.now += seconds

        self.module.time.sleep = sleep
        with patch.object(self.gs, "_save", side_effect=[OSError("disk full"), None]) as save:
            with self.assertWarns(RuntimeWarning), self.assertRaises(StopIteration):
                self.gs._uptime_ticker()
            self.assertEqual(save.call_count, 2)
        self.assertEqual(self.gs.get_stats()["uptime_alltime_s"], 120)

    def test_manual_add_api_rejects_inactive_and_reset_keeps_paused(self):
        api = load_module("stats_api_under_test", "web/config_api.py")
        app = Flask(__name__)
        app.register_blueprint(api.config_bp)
        stub = types.ModuleType("features.gem_statistics")
        stub.get_gem_statistics = lambda: self.gs
        settings = types.ModuleType("config.settings")
        settings.FREEBIES_DIAMONDS_PER_CLAIM = 28
        import config
        with patch.dict(sys.modules, {"features.gem_statistics": stub, "config.settings": settings}), \
             patch.object(config, "settings", settings, create=True), patch.object(api, "_push_log"):
            client = app.test_client()
            self.assertEqual(client.post("/api/gem_stats/manual_add", json={}).status_code, 409)
            self.gs.set_active(True)
            response = client.post("/api/gem_stats/manual_add", json={})
            self.assertEqual(response.json, {"ok": True, "amount": 28})
            self.gs.set_active(False)
            self.assertEqual(client.post("/api/gem_stats/reset", json={}).json, {"ok": True})
            self.assertEqual(self.gs.get_stats()["stats_start_ts"], 0)


class FreebieStatisticsIntegrationTests(unittest.TestCase):
    def test_worker_start_and_toggle_drive_statistics_without_dashboard_requests(self):
        fixture = consumers.ConsumerSlotTests()
        fixture.setUp()
        feature = fixture.freebies
        stub = types.ModuleType("features.gem_statistics")
        stub.get_gem_statistics = Mock()
        feature.state.freebies_enabled = False
        with patch.dict(sys.modules, {"features.gem_statistics": stub}), \
             patch.object(feature.threading.Thread, "start"):
            feature.start()
            stub.get_gem_statistics.return_value.set_active.assert_called_with(False)
            self.assertTrue(feature.toggle())
            stub.get_gem_statistics.return_value.set_active.assert_called_with(True)
            self.assertTrue(feature._wake_evt.is_set())
            self.assertFalse(feature.toggle())
            stub.get_gem_statistics.return_value.set_active.assert_called_with(False)

    def test_enabled_start_and_statistics_io_failure_do_not_prevent_worker_or_toggle(self):
        fixture = consumers.ConsumerSlotTests()
        fixture.setUp()
        feature = fixture.freebies
        feature.state.freebies_enabled = True
        stub = types.ModuleType("features.gem_statistics")
        stub.get_gem_statistics = Mock()
        stub.get_gem_statistics.return_value.set_active.side_effect = OSError("disk full")
        with patch.dict(sys.modules, {"features.gem_statistics": stub}), \
             patch.object(feature.threading.Thread, "start") as start:
            feature.start()
            start.assert_called_once()
            stub.get_gem_statistics.return_value.set_active.assert_called_with(True)
            self.assertFalse(feature.toggle())
            self.assertFalse(feature.state.freebies_enabled)
            self.assertTrue(any("statistics state update failed" in call.args[0]
                                for call in feature.bot_log.call_args_list))


if __name__ == "__main__":
    unittest.main()
