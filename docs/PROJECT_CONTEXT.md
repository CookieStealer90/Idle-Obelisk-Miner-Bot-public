# Project Context: Idle Obelisk Miner Bot

Updated: 2026-10-23. Based on existing source code, local configurations,
`README.md` and the former project overview. Primarily a static inventory; the screenshot layer
described below was also checked on the emulator. Local settings and workflows
may change independently of versioned code.

## Purpose and Operation

The Python bot automates the Android game **Idle Obelisk Miner** through ADB,
primarily on Windows with MEmu or MuMu. It captures screenshots, detects game
elements, and performs clicks and drag scrolling. The Flask dashboard controls
features and workflows and displays status, logs, screenshots and statistics.
According to the README, the project is unpublished and used privately.

Detection primarily uses OpenCV template matching within fixed regions of
interest (ROIs), without an OCR library. Levels are assembled from digit
templates; Rainbow Floors are detected using HSV values and hue distribution.

## Architecture and Module Dependencies

| Component | Responsibilities and Main Connections |
| --- | --- |
| `main.py` | Sets the working directory to the project root and starts `web.app.run_server()`. |
| `tray_runner.py` | Starts the server in the background and provides the Windows tray menu for the WebUI, logs, restart, exit and local configuration reset. |
| `web/app.py` | Flask/Socket.IO server, command queue, bot thread, status broadcasts every second and dashboard endpoints. |
| `bot_app.py` | Connects ADB, initializes runtime values, starts feature threads, processes commands and checks game state. The source sets `MAIN_LOOP_TICK` to 1.5 seconds. |
| `config/settings.py`, `user_overrides.py` | Central defaults and application of `config/user_settings.json` at import time. |
| `config/app_state.py`, `runtime_flags.py` | Shared mutable runtime state, action lock and exception-handling flag propagation. |
| `config/config_workflows.py` | Default workflows, logging configuration and loading of local workflow definitions. |
| `core/adb_helper.py` | ADB discovery, connection, emulator port scanning and reconnection for certain errors; used by screenshot and input helpers. |
| `core/screen_cache.py`, `game_state.py` | Isolated full-device Android captures, atomic per-slot screenshot files in `temp/`, validated cache and serialized game detection. `core/screenshot.py` uses the same capture pipeline as a compatibility helper. |
| `core/vision.py`, `rotation_cache.py` | Grayscale image matching, cached rotated templates, masking and downscaled matching. Templates reside in `images/`. |
| `core/tapper.py`, `scroll.py` | Central click and scroll primitives with configurable timing, coordinate jitter and drag gestures. |
| `features/` | Independent workers for Freebies, Lootbugs, level detection and workflow scheduling; gem statistics with JSON persistence. |
| `web/config_api.py`, `state_builder.py`, `security.py` | Configuration/statistics API, dashboard state construction and LAN/origin access checks. |
| `web/templates/`, `web/static/` | HTML/CSS and JavaScript dashboard without an apparent frontend build step. The workflow editor comprises six scripts loaded together. |

**Data flow:** Browser -> HTTP/Socket.IO command -> `command_queue` ->
`bot_app.py` -> feature control. Feature -> screenshot/image detection ->
ADB input -> runtime state/logging -> dashboard.

`state.cfg` references `config_workflows` and supplies the logger with settings
including file path and enablement. The logger connects to the WebUI through
lazy imports to avoid circular imports. Level detection writes
`state.current_level`; workflow conditions read this value.

## Implemented Features

- **Freebies:** periodic detection using two icon templates, menu opening,
  scrolling to find the claim button, claiming, counting and closing the menu.
  Enabling wakes the worker for a prompt cycle.
