"""Key persistence checks without importing the app or starting the bot."""
from concurrent.futures import ThreadPoolExecutor
import json
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
