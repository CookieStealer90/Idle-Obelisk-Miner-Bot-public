# web/config_api.py - Configuration API routes
"""
/api/config/* endpoints for settings and workflows.
"""
from pathlib import Path

from flask import Blueprint, request, jsonify
from config.user_overrides import normalize_user_settings
from config.validation import validate_workflows
from config.json_store import atomic_write_json, read_json
from werkzeug.exceptions import BadRequest, UnsupportedMediaType

BASE_DIR = Path(__file__).resolve().parent.parent

config_bp = Blueprint("config_api", __name__)


def _push_log(msg):
    from web.app import push_log
    push_log(msg)


@config_bp.route("/api/config/settings", methods=["GET"])
def settings_get():
    """Return editable settings as JSON."""
    try:
        override_path = BASE_DIR / "config" / "user_settings.json"
        if override_path.exists():
            overrides = normalize_user_settings(read_json(override_path))
        else:
            overrides = {}

        from config import settings as s
        defaults = {
            "tapping": {
                "TAP_HUMANIZE_ENABLED": s.TAP_HUMANIZE_ENABLED,
                "TAP_HOLD_MS": s.TAP_HOLD_MS,
                "TAP_HOLD_VARIANCE_PCT": s.TAP_HOLD_VARIANCE_PCT,
                "TAP_JITTER_PX": s.TAP_JITTER_PX,
            },
            "adb": {
                "DEVICE": s.DEVICE,
                "ADB_AUTO_CONNECT": s.ADB_AUTO_CONNECT,
                "ADB_CONNECT_TIMEOUT": s.ADB_CONNECT_TIMEOUT,
                "ADB_MAX_RETRIES": s.ADB_MAX_RETRIES,
                "ADB_SCAN_PORTS": s.ADB_SCAN_PORTS,
            },
            "startup_defaults": {
                "gem_statistics_enabled": s.GEM_STATISTICS_ENABLED_DEFAULT,
                "screenshot_visible": s.SCREENSHOT_VISIBLE_DEFAULT,
                "freebies_enabled": getattr(s, "FREEBIES_ENABLED_DEFAULT", True),
                "lootbug_enabled": getattr(s, "LOOTBUG_ENABLED_DEFAULT", False),
                "FOUNDERS_ENABLED": s.FOUNDERS_ENABLED,
                "NOTICES_ENABLED": s.NOTICES_ENABLED,
                "workflows_enabled": getattr(s, "WORKFLOWS_ENABLED_DEFAULT", False),
                "detect_level_enabled": getattr(s, "DETECT_LEVEL_ENABLED", True),
            },
            "detect_level": {
                "DETECT_LEVEL_ROI": list(getattr(s, "DETECT_LEVEL_ROI", (0, 61, 60, 89))),
                "DETECT_LEVEL_INTERVAL_S": getattr(s, "DETECT_LEVEL_INTERVAL_S", 60.0),
                "DETECT_LEVEL_THRESHOLD": getattr(s, "DETECT_LEVEL_THRESHOLD", 0.85),
                "DETECT_LEVEL_CACHE_MAX_AGE_S": getattr(s, "DETECT_LEVEL_CACHE_MAX_AGE_S", 15.0),
                "DETECT_LEVEL_NMS_MIN_DX_PX": getattr(s, "DETECT_LEVEL_NMS_MIN_DX_PX", 8),
                "DETECT_LEVEL_LOG_LEVEL": getattr(s, "DETECT_LEVEL_LOG_LEVEL", "FULL"),
            },
            "workflows": {
                "WF_INTERVAL_VARIANCE_PCT": getattr(s, "WF_INTERVAL_VARIANCE_PCT", 15.0),
                "WORKFLOWS_TAP_JITTER_PX": getattr(s, "WORKFLOWS_TAP_JITTER_PX", 4),
                "WORKFLOWS_SCREEN_REUSE_AGE_S": getattr(s, "WORKFLOWS_SCREEN_REUSE_AGE_S", 2.0),
                "WORKFLOWS_BUSY_RETRY_S": getattr(s, "WORKFLOWS_BUSY_RETRY_S", 10.0),
                "WORKFLOWS_LOG_LEVEL": getattr(s, "WORKFLOWS_LOG_LEVEL", "FULL"),
                "WORKFLOWS_LOG_LEVEL_STEP": getattr(s, "WORKFLOWS_LOG_LEVEL_STEP", "FULL"),
                "WORKFLOWS_LOG_LEVEL_BUSY": getattr(s, "WORKFLOWS_LOG_LEVEL_BUSY", "FULL"),
            },
            "running_detection": {
                "RUNNING_ROI": list(s.RUNNING_ROI),
                "RUNNING_MATCH_THRESHOLD": s.RUNNING_MATCH_THRESHOLD,
                "RUNNING_CHECK_CACHE_AGE_S": s.RUNNING_CHECK_CACHE_AGE_S,
                "RUNNING_LOG_LEVEL": s.RUNNING_LOG_LEVEL,
            },
            "freebies": {
                "FREEBIES_CHECK_INTERVAL_S_FIRST": s.FREEBIES_CHECK_INTERVAL_S_FIRST,
                "FREEBIES_CHECK_INTERVAL_S_SLOW": s.FREEBIES_CHECK_INTERVAL_S_SLOW,
                "FREEBIES_DETECT_ROI": list(s.FREEBIES_DETECT_ROI),
                "FREEBIES_CLAIM_ROI": list(s.FREEBIES_CLAIM_ROI),
                "FREEBIES_MATCH_THRESHOLD": s.FREEBIES_MATCH_THRESHOLD,
                "FREEBIES_SCROLL_ATTEMPTS": s.FREEBIES_SCROLL_ATTEMPTS,
                "FREEBIES_SCROLL_TO_TOP_COUNT": s.FREEBIES_SCROLL_TO_TOP_COUNT,
                "FREEBIES_POST_OPEN_DELAY_S": s.FREEBIES_POST_OPEN_DELAY_S,
                "FREEBIES_TAP_JITTER_PX": s.FREEBIES_TAP_JITTER_PX,
                "FREEBIES_DIAMONDS_PER_CLAIM": s.FREEBIES_DIAMONDS_PER_CLAIM,
                "FREEBIES_LOG_LEVEL": s.FREEBIES_LOG_LEVEL,
                "FREEBIES_LOG_LEVEL_CLAIMED": s.FREEBIES_LOG_LEVEL_CLAIMED,
                "FREEBIES_CLOSE_ROI": list(s.FREEBIES_CLOSE_ROI),
                "FREEBIES_POST_CLAIM_DELAY_S": s.FREEBIES_POST_CLAIM_DELAY_S,
            },
            "notices": {key: getattr(s, key) for key in s.NOTICE_DEFAULTS},
            "founders": {
                "FOUNDERS_CHECK_INTERVAL_S_FIRST": s.FOUNDERS_CHECK_INTERVAL_S_FIRST,
                "FOUNDERS_CHECK_INTERVAL_S_SLOW": s.FOUNDERS_CHECK_INTERVAL_S_SLOW,
                "FOUNDERS_BUSY_RETRY_S": s.FOUNDERS_BUSY_RETRY_S,
                "FOUNDERS_MAX_CLAIMS_PER_CYCLE": s.FOUNDERS_MAX_CLAIMS_PER_CYCLE,
                "FOUNDERS_DETECT_ROI": list(s.FOUNDERS_DETECT_ROI),
                "FOUNDERS_TEMPLATE": s.FOUNDERS_TEMPLATE,
                "FOUNDERS_MATCH_THRESHOLD": s.FOUNDERS_MATCH_THRESHOLD,
                "FOUNDERS_SCREEN_REUSE_AGE_S": s.FOUNDERS_SCREEN_REUSE_AGE_S,
                "FOUNDERS_TAP_JITTER_PX": s.FOUNDERS_TAP_JITTER_PX,
                "FOUNDERS_LOG_LEVEL": s.FOUNDERS_LOG_LEVEL,
                "FOUNDERS_LOG_LEVEL_CLICK": s.FOUNDERS_LOG_LEVEL_CLICK,
                "FOUNDERS_LOG_LEVEL_BUSY": s.FOUNDERS_LOG_LEVEL_BUSY,
            },
            "lootbug": {
                "LOOTBUG_CHECK_INTERVAL_S": s.LOOTBUG_CHECK_INTERVAL_S,
                "LOOTBUG_INTERVAL_VARIANCE_PCT": s.LOOTBUG_INTERVAL_VARIANCE_PCT,
                "LOOTBUG_BUSY_RETRY_S": s.LOOTBUG_BUSY_RETRY_S,
                "LOOTBUG_DETECT_ROI": list(s.LOOTBUG_DETECT_ROI),
                "LOOTBUG_MATCH_THRESHOLD": s.LOOTBUG_MATCH_THRESHOLD,
                "LOOTBUG_SCREEN_REUSE_AGE_S": s.LOOTBUG_SCREEN_REUSE_AGE_S,
                "LOOTBUG_TAP_JITTER_PX": s.LOOTBUG_TAP_JITTER_PX,
                "LOOTBUG_POST_CLICK_DELAY_S": s.LOOTBUG_POST_CLICK_DELAY_S,
                "LOOTBUG_BUY_RETRY_S": s.LOOTBUG_BUY_RETRY_S,
                "LOOTBUG_BUY_MAX_ATTEMPTS": s.LOOTBUG_BUY_MAX_ATTEMPTS,
                "LOOTBUG_TRIGGER_FOUNDERS_ON_BUY_FAILURE": s.LOOTBUG_TRIGGER_FOUNDERS_ON_BUY_FAILURE,
                "LOOTBUG_FOUNDERS_LOOKAHEAD_S": s.LOOTBUG_FOUNDERS_LOOKAHEAD_S,
                "LOOTBUG_BONUS_BUY_TEMPLATE": s.LOOTBUG_BONUS_BUY_TEMPLATE,
                "LOOTBUG_BONUS_BUY_ROI": list(s.LOOTBUG_BONUS_BUY_ROI),
                "LOOTBUG_BONUS_TAP_JITTER_PX": getattr(s, "LOOTBUG_BONUS_TAP_JITTER_PX", 4),
                "LOOTBUG_LOG_LEVEL": s.LOOTBUG_LOG_LEVEL,
                "LOOTBUG_LOG_LEVEL_DETECT": s.LOOTBUG_LOG_LEVEL_DETECT,
                "LOOTBUG_LOG_LEVEL_CLICK": s.LOOTBUG_LOG_LEVEL_CLICK,
                "LOOTBUG_LOG_LEVEL_BUSY": s.LOOTBUG_LOG_LEVEL_BUSY,
                "LOOTBUG_LOG_LEVEL_BONUS": getattr(s, "LOOTBUG_LOG_LEVEL_BONUS", "FULL"),
            },
            "screenshot_viewer": {
                "SCREENSHOT_VIEWER_FILES": getattr(s, "SCREENSHOT_VIEWER_FILES", ["game_scr.png", "freebie_scr.png", "lootbug_scr.png"]),
            },
            "screenshot_capture": {
                "SCREENSHOT_CAPTURE_ATTEMPTS": s.SCREENSHOT_CAPTURE_ATTEMPTS,
                "SCREENSHOT_RETRY_DELAY_S": s.SCREENSHOT_RETRY_DELAY_S,
                "SCREENSHOT_LOG_LEVEL": s.SCREENSHOT_LOG_LEVEL,
                "SCREENSHOT_LOG_CACHE_HITS": s.SCREENSHOT_LOG_CACHE_HITS,
            },
            "scroll": {
                "SCROLL_DEFAULT_AREA": list(s.SCROLL_DEFAULT_AREA),
                "SCROLL_DEFAULT_SPEED": s.SCROLL_DEFAULT_SPEED,
                "SCROLL_DURATION_SLOW_MS": s.SCROLL_DURATION_SLOW_MS,
                "SCROLL_DURATION_MID_MS": s.SCROLL_DURATION_MID_MS,
                "SCROLL_DURATION_FAST_MS": s.SCROLL_DURATION_FAST_MS,
                "SCROLL_DISTANCE_SLOW_PX": s.SCROLL_DISTANCE_SLOW_PX,
                "SCROLL_DISTANCE_MID_PX": s.SCROLL_DISTANCE_MID_PX,
                "SCROLL_DISTANCE_FAST_PX": s.SCROLL_DISTANCE_FAST_PX,
                "SCROLL_EDGE_PADDING_PX": s.SCROLL_EDGE_PADDING_PX,
                "SCROLL_LOG_LEVEL": s.SCROLL_LOG_LEVEL,
            },
        }

        result = defaults.copy()
        for section, vals in overrides.items():
            if section in result and isinstance(result[section], dict):
                result[section].update(vals)
            else:
                result[section] = vals

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@config_bp.route("/api/config/settings", methods=["POST"])
def settings_save():
    """Save settings to user_settings.json."""
    try:
        data = normalize_user_settings(request.json)
        override_path = BASE_DIR / "config" / "user_settings.json"
        atomic_write_json(override_path, data)
        _push_log("[CONFIG] Settings saved - Restart the bot to apply")
        return jsonify({"ok": True, "apply": "restart"})
    except (TypeError, ValueError, BadRequest, UnsupportedMediaType) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============ WORKFLOWS ============

