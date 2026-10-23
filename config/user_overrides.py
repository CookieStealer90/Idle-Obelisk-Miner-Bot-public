# config/user_overrides.py
import json
from pathlib import Path


def load_user_settings(base_dir: Path) -> dict:
    p = base_dir / "config" / "user_settings.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def apply_overrides_to_settings(settings_globals: dict, overrides: dict):
    """Apply user_settings.json overrides to settings globals."""
    adb = overrides.get("adb", {})
    if "DEVICE" in adb:
        settings_globals["DEVICE"] = adb["DEVICE"]
    if "ADB_AUTO_CONNECT" in adb:
        settings_globals["ADB_AUTO_CONNECT"] = adb["ADB_AUTO_CONNECT"]
    if "ADB_CONNECT_TIMEOUT" in adb:
        settings_globals["ADB_CONNECT_TIMEOUT"] = adb["ADB_CONNECT_TIMEOUT"]
    if "ADB_MAX_RETRIES" in adb:
        settings_globals["ADB_MAX_RETRIES"] = adb["ADB_MAX_RETRIES"]
    if "ADB_SCAN_PORTS" in adb:
        settings_globals["ADB_SCAN_PORTS"] = adb["ADB_SCAN_PORTS"]

    scroll = overrides.get("scroll", {})
    _scroll_keys = (
        "SCROLL_DEFAULT_AREA",
        "SCROLL_DEFAULT_SPEED",
        "SCROLL_DURATION_SLOW_MS",
        "SCROLL_DURATION_MID_MS",
        "SCROLL_DURATION_FAST_MS",
        "SCROLL_DISTANCE_SLOW_PX",
        "SCROLL_DISTANCE_MID_PX",
        "SCROLL_DISTANCE_FAST_PX",
        "SCROLL_EDGE_PADDING_PX",
        "SCROLL_LOG_LEVEL",
    )
    for k in _scroll_keys:
        if k in scroll:
            v = scroll[k]
            # SCROLL_DEFAULT_AREA comes back as list from JSON — coerce to tuple
            if k == "SCROLL_DEFAULT_AREA" and isinstance(v, list):
                try:
                    v = tuple(int(x) for x in v)
                except Exception:
                    continue
            settings_globals[k] = v

    running = overrides.get("running_detection", {})
    _running_keys = (
        "RUNNING_ROI",
        "RUNNING_MATCH_THRESHOLD",
        "RUNNING_CHECK_CACHE_AGE_S",
        "RUNNING_LOG_LEVEL",
    )
    for k in _running_keys:
        if k in running:
            v = running[k]
            if k == "RUNNING_ROI" and isinstance(v, list):
                try:
                    v = tuple(int(x) for x in v)
                except Exception:
                    continue
            settings_globals[k] = v

    freebies = overrides.get("freebies", {})
    _freebies_keys = (
        "FREEBIES_CHECK_INTERVAL_S",
        "FREEBIES_DETECT_ROI",
        "FREEBIES_CLAIM_ROI",
        "FREEBIES_MATCH_THRESHOLD",
        "FREEBIES_SCROLL_ATTEMPTS",
        "FREEBIES_SCROLL_TO_TOP_COUNT",
        "FREEBIES_POST_OPEN_DELAY_S",
        "FREEBIES_TAP_JITTER_PX",
        "FREEBIES_DIAMONDS_PER_CLAIM",
        "FREEBIES_LOG_LEVEL",
        "FREEBIES_LOG_LEVEL_CLAIMED",
        "FREEBIES_CLOSE_ROI",
        "FREEBIES_POST_CLAIM_DELAY_S",
    )
    for k in _freebies_keys:
        if k in freebies:
            v = freebies[k]
            if k in ("FREEBIES_DETECT_ROI", "FREEBIES_CLAIM_ROI", "FREEBIES_CLOSE_ROI") and isinstance(v, list):
                try:
                    v = tuple(int(x) for x in v)
                except Exception:
                    continue
            settings_globals[k] = v

    lootbug = overrides.get("lootbug", {})
    _lootbug_keys = (
        "LOOTBUG_CHECK_INTERVAL_S",
        "LOOTBUG_BUSY_RETRY_S",
        "LOOTBUG_DETECT_ROI",
        "LOOTBUG_MATCH_THRESHOLD",
        "LOOTBUG_SCREEN_REUSE_AGE_S",
        "LOOTBUG_TAP_JITTER_PX",
        "LOOTBUG_POST_CLICK_DELAY_S",
        "LOOTBUG_CLOSE_ROI",
        "LOOTBUG_LOG_LEVEL",
        "LOOTBUG_LOG_LEVEL_DETECT",
        "LOOTBUG_LOG_LEVEL_CLICK",
        "LOOTBUG_LOG_LEVEL_BUSY",
        "LOOTBUG_LOG_LEVEL_BONUS",
        "LOOTBUG_BUY_GEM_UPGRADES_ENABLED",
        "LOOTBUG_BONUS_DETECT_ROI",
        "LOOTBUG_BONUS_BUY_ROI",
        "LOOTBUG_BONUS_TAP_JITTER_PX",
        "LOOTBUG_BONUS_DOUBLE_CLICK_DELAY_S",
    )
    _lootbug_roi_keys = ("LOOTBUG_DETECT_ROI", "LOOTBUG_CLOSE_ROI",
                         "LOOTBUG_BONUS_DETECT_ROI", "LOOTBUG_BONUS_BUY_ROI")
    for k in _lootbug_keys:
        if k in lootbug:
            v = lootbug[k]
            if k in _lootbug_roi_keys and isinstance(v, list):
                try:
                    v = tuple(int(x) for x in v)
                except Exception:
                    continue
            settings_globals[k] = v

    lootbug_founders = overrides.get("lootbug_founders", {})
    if "LOOTBUG_FOUNDERS_ENABLED" in lootbug_founders:
        settings_globals["LOOTBUG_FOUNDERS_ENABLED"] = bool(lootbug_founders["LOOTBUG_FOUNDERS_ENABLED"])
    if "LOOTBUG_FOUNDERS_LOG_LEVEL" in lootbug_founders:
        settings_globals["LOOTBUG_FOUNDERS_LOG_LEVEL"] = lootbug_founders["LOOTBUG_FOUNDERS_LOG_LEVEL"]

    sd = overrides.get("startup_defaults", {})
    if "freebies_enabled" in sd:
        settings_globals["FREEBIES_ENABLED_DEFAULT"] = bool(sd["freebies_enabled"])
    if "lootbug_enabled" in sd:
        settings_globals["LOOTBUG_ENABLED_DEFAULT"] = bool(sd["lootbug_enabled"])
    if "lootbug_buy_bonus" in sd:
        settings_globals["LOOTBUG_BUY_GEM_UPGRADES_ENABLED"] = bool(sd["lootbug_buy_bonus"])
    if "workflows_enabled" in sd:
        settings_globals["WORKFLOWS_ENABLED_DEFAULT"] = bool(sd["workflows_enabled"])
    if "detect_level_enabled" in sd:
        settings_globals["DETECT_LEVEL_ENABLED"] = bool(sd["detect_level_enabled"])

    dl = overrides.get("detect_level", {})
    _dl_keys = (
        "DETECT_LEVEL_ENABLED",
        "DETECT_LEVEL_ROI",
        "DETECT_LEVEL_INTERVAL_S",
        "DETECT_LEVEL_THRESHOLD",
        "DETECT_LEVEL_CACHE_MAX_AGE_S",
        "DETECT_LEVEL_NMS_MIN_DX_PX",
        "DETECT_LEVEL_LOG_LEVEL",
    )
    for k in _dl_keys:
        if k in dl:
            v = dl[k]
            if k == "DETECT_LEVEL_ROI" and isinstance(v, list):
                try:
                    v = tuple(int(x) for x in v)
                except Exception:
                    continue
            settings_globals[k] = v

    workflows = overrides.get("workflows", {})
    _workflow_keys = (
        "WF_INTERVAL_VARIANCE_PCT",
        "WORKFLOWS_TAP_JITTER_PX",
        "WORKFLOWS_SCREEN_REUSE_AGE_S",
        "WORKFLOWS_BUSY_RETRY_S",
        "WORKFLOWS_LOG_LEVEL",
        "WORKFLOWS_LOG_LEVEL_STEP",
        "WORKFLOWS_LOG_LEVEL_BUSY",
    )
    for k in _workflow_keys:
        if k in workflows:
            settings_globals[k] = workflows[k]

    scr = overrides.get("screenshot_viewer", {})
    if "SCREENSHOT_VIEWER_FILES" in scr:
        v = scr["SCREENSHOT_VIEWER_FILES"]
        if isinstance(v, list):
            settings_globals["SCREENSHOT_VIEWER_FILES"] = [str(x) for x in v]
