"""Side-effect-free validation shared by the API and local config loaders.

No imports of settings, features or the web app: validation must never start ADB.
Optional workflow fields keep the editor's existing null/blank defaults.
"""
import math
import copy
from pathlib import PurePosixPath


def _error(path, message):
    raise ValueError(f"{path}: {message}")


def number(low=0, high=None, integer=False):
    def check(value, path):
        try:
            finite = math.isfinite(value)
        except (TypeError, OverflowError):
            finite = False
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not finite or value < low
                or (high is not None and value > high)
                or (integer and int(value) != value)):
            _error(path, f"expected {'integer' if integer else 'finite number'} >= {low}"
                   + (f" and <= {high}" if high is not None else ""))
    return check


def boolean(value, path):
    if not isinstance(value, bool):
        _error(path, "expected true or false")


def text(value, path):
    if not isinstance(value, str):
        _error(path, "expected string")


def choice(*values):
    def check(value, path):
        if value not in values or not isinstance(value, str):
            _error(path, "expected " + "/".join(values))
    return check


def roi(value, path):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        _error(path, "expected four coordinates [x1,y1,x2,y2]")
    for i, coordinate in enumerate(value):
        number(integer=True)(coordinate, f"{path}[{i}]")
    if value[0] >= value[2] or value[1] >= value[3]:
        _error(path, "requires x1 < x2 and y1 < y2")


def relative_path(value, path):
    text(value, path)
    normalized = value.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if not parts or normalized.startswith("/") or ":" in normalized or ".." in parts or "\x00" in value:
        _error(path, "expected a relative path within the image directory")


def filenames(value, path):
    if not isinstance(value, list):
        _error(path, "expected list of PNG filenames")
    for i, name in enumerate(value):
        relative_path(name, f"{path}[{i}]")
        if "/" in name or "\\" in name or not name.lower().endswith(".png"):
            _error(f"{path}[{i}]", "expected PNG filename without directories")


def ports(value, path):
    if not isinstance(value, list):
        _error(path, "expected list of ports")
    for i, port in enumerate(value):
        number(1, 65535, integer=True)(port, f"{path}[{i}]")


def optional(check):
    def validate(value, path):
        if value is not None and value != "":
            check(value, path)
    return validate


def optional_roi(value, path):
    # The editor serializes an empty ROI/area as [], meaning full/default area.
    if value != []:
        optional(roi)(value, path)


def fields(value, schema, path):
    if not isinstance(value, dict):
        _error(path, "expected object")
    for key, item in value.items():
        if key not in schema:
            _error(f"{path}.{key}", "unknown field")
        schema[key](item, f"{path}.{key}")


N = number()
I = number(integer=True)
POS = number(0.001)
UNIT = number(0, 1)
PERCENT = number(0, 100)
LOG = choice("FULL", "TXT", "UI")


def _schema(**groups):
    result = {}
    for rule, keys in groups.items():
        result.update({key: globals()[rule] for key in keys.split()})
    return result


