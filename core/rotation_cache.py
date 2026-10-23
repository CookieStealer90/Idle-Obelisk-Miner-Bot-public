# core/rotation_cache.py - Rotated template cache + matcher
"""
Process-lifetime cache of rotated grayscale templates and a
matcher that searches a screenshot ROI across all rotations.

Used by the workflow step type ``click_rotating`` (e.g. for the
star-sign templates under images/workflows/stargazing/, which
spin around their own axis in-game).

Cache key:  (absolute_template_path, mtime_ns, n_rotations)
            => list[np.ndarray]  (grayscale rotated copies)

The mtime_ns part means: replacing the PNG on disk transparently
invalidates the cache. As long as the file is unchanged the
rotations are computed exactly once per (path, n) and reused for
every match call afterwards.
"""
import os
import threading

import cv2
import numpy as np

from config.settings import BASE_DIR

IMG_DIR = os.path.join(str(BASE_DIR), "images")

_cache = {}            # (path, mtime_ns, n, downscale) -> (list[np.ndarray], mask)
_cache_lock = threading.Lock()


def _build_circular_mask(w: int, h: int) -> np.ndarray:
    """uint8 mask, 255 inside the inscribed circle, 0 outside.
    Used to ignore corner artifacts created by rotating a square template."""
    mask = np.zeros((h, w), dtype=np.uint8)
    cx, cy = w // 2, h // 2
    radius = min(w, h) // 2
    cv2.circle(mask, (cx, cy), radius, 255, thickness=-1)
    return mask


def _resolve(rel_path: str) -> str:
    return rel_path if os.path.isabs(rel_path) else os.path.join(IMG_DIR, rel_path)


def _rotate_one(tpl_gray: np.ndarray, angle: float) -> np.ndarray:
    """Rotate a single template by `angle` degrees around its center.
    Same conventions as _build_rotations (canvas size preserved,
    BORDER_CONSTANT 0). Used for on-the-fly sub-step refinement,
    NOT cached."""
    h, w = tpl_gray.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
    return cv2.warpAffine(
        tpl_gray, M, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )


