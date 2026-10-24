"""Key persistence checks without importing the app or starting the bot."""
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from web.secret_key import load_or_create_secret_key

ROOT = Path(__file__).resolve().parent.parent


class SecretKeyTests(unittest.TestCase):
    def test_first_start_creates_key_and_restart_reuses_it(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "config" / "web_secret.json"
            key = load_or_create_secret_key(path)
            self.assertRegex(key, r"^[0-9a-f]{64}$")
            self.assertEqual(json.loads(path.read_text())["secret_key"], key)
            original = path.read_bytes()
            self.assertEqual(load_or_create_secret_key(path), key)
            self.assertEqual(path.read_bytes(), original)

    def test_independent_installations_get_different_keys(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            self.assertNotEqual(load_or_create_secret_key(root / "a.json"),
                                load_or_create_secret_key(root / "b.json"))

    def test_concurrent_starts_use_one_key_and_remove_temporary_files(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "web_secret.json"
            with ThreadPoolExecutor(max_workers=8) as executor:
                keys = list(executor.map(lambda _: load_or_create_secret_key(path), range(32)))
            self.assertEqual(len(set(keys)), 1)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_transient_windows_read_conflicts_reuse_existing_key(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "web_secret.json"
            key = load_or_create_secret_key(path)
            original = path.read_bytes()
            for winerror in (5, 32, 33):
                with self.subTest(winerror=winerror):
                    conflict = PermissionError("File temporarily locked")
                    conflict.winerror = winerror
                    with patch.object(Path, "read_text", side_effect=[
                        conflict, conflict, original.decode("utf-8")
                    ]) as read, patch("web.secret_key.time.sleep") as sleep:
                        self.assertEqual(load_or_create_secret_key(path), key)
                    self.assertEqual(read.call_count, 3)
                    self.assertEqual(sleep.call_count, 2)
                    self.assertEqual(path.read_bytes(), original)

    def test_persistent_windows_read_conflict_fails_after_bounded_retries(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "web_secret.json"
            load_or_create_secret_key(path)
            original = path.read_bytes()
            conflict = PermissionError("File remains locked")
            conflict.winerror = 32
            with patch.object(Path, "read_text", side_effect=conflict) as read, patch(
                "web.secret_key.time.sleep"
            ) as sleep:
                with self.assertRaises(RuntimeError) as raised:
                    load_or_create_secret_key(path)
            self.assertIs(raised.exception.__cause__, conflict)
            self.assertEqual(read.call_count, 7)
            self.assertAlmostEqual(sum(call.args[0] for call in sleep.call_args_list), 0.63)
            self.assertEqual(path.read_bytes(), original)

    def test_other_read_errors_fail_without_retry(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "web_secret.json"
            load_or_create_secret_key(path)
            for error in (PermissionError("Access denied"), OSError("Read failed")):
                with self.subTest(error=error), patch.object(
                    Path, "read_text", side_effect=error
                ), patch("web.secret_key.time.sleep") as sleep:
                    with self.assertRaises(RuntimeError) as raised:
                        load_or_create_secret_key(path)
                    self.assertIs(raised.exception.__cause__, error)
                    sleep.assert_not_called()

    def test_separate_processes_reuse_persisted_key(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "web_secret.json"
            with ProcessPoolExecutor(
                max_workers=8, mp_context=multiprocessing.get_context("spawn")
            ) as executor:
                keys = list(executor.map(load_or_create_secret_key, [path] * 32))
            self.assertEqual(len(set(keys)), 1)
            self.assertEqual(load_or_create_secret_key(path), keys[0])
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_invalid_existing_key_fails_without_replacing_it(self):
        for content in ("", "broken json", "[]", '{"secret_key": "short"}',
                        '{"secret_key": null}'):
            with self.subTest(content=content), tempfile.TemporaryDirectory(dir=ROOT) as directory:
                path = Path(directory) / "web_secret.json"
                path.write_text(content)
                with self.assertRaises(RuntimeError):
                    load_or_create_secret_key(path)
                self.assertEqual(path.read_text(), content)

    def test_publish_failure_does_not_fall_back_or_leave_temporary_files(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "web_secret.json"
            publish = "os.rename" if os.name == "nt" else "os.link"
            with patch(f"web.secret_key.{publish}", side_effect=PermissionError):
                with self.assertRaises(PermissionError):
                    load_or_create_secret_key(path)
            self.assertEqual(list(path.parent.iterdir()), [])
