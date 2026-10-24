"""Unicode image loading, shared logging and interpreter selection; no bot startup."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from core.image_io import read_image
from core import file_logger, vision, rotation_cache
from tools import python_environment
from core.notice_detection import detect_notice

ROOT = Path(__file__).resolve().parent.parent


class UnicodeImagesTests(unittest.TestCase):
    def test_notice_frames_and_masks_work_from_unicode_directories(self):
        from test_notices import fixture
        with tempfile.TemporaryDirectory(dir=ROOT, prefix="frames_\u00e4_") as directory:
            images = Path(directory)
            destination = images / "Notices"
            destination.mkdir()
            for source in (ROOT / "images" / "Notices").glob("*.png"):
                (destination / source.name).write_bytes(source.read_bytes())
            match = detect_notice(fixture("level"), (0, 740, 390, 925), images,
                                  "Notices/*_frame.png", 0.96)
            self.assertTrue(match["found"])
            self.assertEqual(match["variant"], "level")

    def test_template_loading_and_rotation_support_unicode_paths(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix="unicode_\u00e4_") as directory:
            path = Path(directory) / "template.png"
            image = np.arange(144, dtype=np.uint8).reshape(12, 12)
            path.write_bytes(cv2.imencode(".png", image)[1].tobytes())
            self.assertTrue(np.array_equal(read_image(path, cv2.IMREAD_GRAYSCALE), image))
            self.assertTrue(np.array_equal(vision._load_template_gray(str(path)), image))
            with patch.object(rotation_cache, "_cache", {}):
                rotations, mask = rotation_cache.get_rotated_templates(str(path), 4)
                self.assertEqual(len(rotations), 4)
                self.assertEqual(mask.shape, image.shape)
            path.write_bytes(b"not an image")
            self.assertIsNone(read_image(path))
            self.assertIsNone(read_image(path.with_name("missing.png")))


class LoggingTests(unittest.TestCase):
    def test_console_and_bot_share_rotation_without_losing_concurrent_lines(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "bot.log"
            cfg = types.SimpleNamespace(ENABLE_FILE_LOG=True, FILE_LOG_PATH=str(path))
            with patch.object(file_logger.state, "cfg", cfg), \
                 patch.object(file_logger.settings, "LOG_MAX_SIZE_MB", 0.0002), \
                 patch.object(file_logger.settings, "LOG_BACKUP_COUNT", 100):
                stream = file_logger.FileLogStream()
                def write(index):
                    if index % 2:
                        stream.write(f"console-{index}")
                        stream.write("\n")
                    else:
                        file_logger.bot_log(f"bot-{index}", "TXT")
                with ThreadPoolExecutor(max_workers=4) as executor:
                    list(executor.map(write, range(40)))
                content = "\n".join(p.read_text(encoding="utf-8") for p in path.parent.glob("bot.log*"))
                for index in range(40):
                    label = f"{'console' if index % 2 else 'bot'}-{index}"
                    self.assertEqual(sum(line.endswith("] " + label) for line in content.splitlines()), 1)
                self.assertTrue(path.with_name("bot.log.1").exists())

    def test_startup_console_uses_same_absolute_path_before_bot_config_is_wired(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            with patch.object(file_logger.settings, "BASE_DIR", Path(directory)), \
                 patch.object(file_logger.state, "cfg", None):
                stream = file_logger.FileLogStream()
                stream.write("startup")
                stream.flush()
                self.assertIn("startup", (Path(directory) / "bot.log").read_text())


class InterpreterTests(unittest.TestCase):
    def test_launcher_uses_project_python_and_preserves_port_without_starting_bot(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            scripts = root / ".venv" / "Scripts"
            scripts.mkdir(parents=True)
            (scripts / "pythonw.exe").touch()
            with patch.object(python_environment, "ROOT", root), \
                 patch.object(python_environment.subprocess, "Popen") as launch:
                python_environment.main(["--launch", "6002"])
            self.assertEqual(launch.call_args.args[0],
                             [str(scripts / "pythonw.exe"), str(root / "tray_runner.py"), "6002"])
            self.assertEqual(launch.call_args.kwargs["cwd"], root)

    def test_installer_uses_requirements_and_never_recreates_existing_environment(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            scripts = root / ".venv" / "Scripts"
            scripts.mkdir(parents=True)
            (scripts / "python.exe").touch()
            with patch.object(python_environment, "ROOT", root), \
                 patch.object(python_environment.venv, "EnvBuilder") as create, \
                 patch.object(python_environment.subprocess, "run") as install, \
                 patch("builtins.print"):
                python_environment.main(["--install"])
            create.assert_not_called()
            self.assertEqual(install.call_args.args[0],
                             [str(scripts / "python.exe"), "-m", "pip", "install", "-r", str(root / "requirements.txt")])
            self.assertTrue(install.call_args.kwargs["check"])

    def test_project_environment_wins_over_global_python_and_broken_env_never_falls_back(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            self.assertEqual(python_environment.selected_python(root), Path(python_environment.sys.executable))
            scripts = root / ".venv" / "Scripts"
            scripts.mkdir(parents=True)
            with self.assertRaises(RuntimeError):
                python_environment.selected_python(root)
            for name in ("python.exe", "pythonw.exe"):
                (scripts / name).write_bytes(b"test executable placeholder")
            self.assertEqual(python_environment.selected_python(root), scripts / "python.exe")
            self.assertEqual(python_environment.selected_python(root, windowed=True), scripts / "pythonw.exe")