SETTINGS = {
    "tapping": {"TAP_HUMANIZE_ENABLED": boolean,
                "TAP_HOLD_MS": number(0, 2000, integer=True),
                "TAP_HOLD_VARIANCE_PCT": PERCENT,
                "TAP_JITTER_PX": number(0, 100, integer=True)},
    "adb": {"DEVICE": text, "ADB_AUTO_CONNECT": boolean, "ADB_CONNECT_TIMEOUT": POS,
            "ADB_MAX_RETRIES": number(1, integer=True), "ADB_SCAN_PORTS": ports},
    "startup_defaults": {key: boolean for key in (
        "FOUNDERS_ENABLED", "NOTICES_ENABLED", "freebies_enabled", "lootbug_enabled", "workflows_enabled",
        "detect_level_enabled", "gem_statistics_enabled", "screenshot_visible")},
    "running_detection": {"RUNNING_ROI": roi, "RUNNING_MATCH_THRESHOLD": UNIT,
                          "RUNNING_CHECK_CACHE_AGE_S": N, "RUNNING_LOG_LEVEL": LOG},
    "freebies": _schema(POS="FREEBIES_CHECK_INTERVAL_S_FIRST FREEBIES_CHECK_INTERVAL_S_SLOW",
        N="FREEBIES_POST_OPEN_DELAY_S FREEBIES_POST_CLAIM_DELAY_S",
        I="FREEBIES_SCROLL_ATTEMPTS FREEBIES_SCROLL_TO_TOP_COUNT FREEBIES_TAP_JITTER_PX FREEBIES_DIAMONDS_PER_CLAIM",
        roi="FREEBIES_DETECT_ROI FREEBIES_CLAIM_ROI FREEBIES_CLOSE_ROI",
        UNIT="FREEBIES_MATCH_THRESHOLD", LOG="FREEBIES_LOG_LEVEL FREEBIES_LOG_LEVEL_CLAIMED"),
    "lootbug": _schema(POS="LOOTBUG_CHECK_INTERVAL_S LOOTBUG_BUSY_RETRY_S LOOTBUG_BUY_RETRY_S",
        N="LOOTBUG_SCREEN_REUSE_AGE_S LOOTBUG_POST_CLICK_DELAY_S LOOTBUG_FOUNDERS_LOOKAHEAD_S",
        I="LOOTBUG_TAP_JITTER_PX LOOTBUG_BONUS_TAP_JITTER_PX",
        roi="LOOTBUG_DETECT_ROI LOOTBUG_BONUS_BUY_ROI", UNIT="LOOTBUG_MATCH_THRESHOLD",
        PERCENT="LOOTBUG_INTERVAL_VARIANCE_PCT", relative_path="LOOTBUG_BONUS_BUY_TEMPLATE",
        LOG="LOOTBUG_LOG_LEVEL LOOTBUG_LOG_LEVEL_DETECT LOOTBUG_LOG_LEVEL_CLICK LOOTBUG_LOG_LEVEL_BUSY LOOTBUG_LOG_LEVEL_BONUS")
        | {"LOOTBUG_BUY_MAX_ATTEMPTS": number(1, 100, integer=True)},
    "founders": _schema(POS="FOUNDERS_CHECK_INTERVAL_S_FIRST FOUNDERS_CHECK_INTERVAL_S_SLOW FOUNDERS_BUSY_RETRY_S",
        N="FOUNDERS_SCREEN_REUSE_AGE_S", I="FOUNDERS_TAP_JITTER_PX",
        roi="FOUNDERS_DETECT_ROI", relative_path="FOUNDERS_TEMPLATE", UNIT="FOUNDERS_MATCH_THRESHOLD",
        LOG="FOUNDERS_LOG_LEVEL FOUNDERS_LOG_LEVEL_CLICK FOUNDERS_LOG_LEVEL_BUSY")
        | {"FOUNDERS_MAX_CLAIMS_PER_CYCLE": number(1, 100, integer=True)},
    "notices": _schema(POS="NOTICES_CHECK_INTERVAL_S NOTICES_RETRY_S",
        PERCENT="NOTICES_INTERVAL_VARIANCE_PCT", N="NOTICES_SCREEN_REUSE_AGE_S NOTICES_POST_CLICK_DELAY_S",
        roi="NOTICES_DETECT_ROI", relative_path="NOTICES_TEMPLATE_GLOB",
        UNIT="NOTICES_MATCH_THRESHOLD", I="NOTICES_TAP_X NOTICES_TAP_Y NOTICES_TAP_JITTER_PX",
        LOG="NOTICES_LOG_LEVEL") | {"NOTICES_MAX_PER_CYCLE": number(1, 100, integer=True),
                                   "NOTICES_MAX_ARCHIVE_MB": number(1, 10000)},
    "detect_level": _schema(boolean="DETECT_LEVEL_ENABLED", roi="DETECT_LEVEL_ROI",
        POS="DETECT_LEVEL_INTERVAL_S", UNIT="DETECT_LEVEL_THRESHOLD",
        N="DETECT_LEVEL_CACHE_MAX_AGE_S", I="DETECT_LEVEL_NMS_MIN_DX_PX", LOG="DETECT_LEVEL_LOG_LEVEL"),
    "workflows": _schema(PERCENT="WF_INTERVAL_VARIANCE_PCT", I="WORKFLOWS_TAP_JITTER_PX",
        N="WORKFLOWS_SCREEN_REUSE_AGE_S", POS="WORKFLOWS_BUSY_RETRY_S",
        LOG="WORKFLOWS_LOG_LEVEL WORKFLOWS_LOG_LEVEL_STEP WORKFLOWS_LOG_LEVEL_BUSY"),
    "screenshot_viewer": {"SCREENSHOT_VIEWER_FILES": filenames},
    "screenshot_capture": {"SCREENSHOT_CAPTURE_ATTEMPTS": number(1, 5, integer=True),
        "SCREENSHOT_RETRY_DELAY_S": number(0, 10), "SCREENSHOT_LOG_LEVEL": LOG,
        "SCREENSHOT_LOG_CACHE_HITS": boolean},
    "scroll": _schema(roi="SCROLL_DEFAULT_AREA", LOG="SCROLL_LOG_LEVEL",
        I="SCROLL_EDGE_PADDING_PX"),
}
SETTINGS["scroll"]["SCROLL_DEFAULT_SPEED"] = choice("slow", "mid", "fast")
for _speed in ("SLOW", "MID", "FAST"):
    SETTINGS["scroll"][f"SCROLL_DURATION_{_speed}_MS"] = number(1, integer=True)
    SETTINGS["scroll"][f"SCROLL_DISTANCE_{_speed}_PX"] = number(1, integer=True)


