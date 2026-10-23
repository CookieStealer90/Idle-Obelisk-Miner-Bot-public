"""Compatibility entry point using the shared, isolated capture pipeline."""
import config.settings as s
from core.screen_cache import capture_screen


def screenshot_gray(local_path: str = None):
    """Take a fresh full screenshot; return (gray_image, width, height)."""
    return capture_screen(local_path if local_path is not None else s.LOCAL_SCREEN,
                          slot="manual_scr")
