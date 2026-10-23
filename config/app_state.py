# app_state.py - Mutable runtime state shared between modules
"""
Runtime state for the Idle Obelisk Miner Bot.
bot_app.py initializes values at startup.
"""
import threading

# ========= Config reference (set by bot_app.py) =========
cfg = None

# ========= In-game action lock =========
# Acquired by any feature that is about to perform real ingame interaction
# (taps, scrolls). Pure detection / screenshotting does NOT need the lock.
# Features should prefer non-blocking acquire and reschedule themselves if
# the lock is held by another feature.
ingame_action_lock = threading.Lock()

# ========= Game State =========
game_running = False
gem_collected = 0
gem_cooldown_until = 0.0

# ========= Workflows =========
# Master switch for the workflow scheduler ("Auto WF" button).
workflows_master_enabled = False
# Per-WF runtime state, populated dynamically by features/workflows.py.
# Keyed by WF slug. Each entry:
#   {"enabled": bool, "next_due_ts": float, "last_run_ts": float,
#    "run_count": int, "last_status": str}
workflows = {}
# Slug of the workflow currently executing a step (None if idle).
workflows_running = None

# ========= Feature flags =========
gem_statistics_enabled = True
screenshot_visible = True

# ========= Freebies feature =========
freebies_enabled = True
freebies_claimed_count = 0           # number of successful claim cycles
freebies_diamonds_total = 0          # sum of diamonds from all claims
freebies_last_claim_ts = 0.0
freebies_next_check_ts = 0.0

# ========= Detect Level feature =========
detect_level_enabled = True
current_level = None                 # int 1..999 or None if unknown / disabled
current_level_ts = 0.0               # unix ts of last successful scan
detect_level_next_check_ts = 0.0
detect_level_digits_loaded = 0       # count of digit_*_tpl.png templates discovered
detect_level_last_error = ""         # last failure reason (for UI tooltip)

# ========= Lootbug feature =========
lootbug_enabled = False
lootbug_buy_bonus = False            # when True and enabled: also buy gem-bonus if template matches
lootbug_clicked_count = 0            # number of successful lootbug clicks
lootbug_bonus_count = 0              # number of successful bonus purchases
lootbug_last_click_ts = 0.0
lootbug_next_check_ts = 0.0

# ========= Suppress Exceptions =========
SUPPRESS_EXCEPTIONS = True
