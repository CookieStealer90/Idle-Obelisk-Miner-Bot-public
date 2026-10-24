# Screenshot Capture and Troubleshooting

Updated: 2026-10-24.

## Capture Paths

All captures are full emulator screenshots. ROIs are evaluated only during
image recognition. There is no capture of an ROI crop alone.
Notices archives color crops from full-device captures separately in
`temp/notices/`; these are persistent inbox entries, not screenshot cache slots.
See [Notices](NOTICES.md) before cleaning the temporary directory.

| Usage | Local Slot |
| --- | --- |
| Run Detection | `game_scr` |
| Freebies, claim search and menu closing | `freebie_scr` |
| Lootbug detection and Buy-box retries | `lootbug_scr` |
| Founders | `founders_scr` |
| Notices (fresh captures and mandatory post-tap checks) | `notices_scr` |
| Notices manual detection test (cache-miss fallback) | `notices_test_scr` |
| Level detection | `level_scr` |
| Workflow templates, rotation, Rainbow and If conditions | `wf_scr` |
| Compatibility helper `screenshot_gray()` | `manual_scr`; destination defaults to `temp/__scr.png` through `LOCAL_SCREEN`, or an explicit argument |

The slot settings in the code remain authoritative. Each capture attempt creates
`<directory>/__obelisk_<slot>_<uuid>.png` on Android. The directory is derived
from `REMOTE_SCREEN` and defaults to `/sdcard`. The old shared file
`/sdcard/__scr.png` is no longer written. A new UUID for each attempt also
prevents collisions between captures for the same slot and between different
bot processes on Android.

Captures run through `core/screen_cache.py`:

1. Lock the destination path; different slots can work in parallel.
2. Record the active ADB device for this attempt.
3. Capture a screenshot at a unique Android path.
4. Download it to a unique local `.part` file next to the destination.
5. Validate the PNG signature, final IEND chunk, decodability and image dimensions.
6. Check the device ID, update the timestamp and replace the destination atomically.
7. Clean up this attempt's Android and intermediate files in the `finally` block.

An Android file that cannot be deleted is logged, but does not invalidate an
already successful capture. Files belonging to other capture attempts are never
deleted indiscriminately. Process termination can leave files behind.

Locks are organized per process and normalized local destination path.
Two bot processes running concurrently require separate local temporary
directories. An older bot that is already running continues to use its old
implementation until it restarts.

## Cache Contract and Failure Behavior

- `get_screen(slot, max_age, force=False, color=False)` may capture. A fresh,
  valid cached image is reused when `force=False`.
- `force=True` requires a successful new capture. Once attempts are exhausted,
  the result is `(None, 0, 0)`, never an old image.
- `get_cached_screen()` reads only a fresh local slot.
- File timestamps up to 50 ms ahead of Python's wall clock are treated as age
  zero to accommodate Windows clock precision and timestamp rounding. Larger
  future timestamps remain invalid. Expiry still uses `age >= max_age`, so a
  zero maximum age never reuses a cached frame. The viewer uses the same check.
- `get_latest_cached_screen()` reads the allowed slots in order of freshness,
  skipping missing, stale or damaged images. It never captures.
- Lootbug and Founders initially read only `game_scr` from the cache. If it is
  unsuitable, they capture in their own slots.
- `color=True` returns the color image from the same validated access. In
  particular, Rainbow Check does not read an old file after a failed capture.
- The viewer receives immutable PNG bytes through `latest_cached_png()`, without
  keeping a file handle open. It may display the last valid image regardless
  of age; this does not prove that a current capture succeeded.
- Run Detection checks under its own lock. If all capture attempts fail, it
  sets `game_running=False` as before. The message distinguishes a capture
  failure from a confirmed image miss. No new `UNKNOWN` UI state was introduced.

ADB can reconnect after connection errors. When a device ID is explicitly bound,
a command is never retried on another emulator. If reconnection selects another
device, the next complete capture attempt starts there. Other ADB callers
without device binding retain their existing behavior.

## Settings