- **Lootbugs:** detect `lootbug_tpl_*.png`, click, wait and capture a fresh
  screenshot; then find `Lootbug/lootbug_buy_bonus.png` within
  `LOOTBUG_BONUS_BUY_ROI` and click once at the match center. Buy ROI:
  `(310, 370, 505, 672)`. If notifications obscure the Buy box, retry with fresh
  screenshots every `LOOTBUG_BUY_RETRY_S` (default 3 seconds) until Buy succeeds
  or Lootbug is disabled. The action lock stays held during retries. There is
  no automatic closing; obsolete close settings are removed.
  The switch is ON/OFF only; the bot no longer selects bonuses or double-clicks.
  Regular scan intervals use `LOOTBUG_INTERVAL_VARIANCE_PCT` (default +/-15%,
  0 means fixed, bounded to 0-100%). After each cycle the worker draws exactly
  one delay and publishes the same target time as `lootbug_next_check_ts`; the
  status countdown derives from it. Busy, game-absent and Buy retries retain
  their separate delays without this variance.
  With the feature disabled, select the desired bonuses in the game and confirm
  with Buy; the game remembers the selection. Enable **Remove lootbug gem
  confirmation** in the game settings. Old bonus-selection settings are removed
  on load/save; the previous default Buy ROI migrates to the new value. Other
  custom ROIs are preserved.
- **Founders:** independent worker in `features/founders.py`, with its own
  switch, status tile, counters and countdown. The **Founders** WebUI section
  (`founders`, `FOUNDERS_*`) provides separate scan interval, detection and click
  settings. Independent of the Lootbug switch; both still share
  `state.ingame_action_lock`.
  Flow: detect `Founders/founders_bundle_tpl.png` and click once; no popup,
  post-click wait or closing logic. Its template resides in `images/Founders/`,
  so Lootbug image changes do not affect Founders.
  Legacy `lootbug_founders` settings migrate to `founders` on load/API access;
  previously inherited Lootbug overrides are copied, and explicit Founders
  values take precedence. Saving writes only the new format and removes
  obsolete Founders popup settings.
  `FOUNDERS_ENABLED` belongs to **Startup Defaults** (`startup_defaults`) and
  controls the initial value; the dashboard switch only changes
  `state.founders_enabled` at runtime.
- **Level detection:** periodic scan, digit assembly for levels 1-999, filtering
  of horizontally overlapping matches, display and manual scan. Templates for
  digits 0-9 exist in the inspected files.
- **Workflows:** individual intervals and random variance, automatic/manual
  execution, master switch, per-workflow activation, status and counters.
  Steps: `tap_roi`, `tap_xy`, `swipe`, `click_template`, `click_rotating`, `wait`,
  `rainbow_check`, `call_workflow`, `hold_and_wiggle` and `if`.
  Supports repeats, long presses, optional image matches and If/ElseIf/Else
  branches based on image visibility, level or the previous step result.
- **Workflow editor:** creation, duplication, deletion, sorting, drag-and-drop,
  step comments, disabled steps and hierarchical template selection.
  `dashboard-workflow-editor.js` is an intentionally retained placeholder;
  `web/templates/index.html` lists the scripts actually loaded.
- **Gem statistics:** Freebie yields, hourly buckets, session/all-time counters,
  24-hour/7-day summaries, manual additions and reset. Uptime and claim recording
  pause with the Freebie switch; the dashboard greys values and shows
  **Freebies inactive**. Wall-clock windows continue while paused. The statistics
  period starts on first activation, independently of the first claim. All-time
  uptime is a permanent sum even after hourly pruning. The amount per Freebie
  comes from configuration, not a measurement of the actual game balance.
  Lifecycle, legacy migration and verification: [Statistics](STATISTICS.md).
- **Operation:** ADB reconnection, screenshot viewer, log streaming/filtering,
  rotating file log, and restart through the dashboard or tray.

Default workflows include Bomb Rotation, Prestige, Drone Switch,
Upgrades/Contracts and Rainbow Floor Bombs. The inspected local
`user_workflows.json` also contains a Stargazing Collector. Definitions document
the available flow, not its current reliability in the game.

## Technologies, Startup and Configuration

- Python 3.10+ according to the type annotation syntax used.
  The README recommends 3.10-3.13; its Python 3.8 claim is not a reliable lower
  bound. The initial inventory did not verify installed interpreter/package
  versions; subsequent automated checks used the available local Python 3.10.
- `requirements.txt`: `opencv-python`, `flask>=3.0`, `flask-socketio>=5.3`,
  `pystray`, `pillow`, `pywin32`. NumPy is used directly but is not listed
  separately; OpenCV supplies it as a dependency.
- ADB runs through `subprocess`. The WebUI uses native JavaScript and a Socket.IO
  client loaded from an external CDN.
- Development: `python main.py [port]`; default port 6001. Tray operation:
  `pythonw tray_runner.py`, also through `StartWebUI.bat` or `.vbs`.
  The server binds to `0.0.0.0` by default and is reachable on the LAN.
