"""Create sanitized Notices frame/mask pairs from local screenshots.

Run with --help; see tools/CREATE_NOTICE_TEMPLATE.md for examples.
No ADB, bot startup, OCR, settings changes or source-screenshot copies.
"""
import argparse
from io import BytesIO
from pathlib import Path
import re
import sys
import tempfile

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.notice_detection import detect_notice

PRESETS = {
    "level": ((0, 772, 372, 895), "level_frame_mask.png"),
    "shard": ((0, 750, 390, 918), "shard_frame_mask.png"),
}


def read_image(path):
    # Pillow supports Windows paths containing non-ASCII characters as well.
    with Image.open(path) as image:
        return cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)


def rectangle(value, width, height, label):
    x1, y1, x2, y2 = value
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError(f"{label} must fit inside {width} x {height}: {tuple(value)}")
    return x1, y1, x2, y2


def make_pair(image, crop_roi, regions=None, preset_mask=None):
    height, width = image.shape[:2]
    x1, y1, x2, y2 = rectangle(crop_roi, width, height, "Crop")
    crop = image[y1:y2, x1:x2].copy()
    h, w = crop.shape[:2]
    if preset_mask is not None:
        mask = preset_mask.copy()
        if mask.shape != (h, w):
            raise ValueError("Preset mask dimensions must match the crop")
    else:
        if not regions or not 2 <= len(regions) <= 255:
            raise ValueError("Select between 2 and 255 separate fixed frame/background regions")
        mask = np.zeros((h, w), np.uint8)
        for label, region in enumerate(regions, 1):
            rx1, ry1, rx2, ry2 = rectangle(region, w, h, "Mask region")
            if mask[ry1:ry2, rx1:rx2].any():
                raise ValueError("Mask regions must not overlap")
            mask[ry1:ry2, rx1:rx2] = label
    if len(np.unique(mask[mask > 0])) < 2:
        raise ValueError("The mask needs at least two independently checked regions")
    # Discard every ignored pixel and all source metadata before publication.
    crop[mask == 0] = 0
    return crop, mask


def select_regions(image):
    print("Select the complete notice including its icon; press Enter to accept or Esc to cancel.")
    try:
        x, y, w, h = map(int, cv2.selectROI("Notice crop", image, showCrosshair=True, fromCenter=False))
        if not w or not h:
            raise ValueError("Crop selection cancelled")
        cv2.destroyAllWindows()
        print("Select separate FIXED border/background strips. Enter confirms each; Esc finishes.")
        print("Do not select text, numbers, icons or moving game scenery. Choose at least two strips.")
        selected = cv2.selectROIs("Fixed regions only", image[y:y + h, x:x + w],
                                  showCrosshair=True, fromCenter=False)
        regions = [(int(rx), int(ry), int(rx + rw), int(ry + rh)) for rx, ry, rw, rh in selected]
        return (x, y, x + w, y + h), regions
    finally:
        cv2.destroyAllWindows()


def png_bytes(image, color=False):
    if color:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    buffer = BytesIO()
    Image.fromarray(image).save(buffer, format="PNG")
    return buffer.getvalue()


