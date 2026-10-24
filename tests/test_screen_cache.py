"""Capture/cache regression tests using real PNGs, fake ADB and temporary files.

No emulator connection, bot startup or game input is performed.
"""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

import config
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def png(value=80):
    image = np.full((8, 12, 3), value, dtype=np.uint8)
    image[0, 0] = (10, 40, 200)
    ok, data = cv2.imencode(".png", image)
    assert ok
    return data.tobytes()


class CaptureTests(unittest.TestCase):
    def setUp(self):
        # Use the workspace: Windows sandbox temp permits writes but can deny
        # atomic rename, which is the operation these tests must exercise.
        (ROOT / "temp").mkdir(exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(prefix="screenshot-tests-", dir=ROOT / "temp")
        self.addCleanup(self.folder.cleanup)
        self.settings = types.ModuleType("config.settings")
        self.settings.BASE_DIR = Path(self.folder.name)
        self.settings.REMOTE_SCREEN = "/sdcard/__scr.png"
        self.settings.LOCAL_SCREEN = str(Path(self.folder.name) / "legacy.png")
        self.settings.SCREENSHOT_CAPTURE_ATTEMPTS = 2
        self.settings.SCREENSHOT_RETRY_DELAY_S = 0
        self.settings.SCREENSHOT_LOG_LEVEL = "TXT"
        self.settings.SCREENSHOT_LOG_CACHE_HITS = False
        self.device = "emulator-A"
        self.remote = {}
        self.guard = threading.Lock()
        self.pull_hook = None
        self.capture_hook = None
        self.cleanup_hook = None
        self.payload = png()
        self.log = Mock()
        adb_stub = types.ModuleType("core.adb_helper")
        adb_stub.adb = Mock(side_effect=self.fake_adb)
        adb_stub.get_active_device = lambda: self.device
        logger_stub = types.ModuleType("core.file_logger")
        logger_stub.bot_log = self.log
        with patch.dict(sys.modules, {"config.settings": self.settings,
                                      "core.adb_helper": adb_stub,
                                      "core.file_logger": logger_stub}), \
             patch.object(config, "settings", self.settings, create=True):
            self.cache = load("screen_cache_under_test", "core/screen_cache.py")
        self.adb = adb_stub.adb

    def fake_adb(self, *args, device=None, log_fn=None):
        if args[:3] == ("shell", "screencap", "-p"):
            with self.guard:
                self.remote[(device, args[3])] = self.payload
            if self.capture_hook:
                self.capture_hook(args, device)
        elif args[0] == "pull":
            with self.guard:
                data = self.remote[(device, args[1])]
            if self.pull_hook:
                return self.pull_hook(args, device, data)
            Path(args[2]).write_bytes(data)
        elif args[:3] == ("shell", "rm", "-f"):
            if self.cleanup_hook:
                self.cleanup_hook(args, device)
            with self.guard:
                self.remote.pop((device, args[3]), None)
        else:
            raise AssertionError((args, device))
        return ""

    def write_cache(self, slot, data=None, age=0):
        path = Path(self.cache.screen_path(slot))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.payload if data is None else data)
        timestamp = time.time() - age
        os.utime(path, (timestamp, timestamp))
        return path

    def messages(self):
        return "\n".join(call.args[0] for call in self.log.call_args_list)

    def test_fresh_capture_is_full_color_png_with_gray_and_color_returns(self):
        gray, w, h = self.cache.get_screen("game_scr", force=True)
        self.assertEqual((w, h, gray.ndim), (12, 8, 2))
        color, _, _ = self.cache.get_screen("game_scr", color=True)
        self.assertEqual(color[0, 0].tolist(), [10, 40, 200])
        self.assertEqual(Path(self.cache.screen_path("game_scr")).read_bytes(), self.payload)
        calls = self.adb.call_args_list
        self.assertEqual(len(calls), 3)  # second call was cache-only
        remote = calls[0].args[3]
        self.assertIn("__obelisk_game_scr_", remote)
        self.assertEqual(calls[1].args[1], remote)
        self.assertEqual(calls[2].args[3], remote)
        self.assertNotEqual(calls[1].args[2], self.cache.screen_path("game_scr"))
        self.assertTrue(all(call.kwargs["device"] == "emulator-A" for call in calls))
        self.assertTrue(all(callable(call.kwargs["log_fn"]) for call in calls))
        self.assertFalse(self.remote)
        self.assertFalse(list(Path(self.folder.name).rglob("*.part")))
        for field in ("request=", "capture=", "device=emulator-A", "attempt=1/2", "thread=",
                      "phase=complete", "size=12x8", "bytes=", "elapsed="):
            self.assertIn(field, self.messages())

    def test_retry_after_partial_pull_uses_new_capture_and_cleans_staging(self):
        pulls = []

        def pull(args, device, data):
            pulls.append(args)
            Path(args[2]).write_bytes(data[:20] if len(pulls) == 1 else data)
            if len(pulls) == 1:
                raise RuntimeError("simulated interrupted transfer")

        self.pull_hook = pull
        self.assertIsNotNone(self.cache.get_screen("lootbug_scr", force=True)[0])
        self.assertEqual(len(pulls), 2)
        self.assertNotEqual(pulls[0][1], pulls[1][1])
        self.assertIn("phase=pull failed", self.messages())
        self.assertIn("recovered=True", self.messages())
        self.assertFalse(self.remote)
        self.assertFalse(list(Path(self.folder.name).rglob("*.part")))

    def test_empty_truncated_and_invalid_pngs_never_replace_old_cache(self):
        for bad in (b"", b"not a PNG", self.payload[:-8],
                    b"\x89PNG\r\n\x1a\ninvalid\x00\x00\x00\x00IEND\xaeB`\x82"):
            with self.subTest(data=bad[:16]):
                path = self.write_cache("freebie_scr")
                old_mtime = path.stat().st_mtime_ns
                old = path.read_bytes()
                self.payload = bad
                self.assertEqual(self.cache.get_screen("freebie_scr", force=True), (None, 0, 0))
                self.assertEqual(path.read_bytes(), old)
                self.assertEqual(path.stat().st_mtime_ns, old_mtime)
                self.payload = png()
        self.assertIn("phase=decode failed", self.messages())
        self.assertIn("exhausted attempts=2", self.messages())
        self.assertFalse(self.remote)
        self.assertFalse(list(Path(self.folder.name).rglob("*.part")))

    def test_stale_cache_is_not_fallback_on_failure_and_cache_read_never_captures(self):
        path = self.write_cache("game_scr", age=60)
        self.assertEqual(self.cache.get_cached_screen("game_scr", max_age=15), (None, 0, 0))
        self.assertEqual(self.cache.get_cached_screen("missing"), (None, 0, 0))
        self.adb.assert_not_called()
        self.capture_hook = lambda *args: (_ for _ in ()).throw(RuntimeError("offline"))
        self.assertEqual(self.cache.get_screen("game_scr", max_age=15), (None, 0, 0))
        self.assertTrue(path.is_file())
        self.assertEqual(len([c for c in self.adb.call_args_list if c.args[1:2] == ("screencap",)]), 2)

    def test_corrupt_newest_slot_is_skipped_for_next_valid_fresh_slot(self):
        self.write_cache("valid", age=2)
        self.write_cache("stale", age=90)
        self.write_cache("broken", b"broken", age=1)
        result = self.cache.get_latest_cached_screen(["broken", "valid", "stale", "missing"], 15)
        self.assertEqual(result[3], "valid")
        self.assertEqual(result[1:3], (12, 8))
        self.adb.assert_not_called()
        self.assertIn("slot=broken phase=cache_read failed", self.messages())

    def test_small_future_mtime_remains_readable_by_cache_and_viewer(self):
        path = self.write_cache("game_scr")
        now = 1700000000.0
        for lead in (0.000001, 0.005, 0.04):
            with self.subTest(lead=lead):
                os.utime(path, (now + lead, now + lead))
                with patch.object(self.cache, "time", types.SimpleNamespace(time=lambda: now)):
                    result = self.cache.get_latest_cached_screen(["game_scr"], max_age=5)
                    self.assertIsNotNone(result[0])
                    self.assertEqual(result[3:], ("game_scr", 0.0))
                    self.assertEqual(self.cache.latest_cached_png(["game_scr.png"]),
                                     (self.payload, "game_scr.png"))
        self.adb.assert_not_called()

    def test_timestamp_tolerance_does_not_accept_far_future_or_expired_frames(self):
        path = self.write_cache("game_scr")
        now = 1700000000.0
        for offset, max_age in ((0.25, 5), (-5, 5), (-5.01, 5), (0.005, 0)):
            with self.subTest(offset=offset, max_age=max_age):
                os.utime(path, (now + offset, now + offset))
                with patch.object(self.cache, "time", types.SimpleNamespace(time=lambda: now)):
                    self.assertEqual(self.cache.get_cached_screen("game_scr", max_age),
                                     (None, 0, 0))
        self.adb.assert_not_called()

    def test_cleanup_failure_does_not_repeat_or_invalidate_success(self):
        self.cleanup_hook = lambda *args: (_ for _ in ()).throw(RuntimeError("cleanup unavailable"))
        self.assertIsNotNone(self.cache.get_screen("founders_scr", force=True)[0])
        self.assertEqual(len(self.adb.call_args_list), 3)
        self.assertIn("phase=remote_cleanup", self.messages())

    def test_publish_failure_preserves_previous_image_and_removes_staging(self):
        path = self.write_cache("game_scr")
        old = path.read_bytes()
        with patch.object(self.cache.os, "replace", side_effect=PermissionError("file in use")):
            self.assertEqual(self.cache.get_screen("game_scr", force=True), (None, 0, 0))
        self.assertEqual(path.read_bytes(), old)
        self.assertIn("phase=publish failed", self.messages())
        self.assertFalse(self.remote)
        self.assertFalse(list(path.parent.glob("*.part")))

    def test_device_change_restarts_whole_capture_and_cleans_original_device(self):
        def change_once(args, device, data):
            Path(args[2]).write_bytes(data)
            self.device = "emulator-B"

        self.pull_hook = change_once
        self.assertIsNotNone(self.cache.get_screen("level_scr", force=True)[0])
        devices = [call.kwargs["device"] for call in self.adb.call_args_list]
        self.assertEqual(devices, ["emulator-A"] * 3 + ["emulator-B"] * 3)
        self.assertIn("phase=device_check failed", self.messages())
        self.assertIn("recovered=True", self.messages())
        self.assertFalse(self.remote)

    def test_different_slots_can_capture_concurrently_with_distinct_remote_paths(self):
        barrier = threading.Barrier(2)
        self.capture_hook = lambda *args: barrier.wait(timeout=3)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda slot: self.cache.get_screen(slot, force=True),
                                    ["game_scr", "freebie_scr"]))
        self.assertTrue(all(result[0] is not None for result in results))
        remotes = [call.args[3] for call in self.adb.call_args_list
                   if call.args[:3] == ("shell", "screencap", "-p")]
        self.assertEqual(len(set(remotes)), 2)
        self.assertFalse(self.remote)

    def test_same_slot_captures_are_serial_and_readers_see_complete_new_frame(self):
        entered = threading.Event()
        release = threading.Event()
        reading = threading.Event()
        self.write_cache("game_scr")
        self.payload = png(120)

        def pause_pull(args, device, data):
            Path(args[2]).write_bytes(data[:20])
            entered.set()
            self.assertTrue(release.wait(3))
            Path(args[2]).write_bytes(data)

        self.pull_hook = pause_pull

        def read():
            reading.set()
            return self.cache.latest_cached_png(["game_scr.png"])

        with ThreadPoolExecutor(max_workers=3) as pool:
            first = pool.submit(self.cache.get_screen, "game_scr", 0, True)
            self.assertTrue(entered.wait(3))
            second = pool.submit(self.cache.get_screen, "game_scr", 0, True)
            reader = pool.submit(read)
            self.assertTrue(reading.wait(3))
            self.assertEqual(len([c for c in self.adb.call_args_list
                                  if c.args[:3] == ("shell", "screencap", "-p")]), 1)
            release.set()
            self.assertIsNotNone(first.result(timeout=3)[0])
            self.assertIsNotNone(second.result(timeout=3)[0])
            self.assertEqual(reader.result(timeout=3), (self.payload, "game_scr.png"))
        self.assertFalse(self.remote)

    def test_viewer_returns_snapshot_skips_corruption_and_rejects_paths(self):
        self.write_cache("good", age=5)
        self.write_cache("bad", b"invalid")
        data, name = self.cache.latest_cached_png(["../good.png", "bad.png", "good.png",
                                                  "good.png.tmp", "C:\\outside.png"])
        self.assertEqual((data, name), (self.payload, "good.png"))
        self.write_cache("good", png(100))
        self.assertEqual(data, self.payload)  # independent immutable response
        self.adb.assert_not_called()

    def test_invalid_slots_fail_before_any_adb_or_directory_creation(self):
        for slot in ("../game", "a/b", "a\\b", "", "bad name", "x;rm", "CON", None):
            with self.subTest(slot=slot), self.assertRaises(ValueError):
                self.cache.get_screen(slot, force=True)
        self.adb.assert_not_called()
        self.assertFalse(Path(self.cache.TEMP_DIR).exists())

    def test_verbose_cache_logging_is_opt_in(self):
        self.write_cache("game_scr")
        self.cache.get_cached_screen("game_scr")
        self.log.assert_not_called()
        self.settings.SCREENSHOT_LOG_CACHE_HITS = True
        self.cache.get_cached_screen("game_scr")
        self.assertIn("slot=game_scr cache_hit age=", self.messages())

    def test_legacy_helper_uses_same_atomic_pipeline(self):
        with patch.dict(sys.modules, {"core.screen_cache": self.cache,
                                      "config.settings": self.settings}), \
             patch.object(config, "settings", self.settings, create=True):
            legacy = load("legacy_screenshot_under_test", "core/screenshot.py")
        self.assertIs(legacy.s, self.settings)
        self.assertIsNotNone(legacy.screenshot_gray()[0])
        self.assertTrue(Path(self.settings.LOCAL_SCREEN).is_file())
        self.assertIn("__obelisk_manual_scr_", self.adb.call_args_list[0].args[3])

    def test_decode_failure_without_existing_cache_returns_none(self):
        self.payload = b""
        self.assertEqual(self.cache.get_screen("new_slot", force=True), (None, 0, 0))
        self.assertFalse(Path(self.cache.screen_path("new_slot")).exists())
        self.assertFalse(self.remote)

    def test_capture_failure_is_logged_with_phase_and_remote_is_cleaned(self):
        self.capture_hook = lambda *args: (_ for _ in ()).throw(RuntimeError("screencap failed"))
        self.assertEqual(self.cache.get_screen("game_scr", force=True), (None, 0, 0))
        self.assertIn("phase=capture failed: RuntimeError: screencap failed", self.messages())
        self.assertFalse(self.remote)

    def test_waiting_nonforced_same_slot_request_reuses_completed_capture(self):
        entered = threading.Event()
        release = threading.Event()

        def pause(args, device, data):
            entered.set()
            self.assertTrue(release.wait(3))
            Path(args[2]).write_bytes(data)

        self.pull_hook = pause
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.cache.get_screen, "game_scr")
            self.assertTrue(entered.wait(3))
            second = pool.submit(self.cache.get_screen, "game_scr")
            release.set()
            self.assertIsNotNone(first.result(timeout=3)[0])
            self.assertIsNotNone(second.result(timeout=3)[0])
        self.assertEqual(len(self.adb.call_args_list), 3)


