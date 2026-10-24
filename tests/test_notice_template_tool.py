"""Template authoring tests using synthetic screenshots only; no ADB or GUI."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image, PngImagePlugin

from tools.create_notice_template import create, make_pair, parser
from tools.create_notice_template import ROOT, PRESETS


class NoticeTemplateToolTests(unittest.TestCase):
    def test_sanitization_preserves_only_selected_pixels_and_distinct_labels(self):
        image = np.arange(20 * 30 * 3, dtype=np.uint8).reshape(20, 30, 3)
        frame, mask = make_pair(image, (2, 3, 22, 15), [(1, 0, 19, 2), (1, 10, 19, 12)])
        self.assertEqual(set(np.unique(mask)), {0, 1, 2})
        self.assertTrue(np.array_equal(frame[mask > 0], image[3:15, 2:22][mask > 0]))
        self.assertFalse(frame[mask == 0].any())

    def test_invalid_crop_regions_and_overlaps_are_rejected(self):
        image = np.zeros((20, 30, 3), np.uint8)
        for crop, regions in [((0, 0, 31, 20), [(0, 0, 1, 1)] * 2),
                              ((0, 0, 30, 20), [(0, 0, 1, 1)]),
                              ((0, 0, 30, 20), [(0, 0, 2, 2), (1, 1, 3, 3)]),
                              ((0, 0, 30, 20), [(0, 0, 2, 2), (28, 18, 31, 20)])]:
            with self.subTest(crop=crop, regions=regions), self.assertRaises(ValueError):
                make_pair(image, crop, regions)

    def _arguments(self, directory):
        source = directory / "source.png"
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("private", "must not be copied")
        image = np.full((40, 50, 3), 15, np.uint8)
        image[5:7, 6:24] = (150, 80, 40)
        image[15:17, 6:24] = (80, 150, 40)
        image[9:12, 8:20] = 255  # Simulated private content outside the regions.
        Image.fromarray(image).save(source, pnginfo=metadata)
        args = parser().parse_args([str(source), "--name", "example", "--crop", "5", "5", "25", "17",
            "--region", "1", "0", "19", "2", "--region", "1", "10", "19", "12",
            "--output-dir", str(directory / "output")])
        return args

    def test_generation_validates_source_strips_metadata_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self._arguments(Path(directory))
            original = args.screenshot.read_bytes()
            with redirect_stdout(StringIO()):
                create(args)
            output = Path(args.output_dir)
            self.assertEqual(len(list(output.iterdir())), 3)
            with Image.open(output / "example_frame.png") as frame:
                self.assertNotIn("private", frame.info)
                self.assertFalse(np.array(frame)[3:7, 3:15].any())
            self.assertEqual(original, args.screenshot.read_bytes())
            with self.assertRaises(ValueError):
                create(args)

    def test_negative_match_fails_before_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self._arguments(Path(directory))
            args.negative = [args.screenshot]
            with redirect_stdout(StringIO()), self.assertRaisesRegex(ValueError, "Negative validation failed"):
                create(args)
            self.assertFalse(Path(args.output_dir).exists())

    def test_independent_positive_miss_fails_before_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self._arguments(Path(directory))
            blank = Path(directory) / "blank.png"
            Image.new("RGB", (50, 40)).save(blank)
            args.positive = [blank]
            with redirect_stdout(StringIO()), self.assertRaisesRegex(ValueError, "Positive validation failed"):
                create(args)
            self.assertFalse(Path(args.output_dir).exists())

    def test_unsafe_names_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self._arguments(Path(directory))
            for name in ("../outside", "Uppercase", "with space", "", "0notice"):
                args.name = name
                with self.assertRaises(ValueError):
                    create(args)

    def test_known_presets_generate_compatible_sanitized_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for preset, (roi, _) in PRESETS.items():
                image = Image.new("RGB", (900, 1600), (40, 40, 40))
                with Image.open(ROOT / "images" / "Notices" / (preset + "_frame.png")) as frame:
                    image.paste(frame, roi[:2])
                source = directory / (preset + ".png")
                image.save(source)
                args = parser().parse_args([str(source), "--name", preset + "_copy", "--preset", preset,
                                            "--output-dir", str(directory / "generated")])
                with redirect_stdout(StringIO()):
                    create(args)
                with Image.open(directory / "generated" / (preset + "_copy_frame.png")) as frame:
                    self.assertEqual(frame.size, (roi[2] - roi[0], roi[3] - roi[1]))


if __name__ == "__main__":
    unittest.main()
