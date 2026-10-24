"""OpenCV decoding with filesystem support for Unicode paths on Windows."""
from pathlib import Path

import cv2
import numpy as np


def read_image(path, flags=cv2.IMREAD_COLOR):
    """Return a decoded image or None, matching imread's failure contract."""
    try:
        data = Path(path).read_bytes()
        if not data:
            return None
        return cv2.imdecode(np.frombuffer(data, dtype=np.uint8), flags)
    except (OSError, ValueError, cv2.error):
        return None