class PinnedAdbTests(unittest.TestCase):
    def setUp(self):
        self.adb = load("adb_helper_under_test", "core/adb_helper.py")
        self.adb._active_device = "A"
        self.adb.ADB_MAX_RETRIES = 2

    def test_pinned_device_is_used_even_for_cleanup_after_active_device_change(self):
        self.adb._active_device = "B"
        with patch.object(self.adb.subprocess, "run", return_value=types.SimpleNamespace(
                returncode=0, stdout="ok", stderr="")) as run:
            self.assertEqual(self.adb.adb("shell", "rm", "-f", "/sdcard/owned.png", device="A"), "ok")
        self.assertEqual(run.call_args.args[0][1:3], ["-s", "A"])

    def test_reconnect_switch_never_retries_pull_on_another_emulator(self):
        def reconnect(error):
            self.adb._active_device = "B"
            return True

        with patch.object(self.adb.subprocess, "run", return_value=types.SimpleNamespace(
                returncode=1, stdout="", stderr="device offline")) as run, \
             patch.object(self.adb, "_reconnect_if_needed", side_effect=reconnect):
            with self.assertRaisesRegex(RuntimeError, "device changed"):
                self.adb.adb("pull", "/sdcard/owned.png", "local.png", device="A")
        self.assertEqual(run.call_count, 1)

    def test_reconnect_same_device_retries_and_unpinned_calls_keep_existing_behavior(self):
        failed = types.SimpleNamespace(returncode=1, stdout="", stderr="offline")
        good = types.SimpleNamespace(returncode=0, stdout="ok", stderr="")
        with patch.object(self.adb.subprocess, "run", side_effect=[failed, good]) as run, \
             patch.object(self.adb, "_reconnect_if_needed", return_value=True):
            self.assertEqual(self.adb.adb("pull", "remote", "local", device="A"), "ok")
        self.assertEqual([c.args[0][2] for c in run.call_args_list], ["A", "A"])

        def reconnect(error):
            self.adb._active_device = "B"
            return True

        with patch.object(self.adb.subprocess, "run", side_effect=[failed, good]) as run, \
             patch.object(self.adb, "_reconnect_if_needed", side_effect=reconnect):
            self.assertEqual(self.adb.adb("shell", "input", "tap", "1", "2"), "ok")
        self.assertEqual([c.args[0][2] for c in run.call_args_list], ["A", "B"])

    def test_timeout_reconnect_switch_is_pinned_too(self):
        def reconnect(error):
            self.adb._active_device = "B"
            return True

        with patch.object(self.adb.subprocess, "run", side_effect=subprocess.TimeoutExpired("adb", 30)) as run, \
             patch.object(self.adb, "_reconnect_if_needed", side_effect=reconnect):
            with self.assertRaisesRegex(RuntimeError, "device changed"):
                self.adb.adb("shell", "screencap", "-p", "remote", device="A")
        self.assertEqual(run.call_count, 1)

    def test_reconnect_diagnostics_report_error_and_device(self):
        failed = types.SimpleNamespace(returncode=1, stdout="", stderr="device offline")
        good = types.SimpleNamespace(returncode=0, stdout="ok", stderr="")
        log = Mock()
        with patch.object(self.adb.subprocess, "run", side_effect=[failed, good]), \
             patch.object(self.adb, "_reconnect_if_needed", return_value=True):
            self.adb.adb("pull", "remote", "local", device="A", log_fn=log)
        messages = "\n".join(call.args[0] for call in log.call_args_list)
        self.assertIn("adb_attempt=1/2", messages)
        self.assertIn("device offline", messages)
        self.assertIn("adb_reconnect=True active_device=A pinned_device=A", messages)


if __name__ == "__main__":
    unittest.main()
