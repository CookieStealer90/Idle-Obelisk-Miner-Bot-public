# Notices

The independent **Notices** control saves a game notice before sending one
dismiss tap. Its inbox sits below **Last Screenshot**, remains available while
the feature is off, and survives browser reloads and bot restarts. No OCR.
Startup is disabled by default. All operational defaults live in
`config/notice_defaults.py` and appear under Settings > notices; activation at
startup is under Startup Defaults. Save settings and restart to apply them.
The compact **NOTICES** tile in Bot Status shows the unacknowledged inbox count,
last successful detection scan age (including checks without a match), and next
scan countdown. Timing uses one muted gray line, matching the Level tile:
`next 38m22s · 1m22s ago`. A timestamp tooltip gives the last scan's local date/time.
Busy locks, unavailable frames and failed detection do not advance the last-scan
timestamp. The count shares the inbox refresh and updates immediately on local
acknowledgement, even while the feature is off. Scan timestamps reset on restart.

## Detection and scheduling

Activation checks immediately. A check with no notice schedules one random
interval, default 2700 seconds +/-15%. The dashboard uses that same deadline.
Busy locks, errors, missing screenshots, unchanged notices and remaining notices
use `NOTICES_RETRY_S` instead, without interval variance.

The worker acquires `state.ingame_action_lock` before reading the initial cache.
It reuses `game_scr` only within `NOTICES_SCREEN_REUSE_AGE_S` (default 5 seconds),
otherwise captures in `notices_scr`. Every successful tap requires a fresh
follow-up capture after a configurable animation delay. Failed fresh captures
never fall back to cached frames. The lock is released after at most
`NOTICES_MAX_PER_CYCLE` taps (default 10), including a fresh check after the last
tap. Pending work continues on a short retry. Turning the feature off cancels
at execution boundaries; an in-flight ADB call is not interrupted.

Two masked frame variants were derived from supplied 900 x 1600 screenshots:

| Variant | Original crop (x1, y1, x2, y2) |
| --- | --- |
| Level notification | `(0, 772, 372, 895)` |
| Decorated shard notification | `(0, 750, 390, 918)` |

The configurable search ROI defaults to `(0, 740, 390, 925)` to contain both.
The archived crop follows the matched variant, including its icon. Each
`images/Notices/*_frame.png` has a corresponding `*_frame_mask.png`. Zero mask
pixels exclude text, artwork and moving surroundings. Each nonzero label marks
an independent fixed border/background strip. Color squared-error matching
searches within the ROI; every strip must meet the threshold (default 0.96).
Score is `1 - worst_strip_RMSE / 255`, not a probability. Arbitrary resolutions
and unknown frame styles are not automatically supported. The template glob
and threshold are editable.
Reference PNGs retain only pixels selected by their masks; all ignored pixels
are black. This removes player-specific notice text and artwork from source
assets without changing recognition. Sanitize new reference PNGs the same way
before committing them. The separate masks and reference PNGs are both required.
Create additional pairs with `tools/create_notice_template.py`; see the
[template creation guide](../tools/CREATE_NOTICE_TEMPLATE.md) for interactive
selection, known-frame presets, sanitization and validation examples.

**Test detection** uses active settings and a sufficiently fresh `game_scr`
cache first. If absent or stale, it captures in its isolated `notices_test_scr`
slot, recreating the temporary directory through the standard capture pipeline
when necessary. It never clicks, archives or starts the bot. Failed captures
report an error without falling back to stale images.

## Persistence and acknowledgement

`core/notice_archive.py` stores UUID-named color PNGs in `temp/notices/`. Capture
time and variant are embedded in PNG metadata. PNG publication and the pending
record use atomic replacement; archive instances share an in-process lock.
This directory is excluded from Git. External cleanup of `temp/` also deletes
unread notices: exclude `temp/notices/` from such cleanup.

A durable `pending.json` records the current text-panel identity and whether a
tap was attempted. Moving game surroundings are excluded from identity. The
attempt is persisted before ADB input. An unchanged panel is not rearchived or
tapped again, even after restart or ambiguous ADB failure. Different content or
confirmed absence replaces/clears the identity. Two consecutive pixel-identical
notices cannot be distinguished from failed dismissal and are left for manual
dismissal. Tap counters represent ADB input, not verified dismissal.

Images are ordered oldest first, loaded lazily and shown in batches of 30.
Hover or keyboard focus reveals **Tap to delete**; touch devices show it
persistently. **Enlarge** opens a preview. Acknowledgement deletes only the
chosen PNG, then animates its removal. Failed deletion preserves the card and
reports an error. Visible browsers synchronize within five seconds.
Reduced-motion preferences disable animations. Acknowledgement and detection
testing never send game input.

The storage limit (default 100 MiB) stops saves and taps instead of deleting
unread images. Saving must succeed before a tap. Corrupt PNGs are preserved and
reported without hiding healthy entries. Corrupt pending records block input
with a visible error. Crashing between PNG and pending-record publication can
leave an extra preserved entry, but cannot cause a tap before storage succeeds.

## Integration and verification

Worker: `features/notices.py`; helpers: `core/notice_detection.py` and
`core/notice_archive.py`. The `web/notices_api.py` blueprint uses the existing
Flask LAN/origin policy. Validated IDs prevent arbitrary client file paths.
UI: `web/static/js/dashboard-notices.js`, dashboard template, stylesheet and
settings editor. Regression coverage: `tests/test_notices.py` and
`tests/test_dashboard_notices.cjs`, using simulated game access only.

Before real-game acceptance, confirm the target device, 900 x 1600 resolution,
English game language and both frame variants. Verify one notice per tap,
animation settling time and empty scenes without false positives. Supplied
images and simulated tests do not establish reliability across all game scenes.
