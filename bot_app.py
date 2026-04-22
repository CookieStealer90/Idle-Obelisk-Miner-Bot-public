# bot_app.py
"""Idle Obelisk Miner Bot - Application runtime

No configuration here! Everything lives in config/settings.py.
This file:
  - Propagates SUPPRESS_EXCEPTIONS via runtime_flags
  - Connects ADB
  - Contains the main loop (empty - no features yet)
"""

import time

import config.runtime_flags as runtime_flags
import config.app_state as state
from config.settings import (
    BASE_DIR, ADB,
    SUPPRESS_EXCEPTIONS, MAIN_LOOP_TICK,
)

import config.config_workflows as cfg
from core.adb_helper import adb, ensure_connected, get_active_device
from core.file_logger import file_log, log_exception, bot_log


# ========= Propagate SUPPRESS_EXCEPTIONS =========
runtime_flags.SUPPRESS_EXCEPTIONS = SUPPRESS_EXCEPTIONS
state.SUPPRESS_EXCEPTIONS = SUPPRESS_EXCEPTIONS

# ========= Wire up config_workflows reference =========
state.cfg = cfg

# ========= ADB CONNECTION =========
if not ensure_connected(log_fn=file_log):
    print("\nWARNING: No emulator found! Bot will retry on first ADB call.\n", flush=True)

# ========= Log startup =========
active_dev = get_active_device()
file_log(f"[STARTUP] ADB: {ADB} | Device: {active_dev}")
file_log(f"[STARTUP] SUPPRESS_EXCEPTIONS={SUPPRESS_EXCEPTIONS} | MAIN_LOOP_TICK={MAIN_LOOP_TICK}s")


# ===========================================================
# run() - Main loop (empty - features will be added later)
# ===========================================================
def run():
    """Start the bot main loop."""
    file_log("[STARTUP] Idle Obelisk Miner Bot started - main loop running")
    print("Bot main loop started.", flush=True)

    # Apply startup defaults to runtime state
    _settings_mod = __import__("config.settings",
                               fromlist=["FREEBIES_ENABLED_DEFAULT", "LOOTBUG_ENABLED_DEFAULT",
                                         "WORKFLOWS_ENABLED_DEFAULT"])
    state.freebies_enabled = bool(getattr(_settings_mod, "FREEBIES_ENABLED_DEFAULT", True))
    state.lootbug_enabled = bool(getattr(_settings_mod, "LOOTBUG_ENABLED_DEFAULT", False))
    state.lootbug_buy_bonus = bool(getattr(_settings_mod, "LOOTBUG_BUY_GEM_UPGRADES_ENABLED", False))
    state.workflows_master_enabled = bool(getattr(_settings_mod, "WORKFLOWS_ENABLED_DEFAULT", False))
    state.detect_level_enabled = bool(getattr(_settings_mod, "DETECT_LEVEL_ENABLED", True))

    # Start features
    from features import freebies as freebies_feature
    from features import lootbug as lootbug_feature
    from features import workflows as workflows_feature
    from features import detect_level as detect_level_feature
    freebies_feature.start()
    lootbug_feature.start()
    workflows_feature.start()
    detect_level_feature.start()
    bot_log(f"[STARTUP] Freebies feature armed (enabled={state.freebies_enabled})")
    bot_log(f"[STARTUP] Lootbug feature armed (enabled={state.lootbug_enabled})")
    bot_log(f"[STARTUP] Workflows feature armed (master={state.workflows_master_enabled})")

    # Main loop: central game-running watchdog + command dispatch.
    # Features consume state.game_running via their own is_game_running() checks.
    from core.game_state import is_game_running
    from web.app import command_queue
    from queue import Empty

    def _dispatch(c: str):
        bot_log(f"[CMD] {c}")
        if c == "freebies_toggle":
            freebies_feature.toggle()
        elif c == "lootbug_toggle":
            lootbug_feature.toggle()
        elif c == "detect_level_toggle":
            detect_level_feature.toggle()
        elif c == "detect_level_now":
            detect_level_feature.trigger_now()
        elif c == "auto_global":
            workflows_feature.toggle_master()
        elif c == "reload_cfg":
            workflows_feature.reload_workflows()
            bot_log("[CMD] reload_cfg: settings applied on next process restart; workflows reloaded now")
        elif c.startswith("wf_auto:"):
            workflows_feature.toggle_wf(c.split(":", 1)[1])
        elif c.startswith("wf_run:"):
            workflows_feature.manual_trigger(c.split(":", 1)[1])
        # Unknown commands are logged only — no-op.

    while True:
        try:
            # Drain queued UI commands
            while True:
                try:
                    cmd_str = command_queue.get_nowait()
                except Empty:
                    break
                _dispatch(cmd_str)

            is_game_running()
            time.sleep(MAIN_LOOP_TICK)
        except KeyboardInterrupt:
            print("\nBye.")
            break
        except Exception as e:
            log_exception(e, "main_loop")
            time.sleep(1.5)
