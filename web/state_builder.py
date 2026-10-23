# web/state_builder.py - Bot state dictionary builder
"""
Builds the state dict pushed to dashboard clients every second.
"""
import time


def _get_gem_statistics():
    """Safely fetch gem statistics."""
    try:
        from features.gem_statistics import get_gem_statistics
        return get_gem_statistics().get_stats()
    except Exception:
        return {}


def build_state_dict():
    """Build state dict for the web UI."""
    try:
        import config.app_state as state
        import config.settings as s
        from config.config_workflows import WORKFLOWS
        from core.adb_helper import get_active_device, _connected

        now = time.time()

        # Build workflows list (sorted by user-defined order)
        wf_list = []
        items = [(slug, wf) for slug, wf in WORKFLOWS.items() if isinstance(wf, dict)]
        items.sort(key=lambda kv: (int(kv[1].get("order", 999)), kv[0]))
        for slug, wf in items:
            rt = state.workflows.get(slug, {})
            next_due = float(rt.get("next_due_ts", 0.0))
            wf_list.append({
                "slug": slug,
                "name": wf.get("name", slug),
                "description": wf.get("description", ""),
                "order": int(wf.get("order", 999)),
                "inactive": bool(wf.get("inactive", False)),
                "interval_s": float(wf.get("interval_s", 60.0)),
                "enabled": bool(rt.get("enabled", False)),
                "next_due_ts": next_due,
                "next_remaining": max(0, int(next_due - now)) if next_due > 0 else 0,
                "last_run_ts": float(rt.get("last_run_ts", 0.0)),
                "last_status": rt.get("last_status", ""),
                "run_count": int(rt.get("run_count", 0)),
                "running": (state.workflows_running == slug),
                "step_count": len([st for st in (wf.get("steps") or []) if not st.get("_disabled")]),
            })

        return {
            "started": True,
            "game_running": state.game_running,
            "adb_connected": _connected,
            "adb_device": get_active_device(),
            "gems": {
                "collected": state.gem_collected,
            },
            "cooldowns": {
                "normal_remaining": max(0, int(state.gem_cooldown_until - now)),
            },
            "workflows_master_enabled": bool(getattr(state, "workflows_master_enabled", False)),
            "workflows": wf_list,
            "workflows_running": getattr(state, "workflows_running", None),
            "gem_statistics_enabled": getattr(state, 'gem_statistics_enabled', True),
            "screenshot_visible": getattr(state, 'screenshot_visible', True),
            "gem_statistics": _get_gem_statistics() if getattr(state, 'gem_statistics_enabled', True) else {},
            "freebies": {
                "enabled": getattr(state, 'freebies_enabled', True),
                "claimed": getattr(state, 'freebies_claimed_count', 0),
                "diamonds": getattr(state, 'freebies_diamonds_total', 0),
                "last_claim_ts": getattr(state, 'freebies_last_claim_ts', 0.0),
                "next_check_ts": getattr(state, 'freebies_next_check_ts', 0.0),
                "next_check_remaining": max(0, int(getattr(state, 'freebies_next_check_ts', 0.0) - now)),
            },
            "detect_level": {
                "enabled": getattr(state, 'detect_level_enabled', True),
                "armed": int(getattr(state, 'detect_level_digits_loaded', 0)) > 0,
                "digits_loaded": int(getattr(state, 'detect_level_digits_loaded', 0)),
                "current": getattr(state, 'current_level', None),
                "last_ts": float(getattr(state, 'current_level_ts', 0.0)),
                "last_age": (int(now - getattr(state, 'current_level_ts', 0.0))
                             if getattr(state, 'current_level_ts', 0.0) > 0 else None),
                "next_check_ts": float(getattr(state, 'detect_level_next_check_ts', 0.0)),
                "next_check_remaining": max(0, int(getattr(state, 'detect_level_next_check_ts', 0.0) - now)),
                "last_error": getattr(state, 'detect_level_last_error', ""),
            },
            "action_lock": {
                "locked": bool(getattr(state, 'ingame_action_lock', None) and state.ingame_action_lock.locked()),
            },
            "lootbug": {
                "enabled": getattr(state, 'lootbug_enabled', False),
                "buy_bonus": getattr(state, 'lootbug_buy_bonus', False),
                "clicked": getattr(state, 'lootbug_clicked_count', 0),
                "bonus_count": getattr(state, 'lootbug_bonus_count', 0),
                "last_click_ts": getattr(state, 'lootbug_last_click_ts', 0.0),
                "next_check_ts": getattr(state, 'lootbug_next_check_ts', 0.0),
                "next_check_remaining": max(0, int(getattr(state, 'lootbug_next_check_ts', 0.0) - now)),
                "founders_enabled": getattr(s, 'LOOTBUG_FOUNDERS_ENABLED', False),
                "founders_count": getattr(state, 'lootbug_founders_count', 0),
            },
        }
    except Exception as e:
        return {"started": False, "error": str(e)}