def _build_rotations(tpl_gray: np.ndarray, n: int):
    """Generate N rotations of `tpl_gray` evenly spaced over 360°.

    Canvas size is preserved (in-place rotation around center). Border
    fill uses BORDER_REPLICATE so the corner artifacts after rotation
    stay close to edge pixels — works well for tightly-cropped templates
    where the visible content is roughly circular and the corners
    contain only "background-ish" pixels.
    """
    h, w = tpl_gray.shape[:2]
    cx, cy = w / 2.0, h / 2.0
    out = []
    for i in range(n):
        angle = (360.0 / n) * i
        if i == 0:
            out.append(tpl_gray.copy())
            continue
        M = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
        rot = cv2.warpAffine(
            tpl_gray, M, (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        out.append(rot)
    return out


def get_rotated_templates(rel_path: str, n: int, downscale: int = 1):
    """Return cached (rotations_list, circular_mask) for the template.

    Computed once per (absolute path, mtime_ns, n, downscale). The
    template is downscaled BEFORE building rotations so the match
    runs at the smaller size — matchTemplate cost scales roughly with
    template_area * search_area. The matching caller is expected to
    downscale its search area by the same factor.

    Returns (None, None) on load failure.
    """
    if n < 1:
        n = 1
    if downscale < 1:
        downscale = 1
    full = _resolve(rel_path)
    try:
        mtime_ns = os.stat(full).st_mtime_ns
    except OSError:
        return None, None
    key = (full, mtime_ns, int(n), int(downscale))
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None:
            return cached
    tpl = cv2.imread(full, cv2.IMREAD_GRAYSCALE)
    if tpl is None:
        return None, None
    if downscale > 1:
        h, w = tpl.shape[:2]
        new_w = max(2, w // downscale)
        new_h = max(2, h // downscale)
        tpl = cv2.resize(tpl, (new_w, new_h), interpolation=cv2.INTER_AREA)
    rots = _build_rotations(tpl, int(n))
    h, w = tpl.shape[:2]
    mask = _build_circular_mask(w, h)
    entry = (rots, mask)
    with _cache_lock:
        _cache[key] = entry
    return entry


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


def _match_one(search, rot, method, match_mask):
    if match_mask is not None:
        res = cv2.matchTemplate(search, rot, method, mask=match_mask)
    else:
        res = cv2.matchTemplate(search, rot, method)
    # Masked CCORR_NORMED can produce NaN/inf in low-variance regions —
    # treat those as no-match instead of letting them rank top.
    if not np.all(np.isfinite(res)):
        res = np.nan_to_num(res, nan=-1.0, posinf=-1.0, neginf=-1.0)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    return float(max_val), max_loc


def find_template_rotating(img_gray, rel_path: str, roi=None,
                            threshold: float = 0.8, rotations: int = 24,
                            early_exit: bool = True,
                            mask_mode: str = "circle",
                            downscale: int = 2):
    """Search for a template across `rotations` rotated variants.

    Two-pass coarse-to-fine angle search when rotations > 8:
      pass 1: every Kth rotation (K = rotations // 8)
      pass 2: refine ±(K-1) steps around the best candidate
    With early_exit=True the first rotation reaching `threshold` wins
    and pass 2 is skipped.

    `downscale` (>=1): scale the search area and template by 1/N before
    matching. Click coordinates are scaled back to full-image coords.
    matchTemplate cost ~ search_area * template_area, so 2x downscale
    means ~16x speedup per call (4x in each dimension on each side).

    Returns dict (compatible with previous shape):
        {"found", "score", "cx", "cy", "x", "y", "w", "h",
         "angle", "rotations_tried", "reason"}
    cx/cy is the click point in full-image coords (offsets added by caller).
    """
    result = {
        "found": False, "score": 0.0, "cx": 0, "cy": 0,
        "x": 0, "y": 0, "w": 0, "h": 0,
        "angle": 0.0, "rotations_tried": 0,
        "reason": "",
    }
    if img_gray is None:
        result["reason"] = "no_screenshot"
        return result

    if downscale < 1:
        downscale = 1

    rots, mask = get_rotated_templates(rel_path, rotations, downscale=downscale)
    if not rots:
        result["reason"] = f"template_load_failed ({_resolve(rel_path)})"
        return result

    use_mask = (str(mask_mode).lower() == "circle")
    method = cv2.TM_CCORR_NORMED if use_mask else cv2.TM_CCOEFF_NORMED
    match_mask = mask if use_mask else None

    # Template dimensions are at downscaled resolution.
    th_d, tw_d = rots[0].shape[:2]
    # Full-resolution dimensions for click-point reporting.
    th_full = th_d * downscale
    tw_full = tw_d * downscale
    result["w"], result["h"] = tw_full, th_full

    if roi is not None:
        area, (ox, oy) = _crop_roi(img_gray, roi)
        if area is None:
            result["reason"] = f"roi_invalid roi={roi}"
            return result
        if area.shape[0] < th_full or area.shape[1] < tw_full:
            result["reason"] = (
                f"roi_smaller_than_template "
                f"roi={tuple(roi)} ({area.shape[1]}x{area.shape[0]}) "
                f"tpl={tw_full}x{th_full}"
            )
            return result
        search_full = area
    else:
        ox, oy = 0, 0
        if img_gray.shape[0] < th_full or img_gray.shape[1] < tw_full:
            result["reason"] = (
                f"screen_smaller_than_template "
                f"screen={img_gray.shape[1]}x{img_gray.shape[0]} "
                f"tpl={tw_full}x{th_full}"
            )
            return result
        search_full = img_gray

    if downscale > 1:
        sw = max(2, search_full.shape[1] // downscale)
        sh = max(2, search_full.shape[0] // downscale)
        search = cv2.resize(search_full, (sw, sh), interpolation=cv2.INTER_AREA)
    else:
        search = search_full

    n = len(rots)
    angle_step = 360.0 / n

    # Coarse stride: pass 1 hits ~8 evenly-spaced indices.
    if n > 8:
        stride = max(2, n // 8)
    else:
        stride = 1

    tried_indices = set()
    best_score = -1.0
    best_loc = (0, 0)
    best_idx = 0

    def _eval(idx):
        nonlocal best_score, best_loc, best_idx
        if idx in tried_indices:
            return False
        tried_indices.add(idx)
        score, loc = _match_one(search, rots[idx], method, match_mask)
        if score > best_score:
            best_score = score
            best_loc = loc
            best_idx = idx
        return early_exit and score >= threshold

    # Pass 1: coarse stride.
    for i in range(0, n, stride):
        if _eval(i):
            break

    # Pass 2: refine around best, only if early_exit didn't already hit.
    if best_score < threshold and stride > 1:
        for off in range(1, stride):
            for sign in (+1, -1):
                idx = (best_idx + sign * off) % n
                if _eval(idx):
                    break
            else:
                continue
            break

    # Pass 3 (sub-step): the discrete rotation grid causes score dips
    # between steps — try 4 fresh rotations at ±¼ and ±½ step around
    # the current best. Only when we missed and the grid is coarse.
    sub_tried = 0
    best_angle_sub = None
    if best_score < threshold and n > 1:
        base_tpl = rots[0]
        base_angle = angle_step * best_idx
        sub_offsets = (-0.5, -0.25, 0.25, 0.5)
        for frac in sub_offsets:
            ang = base_angle + angle_step * frac
            rot = _rotate_one(base_tpl, ang)
            score, loc = _match_one(search, rot, method, match_mask)
            sub_tried += 1
            if score > best_score:
                best_score = score
                best_loc = loc
                # Sub-step angle is fractional — store it directly.
                best_idx = -1  # marker: angle below is fractional
                best_angle_sub = ang % 360.0
            if early_exit and score >= threshold:
                break

    # Translate downscaled location -> full-resolution coords.
    x_d, y_d = best_loc
    x = int(x_d * downscale + ox)
    y = int(y_d * downscale + oy)
    result["score"] = float(best_score)
    result["x"], result["y"] = x, y
    result["cx"], result["cy"] = x + tw_full // 2, y + th_full // 2
    if best_idx == -1 and best_angle_sub is not None:
        result["angle"] = float(best_angle_sub)
    else:
        result["angle"] = float(angle_step * best_idx)
    result["rotations_tried"] = len(tried_indices) + sub_tried
    result["found"] = best_score >= threshold
    return result


def clear_cache():
    """Drop all cached rotations (debug / hot-reload helper)."""
    with _cache_lock:
        _cache.clear()
