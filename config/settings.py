# Idle-Obelisk-Miner-Bot - settings.py
# All constants & configuration live here.
# Custom overrides via Web UI are stored in config/user_settings.json

from pathlib import Path

# ========= Paths =========
BASE_DIR = Path(__file__).resolve().parent.parent  # project root
IMG_DIR = BASE_DIR / "images"
TEMP_DIR = BASE_DIR / "temp"

# ========= ADB CONFIGURATION =========
ADB_CANDIDATES = [
    # prio 1 - try to find adb in parent dir
    BASE_DIR.parent / "adb.exe",

    # prio 2 - MuMu standard paths
    Path(r"D:\Program Files\MuMuPlayerGlobal\nx_device\12.0\shell\adb.exe"),
    Path(r"C:\Program Files\MuMuPlayerGlobal\nx_device\12.0\shell\adb.exe"),
    Path(r"C:\Program Files\Netease\MuMuPlayerGlobal\nx_device\12.0\shell\adb.exe"),
    Path(r"C:\Program Files\Netease\MuMuPlayer\nx_device\12.0\shell\adb.exe"),

    # prio 3 - MEmu
    Path(r"C:\Program Files\Microvirt\MEmu\adb.exe"),

    # prio 4 - Nox
    Path(r"C:\Program Files\Nox\bin\adb.exe"),
    Path(r"C:\Program Files (x86)\Nox\bin\adb.exe"),
]

ADB = "adb"  # final fallback = system PATH

for candidate in ADB_CANDIDATES:
    if candidate.exists():
        ADB = str(candidate)
        break

# ========= ADB Device =========
DEVICE = "127.0.0.1:16384"  # MuMu standard

# ========= ADB Auto-Connect =========
ADB_AUTO_CONNECT = True
ADB_SCAN_PORTS = [
    16384, 16416, 16448,    # MuMu 12 (instance 1, 2, 3)
    5555,                   # Generic Android / MuMu default
    7555,                   # MuMu 6
    21503, 21513,           # MEmu (instance 1, 2)
    62001, 62025,           # Nox (instance 1, 2)
]
ADB_CONNECT_TIMEOUT = 5
ADB_MAX_RETRIES = 2

REMOTE_SCREEN = "/sdcard/__scr.png"
LOCAL_SCREEN = str(BASE_DIR / "__scr.png")

# ========= Exception Handling =========
SUPPRESS_EXCEPTIONS = True

# ========= Main Loop Tick =========
MAIN_LOOP_TICK = 1.5  

# ========= Logging =========
LOG_MAX_SIZE_MB = 2
LOG_BACKUP_COUNT = 3

# ========= Tap =========
TAP_JITTER_PX = 4   # default +/- pixel jitter for tap()
TAP_HOLD_MS = 100   # press duration; 0 = use plain `input tap` (often ignored by games)

# ========= Game-running detection (game_state.py) =========
RUNNING_TEMPLATE = "game_running.png"
RUNNING_ROI = (8, 3, 48, 43)
RUNNING_MATCH_THRESHOLD = 0.8
RUNNING_CHECK_CACHE_AGE_S = 15.0   # reuse cached screenshot younger than this
# Slots whose cached PNG may be reused for the running-check if young enough.
# Youngest wins; if none is younger than RUNNING_CHECK_CACHE_AGE_S, a fresh
# game_scr is pulled. All listed slots must be full-device screenshots.
RUNNING_ACCEPT_SLOTS = ["game_scr", "freebie_scr", "lootbug_scr"]
RUNNING_LOG_LEVEL = "TXT"

# ========= Freebies feature =========
FREEBIES_ENABLED_DEFAULT = False
FREEBIES_CHECK_INTERVAL_S = 300.0  # 5 min between cycles

FREEBIES_FULL_TEMPLATE = "freebie/freebie_full.png"
FREEBIES_FULL2_TEMPLATE = "freebie/freebie_full2.png"
FREEBIES_CLAIM_TEMPLATE = "freebie/freebie_claim.png"



# Base-screen ROI where the freebie icon appears
FREEBIES_DETECT_ROI = (713, 1470, 820, 1550)
# Menu-screen ROI in which to search the claim button
FREEBIES_CLAIM_ROI = (645, 107, 835, 1472)