WebUI → Settings → `screenshot_capture`; changes require a process restart.
Existing `user_settings.json` files work without migration or new entries.

| Setting | Default | Meaning |
| --- | --- | --- |
| `SCREENSHOT_CAPTURE_ATTEMPTS` | `2` | Complete capture attempts; allowed range 1–5 |
| `SCREENSHOT_RETRY_DELAY_S` | `0.2` | Delay between attempts; allowed range 0–10 seconds |
| `SCREENSHOT_LOG_LEVEL` | `TXT` | `TXT`: file; `FULL`: file + WebUI; `UI`: WebUI only |
| `SCREENSHOT_LOG_CACHE_HITS` | `False` | Additional message when a cached image is successfully reused |

Capture attempts are additional to the existing ADB command attempts.
ADB still uses a timeout of up to 30 seconds per command; reconnection and
port scanning may take additional time. The retry delay is not an overall
duration limit.

## Reading Logs

All capture messages begin with `[SCREENSHOT]`. Normal captures report their
start and successful completion. Errors, retries, reconnections, cleanup
problems and exhausted attempts are also logged. Cache-hit logging is disabled
by default to avoid filling the log on every watchdog call.

Example with shortened IDs:

```text
[SCREENSHOT] slot=game_scr request=abc capture=def device=127.0.0.1:16416 attempt=1/2 phase=capture begin remote=/sdcard/__obelisk_game_scr_def.png thread=bot-main
[SCREENSHOT] slot=game_scr request=abc capture=def device=127.0.0.1:16416 attempt=1/2 phase=pull failed: RuntimeError: ... elapsed=0.300s
[SCREENSHOT] slot=game_scr request=abc capture=def device=127.0.0.1:16416 attempt=1/2 retry_in=0.200s (new full screenshot)
[SCREENSHOT] slot=game_scr request=abc capture=ghi device=127.0.0.1:16416 attempt=2/2 phase=complete size=900x1600 bytes=120000 elapsed=0.700s recovered=True
```

- `request`: links all attempts belonging to the same request.
- `capture`: identifies an individual attempt and its Android file path.
- `phase`: `prepare`, `capture`, `pull`, `decode`, `device_check`, `publish`,
  `remote_cleanup`, `local_cleanup`, `cache_read`, `cache_stat`, `viewer_read`
  or `complete`.
- `adb_attempt` and `adb_reconnect`: show reconnections within a single ADB
  command, including the active and bound device IDs.
- `elapsed`: time since the capture function started, including its lock wait;
  the successful completion message is emitted before cleanup.
  `recovered=True` means success after another capture attempt.
- `exhausted`: all complete capture attempts failed.

For `[RUNNING] ... marking STOPPED (game stop unconfirmed; ...)`, first look for
the adjacent `slot=game_scr` error and its `request`. A normal status change
with a match score also reports the image source (`cache:<slot>` with its age
or `fresh:game_scr`).

## Verification

```powershell
python -B -m unittest discover -s tests -v
```

`tests/test_screen_cache.py` uses real PNGs, temporary local directories and
simulated ADB. Coverage includes cache age, damaged images, partial transfers,
retries, atomic replacement, device changes, parallel slots, concurrent access
to the same slot, dashboard snapshots, legacy helpers and failure diagnostics.
Deterministic timestamp tests cover slight future offsets, normalized age,
larger future timestamps, exact expiry and a zero maximum age. These reproduce
the Windows/Python 3.10 failure where an immediately read, complete frame was
discarded solely because its computed age was slightly negative.
`tests/test_screenshot_consumers.py` checks Run Detection, its serialization,
workflow color images, other consumers, configuration and HTTP delivery.
The existing Founders/Lootbug tests continue to check feature flows.

Additional checks performed on 2026-10-23 on the locally configured MuMu device:
six concurrent slots, two competing captures of `game_scr`, valid
900 × 1600 PNGs, cache/viewer access, no leftover local `.part` files and
Run-template matching with a score of 1.000. A separate temporary directory
was used. No clicks, swipes or bot starts were performed; this does not replace
an extended operational test with all features active.