def validate_settings(data):
    if not isinstance(data, dict):
        _error("settings", "expected object")
    for section, values in data.items():
        if section not in SETTINGS:
            _error(f"settings.{section}", "unknown section")
        fields(values, SETTINGS[section], f"settings.{section}")
    scroll = data.get("scroll", {})
    if "SCROLL_DEFAULT_AREA" in scroll and "SCROLL_EDGE_PADDING_PX" in scroll:
        x1, y1, x2, y2 = scroll["SCROLL_DEFAULT_AREA"]
        if 2 * scroll["SCROLL_EDGE_PADDING_PX"] >= min(x2 - x1, y2 - y1):
            _error("settings.scroll.SCROLL_EDGE_PADDING_PX", "padding must fit inside the scroll area")
    return data


COMMON = {"type": text, "_disabled": boolean, "note": text, "sleep_after": N}
REPEAT = {"count": optional(number(1, 10000, integer=True)), "count_interval_s": optional(N)}
TAP = {"jitter": I, "hold_ms": optional(I)}
MATCH = {"template": text, "roi": optional_roi, "threshold": UNIT,
         "offset_x": number(-100000, integer=True), "offset_y": number(-100000, integer=True),
         "optional": boolean, "use_prev_screenshot": boolean,
         "clicks": optional(number(1, 10000, integer=True)), "click_interval_s": optional(N), **TAP}
STEPS = {
    "tap_roi": {"roi": roi, "jitter": I, **REPEAT},
    "tap_xy": {"x": I, "y": I, **TAP, **REPEAT},
    "swipe": {"direction": choice("up", "down"), "speed": choice("slow", "mid", "fast"),
              "area": optional_roi, "duration_ms": optional(number(1, integer=True)),
              "distance_px": optional(number(1, integer=True)), **REPEAT},
    "click_template": MATCH,
    "click_rotating": {**MATCH, "rotations": optional(number(1, 3600, integer=True)),
                       "mask": choice("circle", "none"), "downscale": optional(number(1, integer=True)),
                       "log_mode": choice("both", "hit_only", "miss_only", "none")},
    "wait": {"seconds": N},
    "rainbow_check": {"roi": roi, "sat_min": optional(number(0, 255, integer=True)),
        "val_min": optional(number(0, 255, integer=True)), "min_sat_pixels": optional(I),
        "min_hue_buckets": optional(number(1, 180, integer=True)),
        "min_pixels_per_bucket": optional(I), "hue_buckets": optional(number(1, 180, integer=True)),
        "min_hue_entropy": optional(N), "optional": boolean, "use_prev_screenshot": boolean},
    "call_workflow": {"target": text},
    "hold_and_wiggle": {"roi": roi, "duration_s": optional(POS),
        "step_ms": optional(number(30, integer=True)), "max_step_px": optional(number(10, integer=True))},
    "if": {"on_missing_template": choice("false", "fail_wf"),
           "branches": lambda v, p: None, "else_steps": lambda v, p: None},
}
WF = {"name": text, "description": text, "order": number(-100000, integer=True),
      "enabled_default": boolean, "inactive": boolean, "ignore_action_lock": boolean,
      "interval_s": POS, "interval_variance_pct": optional(PERCENT),
      "log_level": optional(LOG), "log_level_step": optional(LOG), "log_level_busy": optional(LOG),
      "steps": lambda v, p: None}
