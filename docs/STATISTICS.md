# Freebie-Gem Statistics

The Freebie worker initializes statistics at startup and forwards its initial
enabled state and every ON/OFF transition. Dashboard requests do not activate
tracking. Search time, configured waits, waiting for the game and waiting for
the action lock count while the Freebie switch is ON. Disabled time does not.
There is intentionally no special handling of computer sleep.

## Lifecycle and Averages

- A new statistics period starts at the first activation, including after a
  reset while inactive. Its timestamp is persisted immediately, before a claim.
- Uptime and both automatic/manual claim recording pause while OFF. The GUI
  shows **Freebies inactive**, greys the table and disables manual addition.
  The manual-add endpoint also rejects inactive requests with HTTP 409.
- Wall-clock time continues during disabled and offline periods. The 24h and
  7d rows become available after 24/168 real hours from statistics start, even
  with zero claims. Their hourly buckets continue expiring during pauses.
- Wall-clock averages divide by 24/168 hours or elapsed time since statistics
  start. Uptime averages divide by the active time for that same row. Averages
  require one hour of the corresponding denominator; zero uptime is never
  divided into a gem count. Session averages always use active session time.
- Restart resets session gems and session active uptime, preserving the period,
  totals and windows. Offline time is not added to active uptime on restart.
- Reset clears totals, buckets and all session accounting, resetting the last
  tick without starting another thread. If active, the new period starts now;
  otherwise it waits for activation. This does not change feature settings,
  game actions or Freebie cooldowns.

## Storage and Existing Data

`gem_statistics.json` retains hourly buckets for seven days, including the
partially overlapping oldest hour. This intentional approximation can include
up to almost one extra hour in a rolling window. All-time gems and uptime are
separate permanent sums; deleting buckets does not change either sum.

Statistics use the existing atomic JSON writer. Save errors reach API/feature
callers; background save errors issue a warning and do not stop the ticker.
Active uptime is checkpointed every minute and on claims/switch changes. An
abrupt process exit can lose the uncheckpointed tail. The enabled flag is not
restored from statistics: the worker supplies the configured state each start.

Legacy files did not store activation time or permanent active uptime. Migration
preserves gem totals and buckets, uses the previous reset time or earliest
available first-event/bucket timestamp as the best known period start, and marks
historical All-Time uptime as unavailable. Its dependent uptime average is also
unavailable; it is not represented as an exact reconstructed value. A user reset
starts complete tracking. Migration never resets the user's data automatically.
Unparseable or structurally incompatible files are not silently replaced.

## Verification

- `python -B -m unittest discover -s tests -p test_gem_statistics.py -v`
- `node --test tests/test_dashboard_gem_stats.cjs`

Tests use temporary files and simulated clocks. They cover startup/toggle hooks,
search before a first claim, pause/resume, real-time window availability with
zero claims, both averages, restart/offline time, active/inactive reset, fourteen
days of pruning, concurrent requests, legacy migration and inactive API gating.
Dashboard tests cover the paused label/style, manual-add gating, dates/tooltips,
mode changes and missing historical uptime. No real ADB or bot starts are needed.
