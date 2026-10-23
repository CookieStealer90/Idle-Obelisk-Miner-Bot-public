"""Calibration helper for Rainbow-Floor detection.

Usage:
    python tools/calibrate_rainbow.py

Scans images/Workflows/*.png (labels inferred from filename prefix pos_/neg_)
and temp/*.png (fallback negatives) and prints multiple candidate metrics
for picking thresholds.

Metrics:
    sat_px           total saturated (S>=sat_min, V>=val_min) pixel count
    buckets          number of hue buckets with >= min_per_bucket pixels
    hue_entropy      Shannon entropy of hue distribution over sat pixels (0..log2(N))
    block_rb         count of NxN blocks where sat-pixel hues span >= K buckets
                     (strong rainbow signal: many colors in same small area)
"""
import os
import glob
import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ROI = (115, 269, 813, 1041)
SAT_MIN = 180
VAL_MIN = 150
HUE_BUCKETS = 12
MIN_PIXELS_PER_BUCKET = 200

# block metric — local hue diversity within small patches
BLOCK_SIZE = 32
BLOCK_MIN_SAT_PX = 40           # at least this many sat pixels in the block
BLOCK_MIN_BUCKETS = 4           # block "rainbow-like" if sat pixels span >=4 hue buckets
BLOCK_BUCKETS = 6               # coarser: 6 buckets over 0..180 (30 deg each)


def analyze(path: str):
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        return None
    x1, y1, x2, y2 = ROI
    h, w = img.shape[:2]
    x1 = max(0, min(x1, w)); x2 = max(x1, min(x2, w))
    y1 = max(0, min(y1, h)); y2 = max(y1, min(y2, h))
    crop = img[y1:y2, x1:x2]
    area = crop.shape[0] * crop.shape[1]

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    mask = (S >= SAT_MIN) & (V >= VAL_MIN)
    sat_count = int(mask.sum())

    # --- buckets ---
    hues = H[mask]
    edges = np.linspace(0, 180, HUE_BUCKETS + 1)
    counts, _ = np.histogram(hues, bins=edges)
    active_buckets = int((counts >= MIN_PIXELS_PER_BUCKET).sum())

    # --- entropy over bucket distribution ---
    probs = counts.astype(np.float64)
    if probs.sum() > 0:
        probs /= probs.sum()
        nz = probs[probs > 0]
        entropy = float(-(nz * np.log2(nz)).sum())
    else:
        entropy = 0.0

    # --- block metric: count blocks with locally diverse hues ---
    bh, bw = crop.shape[:2]
    block_rb = 0
    total_blocks = 0
    coarse_edges = np.linspace(0, 180, BLOCK_BUCKETS + 1)
    for yy in range(0, bh - BLOCK_SIZE + 1, BLOCK_SIZE):
        for xx in range(0, bw - BLOCK_SIZE + 1, BLOCK_SIZE):
            blk_mask = mask[yy:yy+BLOCK_SIZE, xx:xx+BLOCK_SIZE]
            n = int(blk_mask.sum())
            if n < BLOCK_MIN_SAT_PX:
                continue
            total_blocks += 1
            blk_h = H[yy:yy+BLOCK_SIZE, xx:xx+BLOCK_SIZE][blk_mask]
            c, _ = np.histogram(blk_h, bins=coarse_edges)
            if int((c >= 5).sum()) >= BLOCK_MIN_BUCKETS:
                block_rb += 1

    return {
        "path": os.path.relpath(path, ROOT),
        "sat_count": sat_count,
        "sat_pct": 100.0 * sat_count / max(1, area),
        "active_buckets": active_buckets,
        "entropy": entropy,
        "block_rb": block_rb,
        "total_blocks": total_blocks,
    }


def label_for(name: str) -> str:
    b = os.path.basename(name).lower()
    if b.startswith("pos_"):
        return "POS"
    if b.startswith("neg_"):
        return "NEG"
    return "POS"  # legacy: unprefixed images/Workflows files are positives


def main():
    in_wf = sorted(glob.glob(os.path.join(ROOT, "images", "Workflows", "*.png")))
    in_temp = sorted(glob.glob(os.path.join(ROOT, "temp", "*.png")))

    rows = []
    for f in in_wf:
        rows.append((label_for(f), f))
    for f in in_temp:
        rows.append(("NEG", f))

    print(f"ROI={ROI}  S>={SAT_MIN}  V>={VAL_MIN}  min_per_bucket={MIN_PIXELS_PER_BUCKET}")
    print(f"Block: {BLOCK_SIZE}px  min_sat_px={BLOCK_MIN_SAT_PX}  need>={BLOCK_MIN_BUCKETS}/{BLOCK_BUCKETS} coarse buckets")
    print("-" * 110)
    print(f"{'label':<5} {'file':<50} {'sat_px':>8} {'sat%':>6} {'buckets':>7} {'entropy':>8} {'block_rb':>10}")
    print("-" * 110)

    for lbl, f in rows:
        r = analyze(f)
        if not r:
            continue
        print(f"[{lbl}] {r['path']:<50} {r['sat_count']:>8d} {r['sat_pct']:>5.1f}% "
              f"{r['active_buckets']:>7d} {r['entropy']:>8.3f} {r['block_rb']:>4d}/{r['total_blocks']:<4d}")


if __name__ == "__main__":
    main()