FREEBIES_MATCH_THRESHOLD = 0.8
FREEBIES_SCROLL_ATTEMPTS = 4        # slow-scroll tries after hard-scrolling up
FREEBIES_SCROLL_TO_TOP_COUNT = 6    # fast scrolls used to reach the top
FREEBIES_POST_OPEN_DELAY_S = 1.0    # wait after tapping the icon for the menu
FREEBIES_TAP_JITTER_PX = 4
FREEBIES_DIAMONDS_PER_CLAIM = 28    
FREEBIES_LOG_LEVEL = "TXT"
FREEBIES_LOG_LEVEL_CLAIMED = "FULL"  # log level for "Freebie Claimed +X Diamonds" line

# Post-claim: close the menu
FREEBIES_CLOSE_TEMPLATE = "close_menu.png"
FREEBIES_CLOSE_ROI = (3, 1472, 898, 1547)
FREEBIES_POST_CLAIM_DELAY_S = 1.0   # wait after claim before searching close button

# ========= Lootbug feature =========
# A "Lootbug" can spawn in-game; clicking it grants a temporary buff or gems.
# We don't track the reward — we just detect, click, and dismiss the popup.
LOOTBUG_ENABLED_DEFAULT = False
LOOTBUG_CHECK_INTERVAL_S = 180.0       # 3 min between scans
LOOTBUG_BUSY_RETRY_S = 15.0            # retry sooner if action lock is busy

LOOTBUG_TEMPLATE_GLOB = "Lootbug/lootbug_tpl_*.png"   # ANY match within ROI counts
LOOTBUG_DETECT_ROI = (253, 650, 463, 952)
LOOTBUG_MATCH_THRESHOLD = 0.8

# Screenshot cache: reuse game_scr.png if younger than this; else pull a fresh
# one into the lootbug-owned slot.
LOOTBUG_SCREEN_REUSE_AGE_S = 5.0
LOOTBUG_SHARED_SCREEN_SLOT = "game_scr"   # cache slot to piggy-back on
LOOTBUG_OWN_SCREEN_SLOT = "lootbug_scr"   # slot used when forced fresh pull

LOOTBUG_TAP_JITTER_PX = 4
LOOTBUG_POST_CLICK_DELAY_S = 1.2       # wait between lootbug-tap and close-tap

# Close button (popup that opens after tapping the lootbug)
LOOTBUG_CLOSE_TEMPLATE = "Lootbug/lootbug_close_menu.png"
LOOTBUG_CLOSE_ROI = (395, 987, 503, 1085)

# Optional gem-bonus purchase after lootbug click.
# If enabled AND one of bonus_tpl_*.png is detected in BONUS_DETECT_ROI,
# we double-tap BONUS_BUY_ROI (two taps close the popup as a side-effect —
# no explicit close needed).
LOOTBUG_BUY_GEM_UPGRADES_ENABLED = False
LOOTBUG_BONUS_TEMPLATE_GLOB = "Lootbug/bonus_tpl_*.png"
LOOTBUG_BONUS_DETECT_ROI = (540, 497, 693, 640)
LOOTBUG_BONUS_BUY_ROI = (540, 846, 695, 914)
LOOTBUG_BONUS_TAP_JITTER_PX = 4
LOOTBUG_BONUS_DOUBLE_CLICK_DELAY_S = 0.1

# Per-event log levels — set to FULL while testing, lower later.
LOOTBUG_LOG_LEVEL = "TXT"             # general worker / scan messages
LOOTBUG_LOG_LEVEL_DETECT = "TXT"      # template-match outcomes
LOOTBUG_LOG_LEVEL_CLICK = "FULL"       # actual taps performed
LOOTBUG_LOG_LEVEL_BUSY = "FULL"        # postponed because action lock held
LOOTBUG_LOG_LEVEL_BONUS = "FULL"       # bonus-purchase events

# Founders lootbox sub-feature (only for Founders Bundle owners)
# Checked once per lootbug scan cycle, independently of the regular lootbug.
LOOTBUG_FOUNDERS_ENABLED = False
LOOTBUG_FOUNDERS_DETECT_ROI = (110, 201, 753, 1021)
LOOTBUG_FOUNDERS_TEMPLATE = "Lootbug/founders_bundle_tpl.png"
LOOTBUG_FOUNDERS_LOG_LEVEL = "FULL"    # founders detection + tap events