- Settings: defaults in `config/settings.py`, then local overrides from
  `config/user_settings.json`. Overrides mutate the settings module's globals
  at import time. Later assignments would not update values already copied
  through `from ... import ...`.
- Workflows: after validation, `config/user_workflows.json` replaces the Python
  defaults completely, without a deep merge. `{}` is a valid empty workflow
  collection. A missing file selects built-in defaults.
- **Reload only reloads workflows. General settings require a process restart.**
  The API initially saves only the JSON files.
- Persistent statistics: `gem_statistics.json`; screenshots: `temp/`; file log:
  `bot.log`. `.gitignore` excludes all JSON files, logs and temporary
  screenshots, among other files. A Git checkout therefore does not necessarily
  reproduce the local configuration.
- Flask signing key: the first Web-App import creates a random 256-bit key in
  `config/web_secret.json`, which is reused afterwards. The existing `*.json`
  ignore rule excludes it; do not publish it or copy it between independent
  installations. Missing write permissions or a damaged file cause startup to
  fail without a fixed fallback key. To rotate it intentionally, delete the
  file while the server is stopped; existing signed sessions become invalid.
  This does not add authentication or change the LAN/origin policy.
  Tests: `tests/test_secret_key.py`, without bot startup or ADB.

## Existing Architecture Decisions and Conventions

These points are supported by code or documentation; further historical
rationale is not documented:

- Project code, comments, logs, UI text, tests and documentation must be in
  English. Chat replies may follow the user's language.
- Central settings and reusable ADB/image/input helpers are preferred over
  scattered feature configuration.
- ROIs use `(x1, y1, x2, y2)` in screen pixels. Templates, game language and
  coordinates belong together; the README requires the game to use English.
- Clicks normally use a zero-distance swipe to control hold duration.
  `hold_ms=0` uses a normal tap. Scrolling uses drag gestures with speed presets.
- Feature workers are daemon threads. Game actions normally coordinate through
  `state.ingame_action_lock`; pure detection does not need this lock. Freebies
  waits for it; Lootbugs and Workflows postpone if it is busy.
- Workflows run serially and normally hold the lock for the full flow, including
  subworkflows. `ignore_action_lock` is an existing intentional exception that
  allows interaction with other features.
- Turning the workflow master switch OFF blocks manual starts and cooperatively
  cancels running flows. An in-flight ADB call is not interrupted immediately.
  Subworkflow calls have recursion protection and a configurable depth limit
  (default 5); If blocks are limited to one level.
- Logging routes: `FULL` = file and UI, `TXT` = file, `UI` = UI only.

## Known Observations and Statically Identifiable Risks

These observations are not failure reports reproduced in the running bot:

| Code Observation | Implications for Changes |
| --- | --- |
| Features and workflow steps propagate click failures; failed actions do not increment their counters. | A successful ADB command still does not verify a reward. Freebie-Gems are labelled as calculated yields. |
| Settings/workflow APIs and local loaders share schema/value validation; storage uses atomic replacement and an in-process lock. | Migrations remain supported. Invalid API data does not overwrite a valid file; concurrently saved whole documents are not merged. |
| The worker applies workflow reloads between complete executions; metadata uses a shared lock. | Parent/subworkflows retain one definition generation; the dashboard and logs show requests, completion or errors. |
| The dashboard remains reachable on the LAN and checks origin scheme, host and port, including Socket.IO. There is no authentication. | LAN devices remain trusted. Foreign private origins and `null` are blocked; local JSON scripts without Origin remain supported. `OBELISKBOT_ALLOW_PUBLIC` can disable the IP restriction. |
| Statistics retain hourly buckets for seven days and permanent all-time gem/active-uptime sums. | Legacy files preserve gems but cannot reconstruct historical active uptime; the dashboard marks all-time uptime unavailable until an explicit reset. Rolling windows intentionally retain hourly precision. |
| The UI offers startup options for statistics/screenshot visibility; `user_overrides.py` does not apply those two options. | Saved UI values are not consistently connected to runtime state. |

Other details: the README is incomplete and gives conflicting orientation
instructions. Many current ROIs target **900 x 1600**; automatic adaptation to
arbitrary resolutions is not implemented. The WebUI explicitly distinguishes settings
restart from safe workflow reload. Dependencies are mostly unpinned. Frequent
exception suppression makes troubleshooting harder.

