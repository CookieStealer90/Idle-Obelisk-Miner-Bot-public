"""Masked frame matching. Text and item artwork never participate in detection."""
from pathlib import Path

import cv2
import numpy as np


def detect_notice(image, roi, template_dir, pattern, threshold):
    if image is None or image.ndim != 3:
        raise ValueError("A color screenshot is required")
    x1, y1, x2, y2 = roi
    height, width = image.shape[:2]
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError("Notice search ROI must fit inside the screenshot")
    search = image[y1:y2, x1:x2]
    best = {"found": False, "score": 0.0, "variant": None, "roi": None}
    paths = sorted(Path(template_dir).glob(pattern))
    if not paths:
        raise ValueError("No notice frame templates found")
    usable = 0
    for path in paths:
        frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
        mask = cv2.imread(str(path.with_name(path.stem + "_mask.png")), cv2.IMREAD_GRAYSCALE)
        if frame is None or mask is None or mask.shape != frame.shape[:2] or not mask.any():
            raise ValueError(f"Invalid notice frame/mask: {path.name}")
        h, w = mask.shape
        if h > search.shape[0] or w > search.shape[1]:
            continue
        usable += 1
        # Each mask label denotes an independent frame/background strip. Taking
        # the worst strip prevents a large dark background from hiding a bad border.
        errors = []
        for label in np.unique(mask):
            if not label:
                continue
            strip = (mask == label).astype(np.uint8)
            squared = cv2.matchTemplate(search, frame, cv2.TM_SQDIFF, mask=strip)
            errors.append(np.sqrt(np.maximum(squared, 0) / (strip.sum() * 3)) / 255.0)
        scores = 1.0 - np.maximum.reduce(errors)
        scores = np.nan_to_num(scores, nan=-1, posinf=-1, neginf=-1)
        _, score, _, (dx, dy) = cv2.minMaxLoc(scores)
        if score > best["score"]:
            ys, xs = np.nonzero(mask)
            best = {"found": score >= threshold, "score": float(score),
                    "variant": path.stem.removesuffix("_frame"),
                    "roi": (x1 + dx, y1 + dy, x1 + dx + w, y1 + dy + h),
                    "identity_roi": (x1 + dx + int(xs.min()), y1 + dy + int(ys.min()),
                                     x1 + dx + int(xs.max()) + 1, y1 + dy + int(ys.max()) + 1)}
    if not usable:
        raise ValueError("Notice search ROI is smaller than all frame templates")
    return best