@config_bp.route("/api/config/workflows/full", methods=["GET"])
def workflows_get():
    """Return full workflow definitions."""
    try:
        import config.config_workflows as workflow_config
        from config.app_state import workflows_lock
        with workflows_lock:
            return jsonify(workflow_config.WORKFLOWS)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@config_bp.route("/api/config/workflows/full", methods=["POST"])
def workflows_save():
    """Save workflow definitions to user_workflows.json."""
    try:
        data = validate_workflows(request.json)
        override_path = BASE_DIR / "config" / "user_workflows.json"
        atomic_write_json(override_path, data)
        _push_log("[CONFIG] Workflows saved - Use Reload to apply")
        return jsonify({"ok": True, "apply": "reload"})
    except (TypeError, ValueError, BadRequest, UnsupportedMediaType) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@config_bp.route("/api/config/templates", methods=["GET"])
def templates_list():
    """Return list of workflow template image filenames (PNG/JPG/BMP) found
    recursively under images/workflows/. Paths are returned relative to that
    directory (without extension) so the editor can hand them to
    click_template steps verbatim."""
    try:
        from config.config_workflows import WORKFLOW_IMG_DIR
        tpls = []
        if WORKFLOW_IMG_DIR.is_dir():
            for f in sorted(WORKFLOW_IMG_DIR.rglob("*")):
                if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".bmp"):
                    rel = f.relative_to(WORKFLOW_IMG_DIR).with_suffix("").as_posix()
                    tpls.append(rel)
        return jsonify(tpls)
    except Exception:
        return jsonify([])


# ============ GEM STATISTICS ============

@config_bp.route("/api/gem_stats/reset", methods=["POST"])
def gem_stats_reset():
    """Reset gem statistics."""
    try:
        from features.gem_statistics import get_gem_statistics
        gs = get_gem_statistics()
        gs.reset()
        _push_log("[STATS] Gem statistics reset")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@config_bp.route("/api/gem_stats/manual_add", methods=["POST"])
def gem_stats_manual_add():
    """Manually add a gem claim to statistics."""
    try:
        from features.gem_statistics import get_gem_statistics
        gem_type = request.json.get("type", "gem")
        gs = get_gem_statistics()
        amount = gs.record_claim(gem_type)
        if amount is None:
            return jsonify({"ok": False, "error": "Freebies inactive"}), 409
        return jsonify({"ok": True, "amount": amount})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