CONDITION = {"kind": choice("template_visible", "template_not_visible", "level_eq", "level_gte",
    "level_lte", "last_step_ok", "last_step_failed"), "template": text,
    "roi": optional_roi, "threshold": UNIT, "value": optional(number(1, 999, integer=True))}


def _validate_steps(steps, path, definitions, depth=0, inactive=False):
    if not isinstance(steps, list):
        _error(path, "expected list of steps")
    for i, step in enumerate(steps):
        sp = f"{path}[{i}]"
        if (not isinstance(step, dict) or not isinstance(step.get("type"), str)
                or step["type"] not in STEPS):
            _error(sp, "unknown or missing step type")
        kind = step["type"]
        if kind == "swipe" and step.get("area") == [0]:
            # Older editor versions encoded a blank area as [0]; runtime used
            # the default area. Preserve that behavior without accepting other
            # malformed rectangles.
            step["area"] = None
        fields(step, {**COMMON, **STEPS[kind]}, sp)
        disabled = inactive or step.get("_disabled", False)
        if not disabled:
            for key in {"tap_roi": ("roi",), "tap_xy": ("x", "y"),
                        "rainbow_check": ("roi",), "hold_and_wiggle": ("roi",),
                        "call_workflow": ("target",),
                        "click_template": ("template",), "click_rotating": ("template",)}.get(kind, ()):
                if step.get(key) is None or step.get(key) == "":
                    _error(f"{sp}.{key}", "required for enabled step")
            if kind == "call_workflow" and step["target"] not in definitions:
                _error(f"{sp}.target", "unknown workflow")
        if kind in ("click_template", "click_rotating") and step.get("template"):
            relative_path(step["template"], f"{sp}.template")
        if kind == "rainbow_check":
            buckets = step.get("hue_buckets") or 12
            minimum = step.get("min_hue_buckets") if step.get("min_hue_buckets") not in (None, "") else 5
            if minimum > buckets:
                _error(f"{sp}.min_hue_buckets", "must not exceed hue_buckets")
        if kind == "if":
            if depth >= 1:
                _error(sp, "nested if blocks are unsupported")
            branches = step.get("branches", [])
            if not isinstance(branches, list):
                _error(f"{sp}.branches", "expected list")
            for bi, branch in enumerate(branches):
                bp = f"{sp}.branches[{bi}]"
                fields(branch, {"condition": lambda v, p: fields(v, CONDITION, p),
                                "steps": lambda v, p: None}, bp)
                cond = branch.get("condition", {})
                if "kind" not in cond:
                    _error(f"{bp}.condition.kind", "required")
                if not disabled:
                    ck = cond["kind"]
                    if ck.startswith("template_"):
                        relative_path(cond.get("template", ""), f"{bp}.condition.template")
                    if ck.startswith("level_"):
                        number(1, 999, integer=True)(cond.get("value"), f"{bp}.condition.value")
                _validate_steps(branch.get("steps", []), f"{bp}.steps", definitions, depth + 1, disabled)
            otherwise = step.get("else_steps")
            _validate_steps([] if otherwise is None else otherwise,
                            f"{sp}.else_steps", definitions, depth + 1, disabled)


def validate_workflows(data):
    if not isinstance(data, dict):
        _error("workflows", "expected object keyed by workflow slug")
    data = copy.deepcopy(data)
    for slug, workflow in data.items():
        if not isinstance(slug, str) or not slug.strip():
            _error("workflows", "workflow slug must be a nonempty string")
        path = f"workflows.{slug}"
        fields(workflow, WF, path)
        if workflow.get("interval_variance_pct") == "":
            workflow["interval_variance_pct"] = None
        _validate_steps(workflow.get("steps", []), f"{path}.steps", data,
                        inactive=workflow.get("inactive", False))
    return data
