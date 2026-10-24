# config/user_overrides.py
import warnings
from pathlib import Path

from config.validation import validate_settings
from config.json_store import read_json


def migrate_founders_settings(overrides: dict) -> dict:
    """Normalize legacy Founders settings without changing the input or disk.

    Snapshot inherited Lootbug overrides once; explicit Founders values win.
    After saving the normalized document, future Lootbug edits are independent.
    """
    result = dict(overrides)
    legacy = result.pop("lootbug_founders", None)
    if isinstance(legacy, dict):
        founders = {}
        lootbug = result.get("lootbug", {})
        for suffix in (
            "CHECK_INTERVAL_S", "BUSY_RETRY_S", "MATCH_THRESHOLD",
            "SCREEN_REUSE_AGE_S", "TAP_JITTER_PX", "LOG_LEVEL_CLICK", "LOG_LEVEL_BUSY",
        ):
            key = "LOOTBUG_" + suffix
            if key in lootbug:
                founders["FOUNDERS_" + suffix] = lootbug[key]
        for key, value in legacy.items():
            if key.startswith("LOOTBUG_FOUNDERS_"):
                founders[key.removeprefix("LOOTBUG_")] = value
        founders.update(result.get("founders", {}))
        result["founders"] = founders
    if "founders" in result:
        founders = dict(result["founders"])
        if "FOUNDERS_CHECK_INTERVAL_S" in founders:
            founders.setdefault("FOUNDERS_CHECK_INTERVAL_S_FIRST",
                                founders.pop("FOUNDERS_CHECK_INTERVAL_S"))
        if "FOUNDERS_ENABLED" in founders:
            startup = dict(result.get("startup_defaults", {}))
            startup.setdefault("FOUNDERS_ENABLED", founders.pop("FOUNDERS_ENABLED"))
            result["startup_defaults"] = startup
        for key in ("FOUNDERS_CLOSE_ROI", "FOUNDERS_CLOSE_TEMPLATE", "FOUNDERS_POST_CLICK_DELAY_S"):
            founders.pop(key, None)
        result["founders"] = founders
    return result


def validate_screenshot_settings(values: dict) -> dict:
    """Validate against the shared schema and retain existing numeric coercion."""
    validate_settings({"screenshot_capture": values})
    result = dict(values)
    if "SCREENSHOT_CAPTURE_ATTEMPTS" in result:
        result["SCREENSHOT_CAPTURE_ATTEMPTS"] = int(result["SCREENSHOT_CAPTURE_ATTEMPTS"])
    if "SCREENSHOT_RETRY_DELAY_S" in result:
        result["SCREENSHOT_RETRY_DELAY_S"] = float(result["SCREENSHOT_RETRY_DELAY_S"])
    return result


def normalize_user_settings(overrides: dict) -> dict:
    """Migrate feature settings and remove obsolete Lootbug bonus selection settings."""
    if not isinstance(overrides, dict):
        raise ValueError("settings: expected object")
    for section, values in overrides.items():
        if not isinstance(values, dict):
            raise ValueError(f"settings.{section}: expected object")
    result = migrate_founders_settings(overrides)
    if "detect_level" in result:
        level = dict(result["detect_level"])
        if "DETECT_LEVEL_ENABLED" in level:
            startup = dict(result.get("startup_defaults", {}))
            # Preserve the old effective precedence once, then expose one switch.
            startup["detect_level_enabled"] = level.pop("DETECT_LEVEL_ENABLED")
            result["startup_defaults"] = startup
        result["detect_level"] = level
    if "freebies" in result:
        freebies = dict(result["freebies"])
        if "FREEBIES_CHECK_INTERVAL_S" in freebies:
            freebies.setdefault("FREEBIES_CHECK_INTERVAL_S_FIRST",
                                freebies.pop("FREEBIES_CHECK_INTERVAL_S"))
        result["freebies"] = freebies
    if "screenshot_capture" in result:
        result["screenshot_capture"] = validate_screenshot_settings(result["screenshot_capture"])
    if "lootbug" in result:
        lootbug = dict(result["lootbug"])
        for key in (
            "LOOTBUG_BUY_GEM_UPGRADES_ENABLED", "LOOTBUG_BONUS_DETECT_ROI",
            "LOOTBUG_BONUS_DOUBLE_CLICK_DELAY_S", "LOOTBUG_BONUS_TEMPLATE_GLOB",
            "LOOTBUG_BONUS_TEMPLATE", "LOOTBUG_CLOSE_ROI", "LOOTBUG_CLOSE_TEMPLATE",
        ):
            lootbug.pop(key, None)
        for key, old, new in (
            ("LOOTBUG_BONUS_BUY_ROI", (540, 846, 695, 914), (310, 370, 505, 672)),
        ):
            if isinstance(lootbug.get(key), (list, tuple)) and tuple(lootbug[key]) == old:
                lootbug[key] = list(new)
        result["lootbug"] = lootbug
    if "startup_defaults" in result:
        startup = dict(result["startup_defaults"])
        startup.pop("lootbug_buy_bonus", None)
        result["startup_defaults"] = startup
    return validate_settings(result)


