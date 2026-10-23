"""Gem collection statistics tracker with persistence."""
import json
import time
import threading
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent
_STATS_FILE = _BASE_DIR / "gem_statistics.json"
_PRUNE_DAYS = 7
_instance = None
_lock = threading.Lock()


def get_gem_statistics():
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = GemStatistics()
    return _instance


class GemStatistics:
    def __init__(self):
        self._lock = threading.Lock()
        self._session_start = time.time()
        self._session_gems = 0
        self._diamonds_per_claim = 5  # default, can be configured
        self._data = {
            "hourly_buckets": {},  # "YYYY-MM-DD-HH": {"gems": N, "uptime_s": N}
            "alltime_gems": 0,
            "first_event_ts": 0,
            "last_reset_ts": 0,
        }
        self._last_tick = time.time()
        self._load()
        # Start uptime ticker
        self._tick_thread = threading.Thread(target=self._uptime_ticker, daemon=True)
        self._tick_thread.start()

    def _load(self):
        try:
            if _STATS_FILE.exists():
                with open(_STATS_FILE, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
        except Exception:
            pass

    def _save(self):
        try:
            with open(_STATS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception:
            pass

    def _bucket_key(self, ts=None):
        import datetime
        dt = datetime.datetime.fromtimestamp(ts or time.time())
        return dt.strftime("%Y-%m-%d-%H")

    def _uptime_ticker(self):
        while True:
            time.sleep(60)
            with self._lock:
                now = time.time()
                elapsed = now - self._last_tick
                self._last_tick = now
                key = self._bucket_key()
                if key not in self._data["hourly_buckets"]:
                    self._data["hourly_buckets"][key] = {"gems": 0, "uptime_s": 0}
                self._data["hourly_buckets"][key]["uptime_s"] += elapsed
                self._prune()
                self._save()

    def _prune(self):
        import datetime
        cutoff = datetime.datetime.now() - datetime.timedelta(days=_PRUNE_DAYS)
        cutoff_key = cutoff.strftime("%Y-%m-%d-%H")
        to_delete = [k for k in self._data["hourly_buckets"] if k < cutoff_key]
        for k in to_delete:
            del self._data["hourly_buckets"][k]

    def record_claim(self, gem_type="gem", amount=None):
        """Record one claim. If `amount` is None, read FREEBIES_DIAMONDS_PER_CLAIM
        from settings (falls back to the internal default of 5 if unavailable)."""
        if amount is None:
            try:
                import config.settings as _s
                amount = int(getattr(_s, "FREEBIES_DIAMONDS_PER_CLAIM", self._diamonds_per_claim))
            except Exception:
                amount = self._diamonds_per_claim
        amount = int(amount)
        with self._lock:
            self._session_gems += amount
            key = self._bucket_key()
            if key not in self._data["hourly_buckets"]:
                self._data["hourly_buckets"][key] = {"gems": 0, "uptime_s": 0}
            self._data["hourly_buckets"][key]["gems"] += amount
            self._data["alltime_gems"] += amount
            if self._data["first_event_ts"] <= 0:
                self._data["first_event_ts"] = time.time()
            self._save()
            return amount

    def reset(self):
        with self._lock:
            self._data = {
                "hourly_buckets": {},
                "alltime_gems": 0,
                "first_event_ts": 0,
                "last_reset_ts": time.time(),
            }
            self._session_gems = 0
            self._save()

    def get_stats(self):
        with self._lock:
            import datetime
            now = time.time()
            session_uptime = now - self._session_start

            # Collect bucket data for time windows
            now_dt = datetime.datetime.now()
            h24_cutoff = (now_dt - datetime.timedelta(hours=24)).strftime("%Y-%m-%d-%H")
            d7_cutoff = (now_dt - datetime.timedelta(days=7)).strftime("%Y-%m-%d-%H")

            gems_24h = 0
            gems_7d = 0
            uptime_24h = 0
            uptime_7d = 0
            uptime_all = 0

            for key, bucket in self._data["hourly_buckets"].items():
                g = bucket.get("gems", 0)
                u = bucket.get("uptime_s", 0)
                uptime_all += u
                if key >= d7_cutoff:
                    gems_7d += g
                    uptime_7d += u
                if key >= h24_cutoff:
                    gems_24h += g
                    uptime_24h += u

            first_ts = self._data.get("first_event_ts", 0)
            reset_ts = self._data.get("last_reset_ts", 0)
            alltime_gems = self._data.get("alltime_gems", 0)

            # Wall clock since first event
            wallclock_alltime = (now - first_ts) if first_ts > 0 else 0

            # Averages
            def avg_h(total, seconds):
                if seconds < 3600:
                    return None
                return round(total / (seconds / 3600), 1)

            # Session avg always uses session uptime
            avg_session = avg_h(self._session_gems, session_uptime)

            # 24h/7d availability
            wallclock_since_first = now - first_ts if first_ts > 0 else 0
            has_24h = wallclock_since_first >= 86400
            has_7d = wallclock_since_first >= 86400 * 7

            result = {
                "uptime_session_s": round(session_uptime),
                "uptime_24h_s": round(uptime_24h) if has_24h else None,
                "uptime_7d_s": round(uptime_7d) if has_7d else None,
                "uptime_alltime_s": round(uptime_all),
                "wallclock_alltime_s": round(wallclock_alltime),
                "wallclock_remaining_24h_s": max(0, round(86400 - wallclock_since_first)) if not has_24h and first_ts > 0 else None,
                "wallclock_remaining_7d_s": max(0, round(86400 * 7 - wallclock_since_first)) if not has_7d and first_ts > 0 else None,

                "gem_since_startup": self._session_gems,
                "gem_last_24h": gems_24h if has_24h else None,
                "gem_last_7d": gems_7d if has_7d else None,
                "gem_alltime": alltime_gems,

                "gem_avg_per_hour_session": avg_session,
                "gem_avg_per_hour_24h": avg_h(gems_24h, 86400) if has_24h else None,
                "gem_avg_per_hour_7d": avg_h(gems_7d, 86400 * 7) if has_7d else None,
                "gem_avg_per_hour_alltime": avg_h(alltime_gems, wallclock_alltime) if wallclock_alltime >= 3600 else None,

                "gem_avg_per_hour_uptime_24h": avg_h(gems_24h, uptime_24h) if has_24h and uptime_24h >= 3600 else None,
                "gem_avg_per_hour_uptime_7d": avg_h(gems_7d, uptime_7d) if has_7d and uptime_7d >= 3600 else None,
                "gem_avg_per_hour_uptime_alltime": avg_h(alltime_gems, uptime_all) if uptime_all >= 3600 else None,

                "first_event_ts": first_ts,
                "last_reset_ts": reset_ts,
            }
            return result