# ========= Detect Level feature =========
# Scans a small ROI for digit templates (images/level/digit_*_tpl.png),
# composes 1-3 digits left-to-right into an integer (1..999), and publishes
# the result to state.current_level. Used by workflow if-conditions
# (level_eq / level_gte / level_lte).
DETECT_LEVEL_ENABLED = True
DETECT_LEVEL_ROI = (0, 61, 60, 89)
DETECT_LEVEL_INTERVAL_S = 60.0
DETECT_LEVEL_THRESHOLD = 0.78
# Reuse any recent cached screenshot younger than this (from any slot) before
# pulling a fresh one. Falls back to own slot if nothing fresh is available.
DETECT_LEVEL_CACHE_MAX_AGE_S = 15.0
DETECT_LEVEL_OWN_SCREEN_SLOT = "level_scr"
# Slots that may be reused (newest-wins, same convention as RUNNING_ACCEPT_SLOTS).
DETECT_LEVEL_ACCEPT_SLOTS = ["game_scr", "freebie_scr", "lootbug_scr", "wf_scr", "level_scr"]
# NMS: minimum horizontal gap between two detected digit centers, in pixels.
# Prevents two digit templates from "stacking" on the same position.
DETECT_LEVEL_NMS_MIN_DX_PX = 8
DETECT_LEVEL_LOG_LEVEL = "TXT"

# ========= Scrolling =========
# Idle Obelisk Miner requires a DRAG gesture (finger stays down while moving),
# not a flick. We implement this via `adb shell input swipe` with sufficient
# duration — short durations = flick (no scroll in-game), long = drag.

# Default rectangle (x1, y1, x2, y2) used when a scroll call omits the area.
SCROLL_DEFAULT_AREA = (0, 102, 900, 1457)

# Default direction speed if a scroll call omits `speed`.
SCROLL_DEFAULT_SPEED = "mid"     # one of: "slow" | "mid" | "fast"

# Swipe duration per speed preset (milliseconds). Higher = slower / more drag-like.
SCROLL_DURATION_SLOW_MS = 1200
SCROLL_DURATION_MID_MS  = 700
SCROLL_DURATION_FAST_MS = 350

# Travel distance per speed preset (pixels, vertical).
SCROLL_DISTANCE_SLOW_PX = 400
SCROLL_DISTANCE_MID_PX  = 700
SCROLL_DISTANCE_FAST_PX = 1000

# Padding kept from area edges so the gesture doesn't hit the rectangle boundary.
SCROLL_EDGE_PADDING_PX = 20

# Log level for scroll events — "FULL" | "TXT" | "UI"
SCROLL_LOG_LEVEL = "TXT"

# ========= Screenshot Viewer =========
# Filenames to look for in TEMP_DIR; the newest file found wins.
SCREENSHOT_VIEWER_FILES = ["game_scr.png", "freebie_scr.png", "lootbug_scr.png", "wf_scr.png"]

# ========= Workflows feature =========
# Workflows are user-defined step sequences (taps, swipes, template clicks).
# Definitions live in config/config_workflows.py; user overrides land in
# config/user_workflows.json. The scheduler (features/workflows.py) runs them
# on their per-WF interval (with global variance) when the master toggle is ON.
WORKFLOWS_ENABLED_DEFAULT = True        # master "Auto WF" switch on startup

WF_INTERVAL_VARIANCE_PCT = 15.0          # global +/- variance applied to interval

WORKFLOWS_TAP_JITTER_PX = 4              # default jitter for tap_roi/tap_xy
WORKFLOWS_SCREEN_REUSE_AGE_S = 2.0       # click_template: reuse wf_scr.png if younger
WORKFLOWS_OWN_SCREEN_SLOT = "wf_scr"
WORKFLOWS_BUSY_RETRY_S = 10.0            # retry delay when ingame_action_lock held by other feature
WORKFLOWS_MAX_CALL_DEPTH = 5             # max nested call_workflow depth

# Per-event log levels — pro-WF override possible via WF dict
WORKFLOWS_LOG_LEVEL = "FULL"             # general worker / scheduler messages
WORKFLOWS_LOG_LEVEL_STEP = "FULL"        # individual step execution
WORKFLOWS_LOG_LEVEL_BUSY = "FULL"        # postponed / rejected (lock busy)

# --- Apply WebUI overrides (if present) ---
try:
    from config.user_overrides import load_user_settings, apply_overrides_to_settings
    _ovr = load_user_settings(BASE_DIR)
    apply_overrides_to_settings(globals(), _ovr)
except Exception:
    pass