## Guidance for Future Development and Verification

The screenshot layer was hardened on 2026-10-23. All captures remain full-device
emulator screenshots. Each capture and retry uses its own Android file with a
slot name and UUID. Local files are published atomically only after PNG
validation; readers and writers use the same lock per destination path.
`get_cached_screen()` and `get_latest_cached_screen()` read only sufficiently
fresh local images. If the shared cache is unavailable, Lootbug and Founders
capture only in their own slots. Forced or failed fresh captures never return
old images as a fallback. Rainbow Check receives its color image directly from
the validated capture/cache access. The dashboard displays an independent copy
of the last valid image and may therefore still show an older frame. Run
Detection serializes its checks; exhausted capture retries preserve the
existing `game_running=False` behavior, explicitly noting that an actual game
stop remains unconfirmed.

`REMOTE_SCREEN` now only determines the Android directory, not a shared output
file. Related ADB commands are bound to a device ID; a device switch caused by
reconnection requires a new complete capture attempt. Locks apply within one
process; two bot processes should not share a local temporary directory.
Terminated processes can leave their own temporary files behind; there is
intentionally no blanket deletion of other or older Android files.

Settings, logging and verification details: [Screenshots](SCREENSHOTS.md).

- Preserve existing working features; keep changes small, understandable and
  testable. Present a concrete plan before larger changes; agree fundamental
  architecture changes with the user.
- Reread relevant source files and local overrides before changes. This context
  does not replace checking the current state. Record important new architecture
  decisions here or in relevant documentation. Do not include secrets in
  documentation or output.
- For settings/workflow changes, consider the backend, editor fields, JSON
  format, reload behavior and dashboard state together. For feature changes,
  consider locks, screenshot age and menu/popup state.
- Targeted Founders regression tests: `tests/test_founders.py`.
  Run `python -B -m unittest discover -s tests -v`. Tests cover migration,
  configuration API, independent activation, exactly one click without a popup,
  and locking/timing with simulated game access. There is no complete end-to-end
  suite for all real game flows. Windows CI runs Python and JavaScript
  regression tests.
  `tests/test_lootbug.py` covers the Buy-box flow with exactly one purchase
  click, obscured Buy box, missing screenshots, tap failures, retries, ON/OFF
  and configuration migration without real game access.
  `tests/test_screen_cache.py` and `tests/test_screenshot_consumers.py` cover
  isolated capture paths, actual PNG decoding, failures/retries, concurrency,
  atomic replacement, device binding, all feature consumers, Run Detection,
  Rainbow color images, dashboard and configuration API without real ADB calls.
  A separate local emulator check confirmed six parallel slots, two competing
  requests for one slot and Run-template matching at 900 x 1600 pixels; it
  performed no game actions or bot starts.
  `TEST-ENVIRONMENT.bat` checks dependencies and ADB, executes imports and writes
  temporary files; it is neither a read-only check nor a feature regression
  test. `INSTALL-ENVIRONMENT.bat` installs packages.
- `tools/calibrate_rainbow.py` analyzes existing images for calibration.
  `tools/sync_workflows.py` writes local workflows into
  `config/config_workflows.py`, modifying source code.
- Bot starts are not side-effect-free checks: importing `bot_app.py` already
  connects ADB and logs. A statistics request can initialize the background
  ticker, which later writes JSON. Local startup flags can immediately enable
  game actions.
- Before game-related functional tests, establish the emulator/game version,
  resolution, language, active ADB device and approved test flows. These
  operating details and a binding manual acceptance checklist are not yet fully
  documented.
- New settings must also be configurable in the WebUI.

Further sources: [README](../README.md),
[Collaboration Instructions](../AGENTS.md). Resolve conflicts against current
code and state documentation discrepancies explicitly.

## Action, Configuration, Reload and LAN Hardening

[RELIABILITY.md](RELIABILITY.md) describes these changes, their limitations,
tests and manual acceptance. New regression tests:
`tests/test_action_results.py`, `tests/test_config_safety.py`,
`tests/test_workflow_safety.py`, `tests/test_dashboard_security.py` and
`tests/test_dashboard_editors.cjs`. Local settings and workflows were also
checked against the new validator without overwriting their files.