def load_user_settings(base_dir: Path) -> dict:
    p = base_dir / "config" / "user_settings.json"
    if not p.exists():
        return {}
    try:
        return normalize_user_settings(read_json(p))
    except (OSError, ValueError, TypeError) as exc:
        warnings.warn(f"Cannot load user settings; using defaults: {exc}", RuntimeWarning)
        return {}


def apply_overrides_to_settings(settings_globals: dict, overrides: dict):
    """Apply user_settings.json overrides to settings globals."""
    overrides = normalize_user_settings(overrides)
    for key, value in overrides.get("tapping", {}).items():
        settings_globals[key] = value
    capture = overrides.get("screenshot_capture", {})
    for key in ("SCREENSHOT_CAPTURE_ATTEMPTS", "SCREENSHOT_RETRY_DELAY_S",
                "SCREENSHOT_LOG_LEVEL", "SCREENSHOT_LOG_CACHE_HITS"):
        if key in capture:
            settings_globals[key] = capture[key]
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
        "FREEBIES_CHECK_INTERVAL_S_FIRST", "FREEBIES_CHECK_INTERVAL_S_SLOW",
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
        "LOOTBUG_INTERVAL_VARIANCE_PCT",
        "LOOTBUG_BUSY_RETRY_S",
        "LOOTBUG_DETECT_ROI",
        "LOOTBUG_MATCH_THRESHOLD",
        "LOOTBUG_SCREEN_REUSE_AGE_S",
        "LOOTBUG_TAP_JITTER_PX",
        "LOOTBUG_POST_CLICK_DELAY_S",
        "LOOTBUG_LOG_LEVEL",
        "LOOTBUG_LOG_LEVEL_DETECT",
        "LOOTBUG_LOG_LEVEL_CLICK",
        "LOOTBUG_LOG_LEVEL_BUSY",
        "LOOTBUG_LOG_LEVEL_BONUS",
        "LOOTBUG_BONUS_BUY_TEMPLATE",
        "LOOTBUG_BONUS_BUY_ROI",
        "LOOTBUG_BONUS_TAP_JITTER_PX",
        "LOOTBUG_BUY_RETRY_S",
        "LOOTBUG_BUY_MAX_ATTEMPTS", "LOOTBUG_FOUNDERS_LOOKAHEAD_S",
    )
    _lootbug_roi_keys = ("LOOTBUG_DETECT_ROI", "LOOTBUG_BONUS_BUY_ROI")
    for k in _lootbug_keys:
        if k in lootbug:
            v = lootbug[k]
            if k in _lootbug_roi_keys and isinstance(v, list):
                try:
                    v = tuple(int(x) for x in v)
                except Exception:
                    continue
            settings_globals[k] = v

    founders = overrides.get("founders", {})
    for key in (
        "FOUNDERS_CHECK_INTERVAL_S_FIRST", "FOUNDERS_CHECK_INTERVAL_S_SLOW",
        "FOUNDERS_BUSY_RETRY_S",
        "FOUNDERS_MAX_CLAIMS_PER_CYCLE",
        "FOUNDERS_DETECT_ROI", "FOUNDERS_TEMPLATE", "FOUNDERS_MATCH_THRESHOLD",
        "FOUNDERS_SCREEN_REUSE_AGE_S", "FOUNDERS_TAP_JITTER_PX",
        "FOUNDERS_LOG_LEVEL", "FOUNDERS_LOG_LEVEL_CLICK", "FOUNDERS_LOG_LEVEL_BUSY",
    ):
        if key in founders:
            value = founders[key]
            if key == "FOUNDERS_DETECT_ROI" and isinstance(value, list):
                value = tuple(int(x) for x in value)
            settings_globals[key] = value

    sd = overrides.get("startup_defaults", {})
    for key, target in (("gem_statistics_enabled", "GEM_STATISTICS_ENABLED_DEFAULT"),
                        ("screenshot_visible", "SCREENSHOT_VISIBLE_DEFAULT")):
        if key in sd:
            settings_globals[target] = sd[key]
    for key, value in overrides.get("notices", {}).items():
        settings_globals[key] = tuple(int(c) for c in value) if key == "NOTICES_DETECT_ROI" else value
    if "NOTICES_ENABLED" in sd:
        settings_globals["NOTICES_ENABLED"] = sd["NOTICES_ENABLED"]
    if "FOUNDERS_ENABLED" in sd:
        settings_globals["FOUNDERS_ENABLED"] = bool(sd["FOUNDERS_ENABLED"])
    if "freebies_enabled" in sd:
        settings_globals["FREEBIES_ENABLED_DEFAULT"] = bool(sd["freebies_enabled"])
    if "lootbug_enabled" in sd:
        settings_globals["LOOTBUG_ENABLED_DEFAULT"] = bool(sd["lootbug_enabled"])
    if "workflows_enabled" in sd:
        settings_globals["WORKFLOWS_ENABLED_DEFAULT"] = bool(sd["workflows_enabled"])
    if "detect_level_enabled" in sd:
        settings_globals["DETECT_LEVEL_ENABLED"] = bool(sd["detect_level_enabled"])

    dl = overrides.get("detect_level", {})
    _dl_keys = (
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
