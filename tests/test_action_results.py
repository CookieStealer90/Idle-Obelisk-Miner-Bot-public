"""ADB failure propagation and claim accounting using isolated feature imports."""
import sys
import types
import unittest
from unittest.mock import Mock, patch

import test_founders as founders
import test_lootbug as lootbugs
import test_screenshot_consumers as consumers


class FoundersFailureTests(unittest.TestCase):
    def setUp(self):
        founders.FeatureTests.setUp(self)

    def test_failed_tap_does_not_count_or_timestamp_and_releases_lock(self):
        self.feature.find_template.return_value = {"found": True, "score": 1, "cx": 21, "cy": 22}
        self.feature.tap.return_value = False
        self.feature._try_run_with_lock()
        self.assertEqual(self.state.founders_clicked_count, 0)
        self.assertEqual(self.state.founders_last_click_ts, 0)
        self.assertFalse(self.state.ingame_action_lock.locked())
        self.feature.tap.assert_called_once()


class LootbugFailureTests(unittest.TestCase):
    def setUp(self):
        lootbugs.LootbugTests.setUp(self)

    def test_failed_initial_tap_never_starts_buy_wait_or_counts(self):
        self.state.lootbug_clicked_count = 0
        self.state.lootbug_last_click_ts = 0
        self.feature.find_template.return_value = dict(self.hit)
        self.feature.tap.return_value = False
        with patch.object(self.feature, "_buy_when_visible") as buy:
            self.assertFalse(self.feature._run_scan_cycle())
        buy.assert_not_called()
        self.assertEqual(self.state.lootbug_clicked_count, 0)
        self.assertEqual(self.state.lootbug_last_click_ts, 0)
        self.assertEqual(self.state.lootbug_bonus_count, 0)
        self.feature._sleep_interruptible.assert_not_called()


class FreebieResultTests(unittest.TestCase):
    def setUp(self):
        consumers.ConsumerSlotTests.setUp(self)
        self.feature = self.freebies
        self.state = self.feature.state
        self.state.freebies_claimed_count = 0
        self.state.freebies_diamonds_total = 0
        self.state.freebies_last_claim_ts = 0
        self.feature.s.FREEBIES_DIAMONDS_PER_CLAIM = 28
        self.feature.get_screen.return_value = (object(), 900, 1600)
        self.hit = {"found": True, "score": 1, "cx": 20, "cy": 30}
        self.feature.find_template.return_value = self.hit
        self.feature.tap.return_value = True
        self.feature.time = types.SimpleNamespace(sleep=Mock(), time=lambda: 100)
        self.stats = types.ModuleType("features.gem_statistics")
        self.stats.get_gem_statistics = Mock()
        self.patcher = patch.dict(sys.modules, {"features.gem_statistics": self.stats})
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_failed_menu_or_claim_tap_does_not_record_reward(self):
        for results in ([False], [True, False]):
            with self.subTest(results=results):
                self.feature.tap.reset_mock()
                self.feature.tap.side_effect = results
                self.assertFalse(self.feature._run_claim_cycle())
                self.assertEqual(self.state.freebies_claimed_count, 0)
                self.assertEqual(self.state.freebies_diamonds_total, 0)
                self.assertEqual(self.state.freebies_last_claim_ts, 0)
                self.stats.get_gem_statistics.assert_not_called()

    def test_success_records_estimate_once_and_close_failure_does_not_undo_sent_claim(self):
        self.feature.tap.side_effect = [True, True, False]
        self.assertFalse(self.feature._run_claim_cycle())
        self.assertEqual(self.state.freebies_claimed_count, 1)
        self.assertEqual(self.state.freebies_diamonds_total, 28)
        self.stats.get_gem_statistics.return_value.record_claim.assert_called_once_with("gem", amount=28)
        self.assertTrue(any("reward unverified" in call.args[0] for call in self.feature.bot_log.call_args_list))

    def test_failed_scroll_aborts_without_recording_claim(self):
        self.feature.find_template.side_effect = [self.hit, {"found": False, "score": 0}]
        self.feature.scroll_down.return_value = False
        self.assertFalse(self.feature._run_claim_cycle())
        self.assertEqual(self.feature.tap.call_count, 1)
        self.assertEqual(self.state.freebies_claimed_count, 0)
        self.stats.get_gem_statistics.assert_not_called()


if __name__ == "__main__":
    unittest.main()