def create(args):
    if not re.fullmatch(r"[a-z][a-z0-9_]*", args.name):
        raise ValueError("Name must start with a lowercase letter and contain only a-z, 0-9 and underscores")
    if not 0 < args.threshold <= 1:
        raise ValueError("Threshold must be greater than 0 and at most 1")
    if args.regions and args.crop is None:
        raise ValueError("--region requires --crop")
    if args.install and args.output_dir:
        raise ValueError("Use either --install or --output-dir")
    image = read_image(args.screenshot)
    preset_mask = None
    regions = args.regions
    if args.preset:
        crop_roi, filename = PRESETS[args.preset]
        with Image.open(ROOT / "images" / "Notices" / filename) as mask_image:
            preset_mask = np.array(mask_image.convert("L"))
    elif args.interactive:
        crop_roi, regions = select_regions(image)
    else:
        crop_roi = args.crop
    frame, mask = make_pair(image, crop_roi, regions, preset_mask)
    search_roi = args.search_roi or crop_roi
    x1, y1, x2, y2 = rectangle(search_roi, image.shape[1], image.shape[0], "Search ROI")
    if not (x1 <= crop_roi[0] < crop_roi[2] <= x2 and y1 <= crop_roi[1] < crop_roi[3] <= y2):
        raise ValueError("Search ROI must contain the complete crop")
    destination = (ROOT / "images" / "Notices" if args.install else
                   Path(args.output_dir) if args.output_dir else ROOT / "temp" / "notice_templates")
    names = [args.name + "_frame.png", args.name + "_frame_mask.png", args.name + "_preview.png"]
    if any((destination / name).exists() for name in names):
        raise ValueError("Output already exists; use a new name or a different output directory")
    # Self-check in an isolated directory; only sanitized assets are written.
    with tempfile.TemporaryDirectory(prefix="notice_template_") as directory:
        staging = Path(directory)
        (staging / names[0]).write_bytes(png_bytes(frame, color=True))
        (staging / names[1]).write_bytes(png_bytes(mask))
        for label, source, should_match in [
            ("Source", image, True),
            *[("Positive", read_image(path), True) for path in args.positive],
            *[("Negative", read_image(path), False) for path in args.negative],
        ]:
            match = detect_notice(source, search_roi, staging, names[0], args.threshold)
            print(f"{label}: found={match['found']} score={match['score']:.4f}")
            if match["found"] != should_match:
                raise ValueError(f"{label} validation failed; no output pair was installed")
        # A bright, sanitized mask preview makes even low-valued mask labels visible.
        preview = np.zeros_like(frame)
        preview[mask > 0] = (80, 220, 80)
        preview = np.concatenate((frame, preview), axis=1)
        payloads = [png_bytes(frame, color=True), png_bytes(mask), png_bytes(preview, color=True)]
        destination.mkdir(parents=True, exist_ok=True)
        created = []
        try:
            for name, payload in zip(names, payloads):
                path = destination / name
                with path.open("xb") as output:
                    created.append(path)
                    output.write(payload)
        except Exception:
            for path in created:
                path.unlink(missing_ok=True)
            raise
    print(f"Created sanitized frame, mask and preview in: {destination.resolve()}")
    print("No text outside the selected regions or screenshot metadata was copied.")
    print(f"Required search coverage: {tuple(crop_roi)}; check NOTICES_DETECT_ROI before enabling.")
    if args.install:
        print("Installed. The default Notices template glob loads the pair on the next scan.")
    else:
        print("Review the preview, then copy only the frame and mask into images/Notices/.")


def parser():
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("screenshot", type=Path, help="Original unscaled screenshot; never modified")
    cli.add_argument("--name", required=True, help="Unique variant name, for example special_notice")
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preset", choices=PRESETS, help="Reuse a known crop and mask automatically")
    mode.add_argument("--crop", nargs=4, type=int, metavar=("X1", "Y1", "X2", "Y2"))
    mode.add_argument("--interactive", action="store_true", help="Select crop and fixed regions with the mouse")
    cli.add_argument("--region", dest="regions", action="append", nargs=4, type=int,
                     metavar=("X1", "Y1", "X2", "Y2"), help="Fixed region relative to crop; repeat at least twice")
    cli.add_argument("--search-roi", nargs=4, type=int, help="Validation search ROI; defaults to the crop")
    cli.add_argument("--positive", type=Path, action="append", default=[], help="Additional same-frame screenshot expected to match")
    cli.add_argument("--negative", type=Path, action="append", default=[], help="Screenshot without this frame; must not match")
    cli.add_argument("--threshold", type=float, default=.96, help="Validation threshold, default 0.96")
    cli.add_argument("--output-dir", type=Path, help="Default: project temp/notice_templates (not active)")
    cli.add_argument("--install", action="store_true", help="Write directly to project images/Notices (active)")
    return cli


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    try:
        create(args)
    except (OSError, ValueError, cv2.error) as exc:
        cli.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
