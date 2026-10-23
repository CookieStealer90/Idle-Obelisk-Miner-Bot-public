# Reliability, Configuration and LAN Access

Updated: 2026-10-23. Supplements [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).
Existing feature flows and local configuration files
are preserved.

## Success and Statistics

`core.tapper.tap()` confirms that an ADB command completed without a reported
error. It does not confirm receipt of an in-game reward. Freebies, Founders,
the initial Lootbug click and workflow click steps check this return value.
A failure does not increment the failed action's counters or trigger dependent
actions. Workflow click failures abort the workflow. `optional` still permits
missing image matches, but does not permit an ADB click failure.

Freebie-Gems remain estimates calculated from submitted claim clicks and
`FREEBIES_DIAMONDS_PER_CLAIM`. The dashboard and logs explicitly label them as
such. A successful claim click remains counted if the subsequent close click
fails; the overall cycle then reports failure. Founders still performs exactly
one click without a popup or delay. The existing Lootbug Buy retry flow remains
unchanged.

Actual reward verification requires a reliable, agreed visual indicator in the
game. No additional image search or balance measurement has been introduced.

## Configuration Protection

`config/validation.py` validates API input and loaded local settings: object
structure, allowed fields, boolean/numeric/string types, finite numbers, value
ranges, ordered ROIs, relative image paths, and workflow steps and conditions.
Actively used subworkflow targets must exist. Disabled steps and inactive
workflows may contain incomplete drafts; supplied fields remain type-checked.

Existing Founders/Lootbug migrations are preserved. The older editor value
`area: [0]`, representing the default scroll area, is normalized to `null` in a
copy. The editor now produces `[]` for blank ROI fields. A valid empty workflow
object `{}` removes all workflows, including after restart; only a missing file
selects the built-in definitions.

`config/json_store.py` first writes the complete settings or workflow document
to its own temporary file in the destination directory, calls `flush` and
`fsync`, and publishes it using `os.replace`. On failure, the previous file is
preserved and the temporary file is removed. Reads and writes share an
in-process lock, including for Windows file-sharing compatibility. Concurrent
saves use the last successfully saved whole document; edits from multiple
devices are not merged automatically. The lock does not coordinate separate
bot processes or external editors.

Invalid API input returns HTTP 400 with a field path; write failures return
HTTP 500. Invalid local settings are rejected with a warning and defaults are
used. Invalid local workflows leave the built-in defaults active at startup.
The invalid files are not overwritten. A failed reload retains the previously
active workflow definitions.

## Safe Workflow Reload

`reload_cfg` only requests a reload. The workflow worker loads and validates the
new definitions at an execution boundary. A running parent workflow and all its
subworkflow calls keep the same definition generation. Results and counters are
recorded before the swap. Other queued manual requests are retained if their
workflows still exist. A new request arriving during loading remains pending as
another request. Reload never shortens running waits.

Definitions and their runtime metadata are published together under
`state.workflows_lock`. Existing activation flags, counters and timestamps are
retained for surviving slugs; removed slugs are cleaned up. The lock protects
only brief metadata accesses and is not held over game actions or waits. The
dashboard exposes `pending`, `applied` or `error`, including an error message;
logs distinguish the request from completion. **General settings still require
a process restart.**

## Access from Multiple Devices on the Home Network

The server continues to bind to `0.0.0.0:6001`. Phones, tablets and other
computers open the bot's address, such as `http://192.168.178.50:6001`, or a
hostname resolvable on the home network. Each browser sends API requests to the
server address it opened. A client-device list or permission to use client IPs
as origins is not required. Existing Windows Firewall rules were not changed.

HTTP and Socket.IO validate the origin's scheme, host and port. Other private
origins, different ports and `Origin: null` are rejected. Engine.IO uses the
same validation for polling and WebSocket upgrades instead of wildcard CORS.
Direct LAN clients are checked using their actual peer IP; `X-Forwarded-For`,
`X-Forwarded-Host` and `X-Forwarded-Proto` do not grant exceptions. A reverse
proxy requires a separate, explicitly configured integration.

Local scripts without an Origin header remain supported. Mutating HTTP
requests without an Origin require `Content-Type: application/json`; a supplied
foreign Referer or `Sec-Fetch-Site: cross-site` is rejected. This is not user
authentication: devices on the trusted LAN can control the bot. A mandatory
password was not added, consistent with the agreed usage. The existing
`OBELISKBOT_ALLOW_PUBLIC` environment variable still disables only the IP
restriction, not origin validation; it is not required for home-network access.

## Automated Verification and Manual Acceptance

Without starting the bot or performing real ADB/game actions:

```text
python -B -m unittest discover -s tests -v
node --test tests/test_dashboard_connection.cjs tests/test_dashboard_editors.cjs
```

In addition to the existing tests, `test_action_results.py`,
`test_config_safety.py`, `test_workflow_safety.py` and
`test_dashboard_security.py` cover click failures, counters, API validation,
atomic file operations and failures, concurrent readers/writers, nested
workflows, cancellation, reload and LAN-device access. JavaScript tests cover
connection handling and editor serialization. `.github/workflows/tests.yml`
runs the checks on Windows with Python 3.10 and 3.13 and Node 22. A local test
run does not confirm that the workflow has already run on GitHub.

After an intentional restart, check manually:

1. Open the dashboard on the bot PC and a second LAN device; status and
   connection must appear. Fully reload the page if the browser caches old
   scripts.
2. Save settings: the notice must require a restart. Save a workflow and
   request reload: the request and completion must be distinguishable.
3. Start an approved flow containing a subworkflow and request reload while it
   runs: verify completion of the running flow before the update is applied.
4. Check Freebie, Founders and Lootbug flows on the specified emulator. Failure
   cases are simulated automatically; verify actual rewards separately.

These manual game and device checks were not triggered by automatically
starting the bot as part of this change.
