# Working Instructions for Codex

These instructions apply to the entire project and our ongoing collaboration.

## Language Policy

- Communicate with the user in German.
- Use English throughout the project directory and all project content, including file and directory names, source code, comments, log messages, UI text, tests, documentation, and working instructions such as this file.
- A German conversation or request does not change the project language. Write and update project files in English unless the user explicitly requests an exception.
- Before completing a change, check added or edited project content for compliance with this language policy.

## Orientation and Documentation

- Before making changes, read the relevant sections of [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md). They describe the architecture, feature scope, module dependencies, limitations, and verification guidance.
- Inspect affected source files and local configurations where needed. Compare documentation with the current code; identify discrepancies, assumptions, and unverified behavior.
- Additional documentation:
  - [README.md](README.md): setup and operation; known inconsistencies are recorded in the project context.
  - [docs/RELIABILITY.md](docs/RELIABILITY.md): action results, configuration validation, workflow reloads, and LAN access.
  - [docs/SCREENSHOTS.md](docs/SCREENSHOTS.md): screenshot pipeline and cache.
  - [docs/STATISTICS.md](docs/STATISTICS.md): statistics, uptime, and migration.
- Keep relevant documentation current when behavior or architecture changes. This file contains working instructions; technical details belong in `docs/`.

## Approach and Change Scope

- Preserve existing features and saved user settings. Behavior changes must belong to the task and be explicitly identified.
- Before larger changes, prepare a concrete plan covering affected components, intended behavior, and checks. Agree fundamental architecture changes with the user.
- Keep changes small, understandable, and testable. Avoid unrelated restructuring, formatting, and additional dependencies.
- Check the working tree before making changes. Do not overwrite or discard existing changes or perform unrequested cleanup.

## Architecture Rules

- `main.py` and `tray_runner.py` are the entry points. `web/` provides Flask/Socket.IO and the dashboard; `bot_app.py` processes the command queue and controls background work.
- Use existing helpers in `core/` for ADB, image recognition, screenshots, clicks, and scrolling. Feature logic belongs in `features/`, central defaults in `config/`.
- Respect configuration order: `config/settings.py`, followed by local overrides from `config/user_settings.json` through `config/user_overrides.py`. Import the settings module instead of copying overridable individual values prematurely.
- New settings must also be configurable through the WebUI. Check defaults, validation, migration, persistence, and UI together. General settings require a process restart; workflow reloads apply only workflow definitions at execution boundaries.
- Coordinate game actions through `state.ingame_action_lock`. Preserve documented exceptions and workflow locking and cancellation rules. Do not hold metadata locks during ADB calls or waits.
- Preserve isolated screenshot slots, atomic publication, image validation, device binding, and age checks. A failed fresh capture must not silently fall back to an old image.
- ROIs use `(x1, y1, x2, y2)` in screen pixels. Check resolution, game language, and image templates together; automatic adaptation to arbitrary resolutions is not available.
- A successful ADB click does not confirm an in-game reward. Preserve error propagation and do not increment action counters after failed actions.
- Preserve configuration migrations, atomic JSON persistence, and existing LAN/origin checks. Do not publish local secrets or user-specific configurations.

## Verification and Completion

- Run appropriate regression tests from `tests/`. Commands for the existing Python and JavaScript tests:

  ```text
  python -B -m unittest discover -s tests -v
  node --test tests/test_dashboard_connection.cjs tests/test_dashboard_editors.cjs tests/test_dashboard_gem_stats.cjs
  ```

- Select checks according to the change scope. For documentation-only changes, content, link, and change review are sufficient. The Windows test configuration is in `.github/workflows/tests.yml`.
- Do not casually start the bot or perform real game actions for verification. Importing `bot_app.py` can already connect ADB; local startup defaults can enable game actions. Before functional tests, establish the target device, resolution, game language, and flows covered by the task.
- `TEST-ENVIRONMENT.bat` writes temporary files; `INSTALL-ENVIRONMENT.bat` installs packages; `tools/sync_workflows.py` modifies source code. Use these tools only when their effects belong to the task.
- At completion, report what changed, which checks actually ran, and any remaining limitations or open points. Simulated tests do not confirm behavior in the real game.
