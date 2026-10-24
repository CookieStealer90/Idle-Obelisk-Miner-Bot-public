"""Notices regression coverage with local images and mocked game access only."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np
from flask import Flask

from config.notice_defaults import NOTICE_DEFAULTS
from config.user_overrides import apply_overrides_to_settings, normalize_user_settings
from core.notice_archive import NoticeArchive
from core.notice_detection import detect_notice

ROOT = Path(__file__).resolve().parent.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(variant):
    image = np.full((1600, 900, 3), 180, np.uint8)
    frame = cv2.imread(str(ROOT / "images" / "Notices" / (variant + "_frame.png")))
    y = 772 if variant == "level" else 750
    image[y:y + frame.shape[0], :frame.shape[1]] = frame
    return image


class DetectionTests(unittest.TestCase):
    def detect(self, image, roi=(0, 740, 390, 925)):
        return detect_notice(image, roi, ROOT / "images", "Notices/*_frame.png", .96)

    def test_both_variants_and_variable_text(self):
        for variant in ("level", "shard"):
            image = fixture(variant)
            match = self.detect(image)
            self.assertTrue(match["found"])
            self.assertEqual(match["variant"], variant)
            # Arbitrary text, including all-white text, is outside the mask.
            image[790:885, 22:275] = 255
            self.assertTrue(self.detect(image)["found"])

    def test_dark_background_blank_screen_and_wrong_borders_do_not_match(self):
        for color in (0, 15, 80, 255):
            self.assertFalse(self.detect(np.full((1600, 900, 3), color, np.uint8))["found"])
        image = fixture("level")
        image[772, 4:290] = 0
        self.assertFalse(self.detect(image)["found"])

    def test_search_translation_and_invalid_roi(self):
        image = fixture("level")
        image[750:920] = np.roll(image[750:920], 4, axis=1)
        self.assertEqual(self.detect(image)["roi"], (4, 772, 376, 895))
        for roi in ((0, 0, 5, 5), (0, 0, 901, 1600)):
            with self.assertRaises(ValueError):
                self.detect(image, roi)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.archive = NoticeArchive(Path(self.tmp.name))
        self.crop = np.full((123, 372, 3), 30, np.uint8)

    def test_persistence_acknowledgement_and_pending_identity(self):
        identifier, attempted = self.archive.prepare(self.crop, "level", 1)
        self.assertFalse(attempted)
        self.archive.mark_attempted(identifier)
        restarted = NoticeArchive(self.tmp.name)
        self.assertEqual(restarted.prepare(self.crop, "level", 1), (identifier, True))
        self.assertEqual(restarted.entries()[0]["id"], identifier)
        self.assertTrue(restarted.read(identifier).startswith(b'\x89PNG'))
        restarted.delete(identifier)
        restarted.delete(identifier)
        self.assertEqual(restarted.entries(), [])
        self.assertEqual(restarted.prepare(self.crop, "level", 1), (identifier, True))
        restarted.clear_pending()
        self.assertNotEqual(restarted.prepare(self.crop, "level", 1)[0], identifier)

    def test_full_disk_or_metadata_error_never_leaves_partial_entry(self):
        with self.assertRaises(OSError):
            self.archive.prepare(self.crop, "level", 0)
        with patch("core.notice_archive.atomic_write_json", side_effect=OSError("full disk")):
            with self.assertRaises(OSError):
                self.archive.prepare(self.crop, "level", 1)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_path_validation_and_corrupt_file_isolation(self):
        self.archive.prepare(self.crop, "level", 1)
        (Path(self.tmp.name) / ("a" * 32 + ".png")).write_bytes(b"damaged")
        self.assertEqual(len(self.archive.entries()), 1)
        self.assertEqual(self.archive.unreadable_count, 1)
        for identifier in ("../pending", "pending.json", "", "0" * 31):
            with self.assertRaises(ValueError):
                self.archive.delete(identifier)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = types.ModuleType("config.settings")
        self.settings.__dict__.update(NOTICE_DEFAULTS)
        self.settings.TEMP_DIR = Path(self.tmp.name)
        self.settings.BASE_DIR = ROOT
        self.settings.NOTICES_POST_CLICK_DELAY_S = 0
        self.state = types.SimpleNamespace(notices_enabled=True, notices_clicked_count=0,
            notices_status="", notices_error="", notices_last_score=0,
            notices_next_check_ts=0, ingame_action_lock=threading.Lock())
        self.state.notices_last_scan_ts = 0.0
        stubs = {"config.settings": self.settings}
        for name, attrs in {
            "core.screen_cache": {"get_cached_screen": Mock(), "get_screen": Mock()},
            "core.tapper": {"tap": Mock(return_value=True)},
            "core.game_state": {"is_game_running": Mock(return_value=True)},
            "core.file_logger": {"bot_log": Mock()},
        }.items():
            stubs[name] = types.ModuleType(name)
            stubs[name].__dict__.update(attrs)
        with patch.dict(sys.modules, stubs):
            self.feature = load("notices_under_test", "features/notices.py")
        self.feature.s = self.settings
        self.feature.state = self.state
        self.feature.archive = NoticeArchive(Path(self.tmp.name) / "notices")
        self.feature.get_cached_screen.return_value = (fixture("level"), 900, 1600)
        self.feature.get_screen.return_value = (np.zeros((1600, 900, 3), np.uint8), 900, 1600)

    def test_cached_initial_frame_save_before_tap_and_fresh_chain(self):
        self.feature.get_screen.side_effect = [(fixture("shard"), 900, 1600),
                                               (np.zeros((1600, 900, 3), np.uint8), 900, 1600)]
        def tap(*args, **kwargs):
            self.assertEqual(len(self.feature.archive.entries()), self.state.notices_clicked_count + 1)
            self.assertTrue(self.state.ingame_action_lock.locked())
            return True
        self.feature.tap.side_effect = tap
        self.assertEqual(self.feature._cycle(), "ok")
        self.assertEqual(self.feature.tap.call_count, 2)
        self.assertEqual(self.state.notices_clicked_count, 2)
        self.assertGreater(self.state.notices_last_scan_ts, 0)
        self.feature.get_cached_screen.assert_called_once_with("game_scr", max_age=5, color=True)
        self.assertEqual(self.feature.get_screen.call_count, 2)
        for call in self.feature.get_screen.call_args_list:
            self.assertEqual(call.args, ("notices_scr",))
            self.assertEqual(call.kwargs, {"max_age": 0, "force": True, "color": True})
        self.assertFalse(self.state.ingame_action_lock.locked())

    def test_missing_cache_and_no_notice(self):
        self.feature.get_cached_screen.return_value = (None, 0, 0)
        self.assertEqual(self.feature._cycle(), "ok")
        self.feature.get_screen.assert_called_once()
        self.feature.tap.assert_not_called()
        self.assertGreater(self.state.notices_last_scan_ts, 0)

    def test_failed_capture_does_not_advance_last_scan(self):
        self.feature.get_cached_screen.return_value = (None, 0, 0)
        self.feature.get_screen.return_value = (None, 0, 0)
        with self.assertRaises(OSError):
            self.feature._cycle()
        self.assertEqual(self.state.notices_last_scan_ts, 0)

    def test_interval_variance_retries_and_independent_toggle(self):
        with patch.object(self.feature.random, "uniform", return_value=1.15) as draw:
            self.assertAlmostEqual(self.feature._next_delay("ok"), 3105)
            draw.assert_called_once_with(.85, 1.15)
            self.assertEqual(self.feature._next_delay("retry"), 10)
            self.assertEqual(draw.call_count, 1)
        generation = self.feature._generation
        self.assertFalse(self.feature.toggle())
        self.assertGreater(self.feature._generation, generation)
        self.assertTrue(self.feature._wake.is_set())
        self.assertTrue(self.feature.toggle())

    def test_busy_and_disabled_do_not_capture(self):
        self.state.ingame_action_lock.acquire()
        self.assertEqual(self.feature._cycle(), "retry")
        self.state.ingame_action_lock.release()
        self.state.notices_enabled = False
        self.assertEqual(self.feature._cycle(), "off")
        self.feature.get_cached_screen.assert_not_called()
        self.feature.tap.assert_not_called()
        self.assertEqual(self.state.notices_last_scan_ts, 0)

    def test_unchanged_image_is_not_archived_or_clicked_twice(self):
        self.feature.get_screen.return_value = (fixture("level"), 900, 1600)
        self.assertEqual(self.feature._cycle(), "retry")
        self.assertEqual(self.feature._cycle(), "retry")
        self.feature.tap.assert_called_once()
        self.assertEqual(len(self.feature.archive.entries()), 1)

    def test_moving_surroundings_do_not_change_notice_identity(self):
        changed = fixture("level")
        changed[773:782, 310:370] = 255
        self.feature.get_screen.return_value = (changed, 900, 1600)
        self.assertEqual(self.feature._cycle(), "retry")
        self.feature.tap.assert_called_once()
        self.assertEqual(len(self.feature.archive.entries()), 1)

    def test_absent_game_and_disable_during_detection_never_tap(self):
        self.feature.is_game_running.return_value = False
        self.assertEqual(self.feature._cycle(), "retry")
        self.feature.get_cached_screen.assert_not_called()
        self.feature.is_game_running.return_value = True
        original = self.feature.inspect
        def disable(image):
            match = original(image)
            self.feature.toggle()
            return match
        self.feature.inspect = disable
        self.assertEqual(self.feature._cycle(), "off")
        self.feature.tap.assert_not_called()
        self.assertEqual(self.feature.archive.entries(), [])

    def test_capture_storage_and_tap_failures_release_lock(self):
        self.feature.get_screen.return_value = (None, 0, 0)
        with self.assertRaises(OSError):
            self.feature._cycle()
        self.assertEqual(self.state.notices_clicked_count, 1)
        self.assertFalse(self.state.ingame_action_lock.locked())
        self.feature.archive.clear_pending()
        self.feature.tap.return_value = False
        with self.assertRaises(OSError):
            self.feature._cycle()
        self.assertEqual(self.state.notices_clicked_count, 1)
        self.assertFalse(self.state.ingame_action_lock.locked())
        self.feature.archive.clear_pending()
        with patch.object(self.feature.archive, "prepare", side_effect=OSError("disk")):
            calls = self.feature.tap.call_count
            with self.assertRaises(OSError):
                self.feature._cycle()
            self.assertEqual(calls, self.feature.tap.call_count)

    def test_chain_limit_and_disable_after_tap(self):
        self.settings.NOTICES_MAX_PER_CYCLE = 1
        self.feature.get_screen.return_value = (fixture("shard"), 900, 1600)
        self.assertEqual(self.feature._cycle(), "retry")
        self.feature.tap.assert_called_once()
        self.feature.archive.clear_pending()
        def disable(*args, **kwargs):
            self.state.notices_enabled = False
            return True
        self.feature.tap.side_effect = disable
        self.assertEqual(self.feature._cycle(), "off")
        self.assertFalse(self.state.ingame_action_lock.locked())


class SettingsAndApiTests(unittest.TestCase):
    def test_manual_detection_cache_hit_miss_and_capture_failure(self):
        module = load("notices_test_api_under_test", "web/notices_api.py")
        app = Flask(__name__)
        app.register_blueprint(module.notices_bp)
        cache = types.ModuleType("core.screen_cache")
        cache.get_cached_screen = Mock(return_value=(fixture("level"), 900, 1600))
        cache.get_screen = Mock(return_value=(fixture("shard"), 900, 1600))
        with patch.dict(sys.modules, {"core.screen_cache": cache}), patch.object(module.archive, "prepare") as save:
            client = app.test_client()
            response = client.post('/api/notices/test', json={})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["variant"], "level")
            cache.get_screen.assert_not_called()
            # Missing and stale caches have the same cache-helper contract.
            cache.get_cached_screen.return_value = (None, 0, 0)
            response = client.post('/api/notices/test', json={})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["variant"], "shard")
            cache.get_screen.assert_called_once_with("notices_test_scr", max_age=0, force=True, color=True)
            cache.get_screen.return_value = (None, 0, 0)
            response = client.post('/api/notices/test', json={})
            self.assertEqual(response.status_code, 503)
            self.assertIn("capture failed", response.json["error"])
            save.assert_not_called()

    def test_settings_api_exposes_every_operational_default(self):
        module = load("notices_config_under_test", "web/config_api.py")
        with tempfile.TemporaryDirectory() as directory:
            module.BASE_DIR = Path(directory)
            app = Flask(__name__)
            app.register_blueprint(module.config_bp)
            data = app.test_client().get('/api/config/settings').json
            self.assertEqual(set(data["notices"]), set(NOTICE_DEFAULTS))
            self.assertIn("NOTICES_ENABLED", data["startup_defaults"])

    def test_all_defaults_validate_and_roundtrip(self):
        payload = {"notices": dict(NOTICE_DEFAULTS), "startup_defaults": {"NOTICES_ENABLED": True}}
        self.assertEqual(normalize_user_settings(payload), payload)
        values = {}
        apply_overrides_to_settings(values, payload)
        self.assertTrue(values["NOTICES_ENABLED"])
        for key, value in NOTICE_DEFAULTS.items():
            self.assertEqual(values[key], value)
        for key, value in (("NOTICES_MAX_PER_CYCLE", 0), ("NOTICES_MATCH_THRESHOLD", 1.1),
                           ("NOTICES_INTERVAL_VARIANCE_PCT", -1), ("NOTICES_TEMPLATE_GLOB", "../*.png")):
            with self.assertRaises(ValueError):
                normalize_user_settings({"notices": {key: value}})

    def test_list_image_delete_and_missing_files(self):
        module = load("notices_api_under_test", "web/notices_api.py")
        with tempfile.TemporaryDirectory() as directory:
            module.archive = NoticeArchive(directory)
            identifier, _ = module.archive.prepare(np.zeros((10, 20, 3), np.uint8), "test", 1)
            app = Flask(__name__)
            app.register_blueprint(module.notices_bp)
            client = app.test_client()
            self.assertEqual(client.get('/api/notices').json["entries"][0]["id"], identifier)
            self.assertEqual(client.get(f'/api/notices/{identifier}/image').mimetype, 'image/png')
            self.assertTrue(client.delete(f'/api/notices/{identifier}').json["ok"])
            self.assertTrue(client.delete(f'/api/notices/{identifier}').json["ok"])
            self.assertEqual(client.get(f'/api/notices/{identifier}/image').status_code, 404)
            self.assertEqual(client.delete('/api/notices/invalid').status_code, 400)


if __name__ == "__main__":
    unittest.main()
