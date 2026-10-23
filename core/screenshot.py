# screenshot.py - Screenshot capture via ADB
import cv2

from config.settings import REMOTE_SCREEN, LOCAL_SCREEN
from core.adb_helper import adb


def screenshot_gray(local_path: str = None):
    """Take a screenshot via ADB, return (gray_image, width, height)."""
    if local_path is None:
        local_path = LOCAL_SCREEN
    adb("shell", "screencap", "-p", REMOTE_SCREEN)
    adb("pull", REMOTE_SCREEN, local_path)
    adb("shell", "rm", REMOTE_SCREEN)
    img = cv2.imread(local_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None, 900, 1600
    h, w = img.shape[:2]
    return img, w, h
