# core/vision.py - Template matching helpers
"""
OpenCV template-matching wrappers used by features to find UI elements.

Coordinate convention for ROIs: (x1, y1, x2, y2) in screen pixels.
All images are handled in grayscale.
"""
import os
import cv2

from config.settings import BASE_DIR

IMG_DIR = os.path.join(str(BASE_DIR), "images")


def _load_template_gray(rel_path: str):
    """Load a template from images/<rel_path> as grayscale. Returns None on failure."""
    full = rel_path if os.path.isabs(rel_path) else os.path.join(IMG_DIR, rel_path)
    return cv2.imread(full, cv2.IMREAD_GRAYSCALE)


def _crop_roi(img, roi):
    x1, y1, x2, y2 = roi
    h, w = img.shape[:2]
    x1 = max(0, min(int(x1), w))
    y1 = max(0, min(int(y1), h))
    x2 = max(x1, min(int(x2), w))
    y2 = max(y1, min(int(y2), h))
    if x2 <= x1 or y2 <= y1:
        return None, (0, 0)
    return img[y1:y2, x1:x2], (x1, y1)


def find_template(img_gray, template_path: str, roi=None, threshold: float = 0.8):
    """Search for a template inside `img_gray` (optionally restricted to ROI).

    Returns dict:
        {"found": bool, "score": float, "cx": int, "cy": int,
         "x": int, "y": int, "w": int, "h": int}
    cx/cy = center of match in full-image coords. x/y = top-left.
    """
    result = {"found": False, "score": 0.0, "cx": 0, "cy": 0, "x": 0, "y": 0, "w": 0, "h": 0}
    if img_gray is None:
        return result

    tpl = _load_template_gray(template_path)
    if tpl is None:
        return result

    th, tw = tpl.shape[:2]
    if roi is not None:
        area, (ox, oy) = _crop_roi(img_gray, roi)
        if area is None or area.shape[0] < th or area.shape[1] < tw:
            return result
        search = area
    else:
        ox, oy = 0, 0
        if img_gray.shape[0] < th or img_gray.shape[1] < tw:
            return result
        search = img_gray

    res = cv2.matchTemplate(search, tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    x = int(max_loc[0] + ox)
    y = int(max_loc[1] + oy)

    result["score"] = float(max_val)
    result["x"], result["y"] = x, y
    result["w"], result["h"] = tw, th
    result["cx"], result["cy"] = x + tw // 2, y + th // 2
    result["found"] = max_val >= threshold
    return result
