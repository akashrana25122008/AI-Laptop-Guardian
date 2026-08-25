# Development environment

This repository is the AI-assisted development copy of AI Laptop Guardian.
Use the local virtual environment so packages are not installed globally.

## Set up on Windows

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run the non-cloud import checks:

```powershell
.\.venv\Scripts\python.exe scripts\validate_imports.py
.\.venv\Scripts\python.exe -m pytest tests\test_imports.py -q
```

The validation script exits with a non-zero status if any listed import fails.

## Dependencies

Local system tools require `psutil`. The AI explanation client requires the
Python `ollama` package and a running local Ollama service. The validation
tests use `pytest`. `customtkinter` remains listed for the desktop UI.

Google Drive dependencies are intentionally not installed as part of the
non-cloud validation workflow. The current `ToolRouter` imports the Google
Drive provider transitively, so the import validation temporarily replaces
only that boundary with a test stub. It does not authenticate, read
credentials, or call Google Drive. Full cloud setup belongs to the separate
Google Drive hardening milestone.

## Ollama check

Verify that the local service is reachable without sending a model prompt:

```powershell
.\.venv\Scripts\python.exe -c "from ollama import list; list(); print('Ollama reachable')"
```

This confirms service reachability only. It does not verify that the configured
`llama3.2:3b` model is installed or generate an AI response.

## Safety

Do not add `credentials.json`, `token.json`, or `.env` to Git. They are
ignored by `.gitignore`. Do not authenticate with or mutate Google Drive while
running the non-cloud checks.

## Milestone 7 - Multi-account Google Drive architecture

Milestone 7 adds account-aware Google Drive support while
preserving every existing single-account behavior.

### Components

- `cloud/accounts.py`
  `CloudAccount` stores safe metadata only (id, provider,
  email, display name, status, token reference). It never
  stores tokens or secrets. `AccountRegistry` assigns
  sequential ids (`account-1`, ...), is idempotent for the
  same provider+email, never reuses a removed id, and can
  optionally persist safe metadata as JSON.
- `cloud/multi_drive.py`
  `MultiAccountDriveManager` owns one isolated session per
  account. The default provider factory binds each session
  to its own token file at `cloud_data/tokens/<account_id>.json`.
  Sessions are lazy: registering or listing accounts never
  constructs a provider and never touches the network.
  `authenticate_account` runs OAuth for exactly one account,
  only when explicitly requested by the user.
- `agent/tool_router.py`
  Adds `execute_cloud_search_scoped`, `execute_download_bound`,
  `resolve_account`, and `describe_connected_accounts`.
  `execute_delete_by_id` accepts an optional `account_id`.
- `agent/planner.py`
  Recognizes explicit account references ("Search account 2
  for report.pdf") and ALL-drives scoping ("Search all my
  connected Google Drives for x").
- `agent/action_safety.py`
  `PendingAction` now carries an optional `account_id`; a
  confirmed deletion is bound to that exact account.

### Deterministic selection rules

1. An explicitly named account is always used; unknown names
   fail safely instead of falling back to another account.
2. ALL-drives wording searches every connected account.
3. Exactly one connected account is used automatically.
4. Multiple connected accounts without an explicit choice
   produce a needs_selection prompt; the agent never silently
   picks an account, especially for mutations.
5. With zero registered accounts, all legacy single-provider
   behavior remains unchanged.

### Isolation guarantees

Search matches are tagged with their originating
`account_id`/`account_email`. Numbered downloads reuse that
identity so "Download number 2" can only hit the account the
result came from. Deletion confirmations carry `account_id`
end-to-end; disconnecting the bound account before
confirmation makes execution fail safely.

### Storage layout

Account registry state and per-account token files live under
`cloud_data/`, which is gitignored. Only references are stored;
token contents stay inside each isolated token file and are
never logged, printed, or returned in results.

### Tests

Milestone 7 test coverage lives in:

- `tests/test_account_registry.py`
- `tests/test_multi_drive_search.py`
- `tests/test_auth_isolation_m7.py`
- `tests/test_planner_milestone7.py`
- `tests/test_agent_multiaccount.py`
- `tests/test_delete_cross_account_safety.py`
- `tests/test_upload_resolution.py`

All cloud interaction in tests uses injected fakes or stubs;
no test authenticates with or mutates real cloud storage.

Milestone 8 - Cloud storage intelligence and cross-account analysis

Milestone 8 adds a strictly READ-ONLY analytics layer on top
of the Milestone 7 multi-account architecture. It answers
storage questions with deterministic numbers and never
mutates local or cloud data.

### Components

- `cloud/google_drive.py` (additive only)
  Three read-only provider capabilities:
  `get_storage_info` (quota via the Drive about endpoint),
  `list_large_files` (metadata ordered by quotaBytesUsed),
  and `list_all_files_metadata`. No method downloads file
  contents.
- `cloud/cloud_intelligence.py`
  `CloudStorageIntelligence` turns per-account metadata into
  deterministic cross-account facts: per-account quota
  entries, a multi-account summary with honest partial
  failures, large-file analysis, duplicate CANDIDATES by
  name + exact size, and insights. `format_size` gives one
  consistent binary-unit rendering for user-facing text.
  Unknown values stay unknown; nothing is guessed,
  defaulted to zero, or invented.
- `agent/tool_router.py`
  Adds `execute_cloud_storage`, `execute_cloud_large_files`,
  and `execute_cloud_duplicates`. Analytics default to ALL
  connected accounts because they are pure reads;
  an explicit selector still pins one account. The
  intelligence binding follows the live drive manager so a
  replaced manager can never leave stale analysis.
- `agent/planner.py`
  New intents: `cloud_storage` (quota/space/free-space
  questions), `cloud_large_files` ("files larger than N
  MB/GB/TB", default threshold 100 MB), `cloud_duplicates`,
  and `storage_overview` (unified local + cloud view).
- `agent/ai_agent.py`
  Deterministic handlers for all four tools. Like health
  reports, these answers never go through the AI: numbers
  are formatted by code, so the model can never invent
  quotas, sizes, or account identities.

### Honesty rules for aggregated data

- Every result keeps its originating account identity;
  files from different accounts are never merged into one
  ambiguous record.
- One failing account never hides healthy accounts: partial
  results stay structured, excluded accounts are listed with
  their reason, and totals include ONLY known values.
  "Unavailable" is never reported as zero.
- Duplicate candidates are always labeled possible
  (same name + same size), `confirmed` is always False, and
  nothing is ever deleted based on this analysis.

### Rate and safety profile

Analytics use bounded metadata queries (per-account listing
limits), run only when the user asks, and never spawn
background jobs, crawlers, or content reads. No new
dependencies were added.

### Tests

Milestone 8 test coverage lives in:

- `tests/test_cloud_quota.py`
- `tests/test_cloud_storage_summary.py`
- `tests/test_cloud_cross_search_m8.py`
- `tests/test_cloud_large_files.py`
- `tests/test_cloud_duplicates.py`
- `tests/test_cloud_insights.py`
- `tests/test_planner_milestone8.py`
- `tests/test_agent_cloud_intelligence.py`

All tests use injected fakes or stubs; they assert that no
download, upload, delete, or AI call ever happens during
analytics, and that partial failures remain explicit in
user-facing output.

---

## Milestone 9: Google Account Connection & Account Management

Milestone 9 adds the explicit, user-driven account lifecycle on
top of the multi-account architecture from Milestone 7:

- Connect a new Google account through Google's official
  OAuth installed-app consent flow.
- List connected accounts offline, including honest
  reporting when an account's stored authorization is
  missing.
- Disconnect exactly one account after an explicit
  confirmation, removing ONLY this application's stored
  authorization state for that account.

### One-time OAuth setup (Phase 17)

Connecting a Google account requires a Google OAuth client
configuration file named `credentials.json` in the project
root:

1. Open Google Cloud Console and create (or select) a
   project.
2. Enable the Google Drive API for that project.
3. Configure the OAuth consent screen (External or Internal,
   per your needs). No sensitive scopes are requested beyond
   Drive file access used by earlier milestones.
4. Create OAuth client credentials of type "Desktop app".
5. Download the client configuration and save it as
   `credentials.json` in the project root.

The downloaded file contains placeholders specific to your
project (for example `YOUR_GOOGLE_CLIENT_ID` and
`YOUR_GOOGLE_CLIENT_SECRET` values are filled in by Google).
This application never prints those values and never sends
them to the local AI model. `credentials.json` and all token
files stay untracked in `.gitignore`.

Without this file, connecting fails safely with setup
guidance; nothing else in the assistant is affected.

### Explicit authentication only

Authentication can NEVER start implicitly. Importing modules,
starting the agent, asking about CPU/RAM/storage/battery, or
listing accounts never triggers OAuth. The flow runs only
when the user explicitly asks to connect a Google account,
and the user always chooses their Google identity on
Google's own consent screen. The application never asks for,
accepts, or stores a password.

### New module: cloud/auth_manager.py

`GoogleAuthManager` coordinates the full lifecycle:

- Pending connections use a hidden temporary token file
  (`.pending-<random>.json`) inside the existing token
  directory until completion; failures and cancellations
  always clean it up.
- On success, the SAFE identity reported by Google is read
  via `get_account_identity()` (email + display name only),
  the account is registered/updated idempotently through the
  existing registry (same email reconnects instead of
  duplicating), and the token is relocated to that account's
  OWN isolated file `<token_dir>/<account_id>.json`.
- Completing a connection never materializes a provider
  session; lazy session construction from Milestone 7 is
  preserved.
- If the isolated token cannot be stored, a NEW registration
  is rolled back so no account ever exists without its
  authorization state.
- Disconnect marks the registration disconnected (ids are
  never silently reassigned), drops any cached session, and
  deletes only that account's token file. Other accounts are
  untouched, cloud data is never touched, and no token file
  content is ever read.
- Status listing is fully offline and reports accounts whose
  token file is missing as "authentication unavailable"
  instead of silently re-authenticating.

### Router and planner integration

`ToolRouter` gained `execute_accounts_status()`,
`execute_google_connect()`, and
`execute_google_disconnect(selector)` wired to tools
`cloud_accounts`, `cloud_connect`, and `cloud_disconnect`.
The auth manager binding follows the live drive manager like
the analytics layer does.

The Planner recognizes connect/list/disconnect phrasing with
narrow context rules, so ordinary file requests mentioning
accounts keep their Milestone 5-8 routing. Disconnect
selectors accept account numbers or email addresses; without
a selector the agent asks which account instead of guessing.

### Confirmation-gated disconnect

Disconnect requests never execute immediately. The agent
remembers the exact proposed account in single-use pending
state and requires a separate explicit confirmation message
("confirm disconnect"). Any other reply cancels; cancelled
requests can never execute later, and wrong-account input is
impossible because confirmation carries no selector.

### Security posture

- Tokens, authorization codes, client secrets, and
  credentials-file contents are never printed, logged, sent
  to the AI model, or included in any result payload.
- Identity-failure messages are fully generic so raw
  exception text from the OAuth layer can never leak.
- Listing accounts builds no sessions and performs no
  network access; a dedicated test explodes if any factory
  call happens during offline flows.
- All tests use fake handshakes only: no real OAuth, no
  browser, no network, no Google API calls.

### Dependencies

requirements.txt now lists the implementation-required
Google client libraries (unpinned, matching the project's
runtime-dependency convention): `requests`, `google-auth`,
`google-auth-oauthlib`, `google-auth-httplib2`,
`google-api-python-client`. The development venv intentionally
does not install them; cloud imports remain lazy and all
tests run against stubs.

### Tests

Milestone 9 test coverage lives in:

- `tests/test_auth_manager_connect.py`
- `tests/test_auth_token_isolation_m9.py`
- `tests/test_auth_status_security.py`
- `tests/test_planner_milestone9.py`
- `tests/test_agent_account_management.py`

## Milestone 10: Desktop UI Foundation

Milestone 10 adds a thin, headless-testable desktop
interface using customtkinter. The UI is a presentation
layer over the existing M1–M9 backend. It never performs
business logic, never bypasses safety mechanisms, and
never exposes credentials or tokens.

### Architecture

```
ui/
├── __init__.py
├── app.py              # CTk shell + entry point
├── app_controller.py   # headless GuardianController
├── components.py       # format helpers
├── navigation.py       # view keys + labels
└── views/
    ├── __init__.py
    ├── dashboard.py
    ├── health_view.py
    ├── storage_view.py
    ├── cleanup_view.py
    ├── cloud_view.py
    ├── accounts_view.py
    └── settings_view.py
```

GuardianController is the sole backend gateway. Views
are display-only and call controller methods. Background
work uses `run_in_background()` with `after()` marshaling.

### Available Views

1. **Dashboard** — status cards + assistant chat
2. **Health** — health score, components, recommendations
3. **Storage** — drives, large files, duplicates
4. **Cleanup** — scan → preview → confirm → cancel flow
5. **Cloud** — Google Drive summary, large, duplicates
6. **Accounts** — list, connect, disconnect
7. **Settings** — theme, model, Ollama status, version

### Security Guarantees

- No OAuth on startup or view navigation.
- Cleanup preserves M6 proposal → confirmation → exact snapshot execution.
- Disconnect preserves M9 confirmation flow.
- Credentials, tokens, and client secrets never appear in UI or logs.
- No network calls in UI layer.

### How to Run

```bash
python -m ui.app
```

### Tests

Milestone 10 test coverage lives in:

- `tests/test_ui_controller.py` — headless controller tests
- `tests/test_ui_security_no_auth.py` — security regression

---

## Milestone 11 — Real Google Drive Integration

### What Changed

M11 bridges the desktop UI to the real cloud backend.
The M7-M9 backend was already complete; M11 fixes UI
rendering bugs, adds account selection for disconnect,
and adds comprehensive integration tests.

### UI Fixes

**Cloud View** (`ui/views/cloud_view.py`):
- Fixed `result.get("entries")` → `result.get("accounts")`
- Fixed `storage.get("used/free/total")` → `storage.get("used_bytes/free_bytes/total_bytes")`
- Fixed `result.get("data").get("files/groups")` → `result.get("files/groups")`
- Fixed `totals.get("used/free/total")` → `totals.get("known_used_bytes/known_free_bytes")`

**Accounts View** (`ui/views/accounts_view.py`):
- Added radio button selection per account
- Disconnect now uses selected account instead of first account

### Integration Tests

`tests/test_m11_cloud_integration.py` — 31 tests covering:

- OAuth flow (connect, failed OAuth, missing credentials, no secret exposure)
- Multi-account isolation (two accounts, same filename, disconnected fails, no fallback)
- Cloud intelligence (healthy, failing, unavailable, large files, duplicates)
- Disconnect (exact account, unknown, token cleanup, preserves others)
- Account listing (offline no-auth, empty)
- Dashboard integration (account count)
- No-auth guarantees (startup, navigation, connect button)
- Settings version
- Cloud view data shapes

### Test Results

659 tests pass, 0 fail, 2 skipped (Windows symlinks).

---

## Milestone 12 — Desktop Application Reliability

### What Changed

M12 hardens the desktop UI for production use without
changing the established backend architecture.

### Background Task Safety

`run_in_background` now marshals callbacks to the main
thread via `root.after(0, ...)`. This prevents tkinter
crashes from widget manipulation on background threads.
In headless mode (no Tk root), callbacks run directly
for backward compatibility.

### Widget Existence Guards

All `_on_*` callbacks in all 7 views now check
`winfo_exists()` before manipulating widgets. This
prevents crashes when background callbacks fire after
the view or application has been destroyed.

### Clean Shutdown

`WM_DELETE_WINDOW` protocol handler added to
`GuardianApp`. The `_shutting_down` flag propagates to
the controller, preventing late callbacks from updating
a destroyed UI.

### Error Handling

- Synchronous backend calls in cancel paths wrapped in
  try/except to prevent main-thread crashes.
- `settings_view` now has isinstance guard on result.
- Dashboard uses `.get()` for card label access.
- Navigation keys derived from `NAV_ITEMS` instead of
  hardcoded set.

### Files Changed

| File | Change |
|---|---|
| `ui/app_controller.py` | Main-thread marshaling, NAV_ITEMS import, shutdown flag |
| `ui/app.py` | WM_DELETE_WINDOW handler, _root binding, clean shutdown |
| `ui/views/dashboard.py` | Widget guards, safe key access |
| `ui/views/health_view.py` | Widget guards |
| `ui/views/storage_view.py` | Widget guards |
| `ui/views/cleanup_view.py` | Widget guards, safe cancel |
| `ui/views/cloud_view.py` | Widget guards |
| `ui/views/accounts_view.py` | Widget guards, safe disconnect |
| `ui/views/settings_view.py` | Widget guards, isinstance guard |
| `tests/test_m12_reliability.py` | New: 53 reliability tests |

### Tests

53 new tests covering controller initialization,
navigation, background tasks, shutdown, error handling,
empty/unavailable states, security regressions, and
view key consistency.

### Test Results

712 tests pass, 0 fail, 2 skipped (Windows symlinks).

---

## Milestone 13 — Real-World Validation & Packaging Readiness

### What Changed

M13 validates the application for real-world local use,
adds stale-result protection, live Tk smoke tests, and
prepares a packaging foundation.

### Stale-Result Protection

`run_refresh` wraps `run_in_background` with a generation
counter per view. Each view bumps `_gen_id` before
dispatching. When a callback fires, it checks
`view._gen_id` against the captured generation; if the
view has moved on, the stale result is silently
discarded.

This prevents older results from overwriting newer ones
when rapid tab switching or repeated button presses
spawn overlapping background tasks.

### Live Tk Smoke Tests

M13 adds a Tk smoke test layer that:
- Detects whether Tk can initialize
- Skips gracefully when a display/Tk environment is
  unavailable
- Does not fail the entire suite when Tk cannot init

Where Tk is available, tests cover application
construction, root creation, view navigation, basic
widget existence, controller shutdown, and root
destruction.

### Background-Task Robustness

`run_refresh` blocks new work when `_shutting_down` is
set. Destroyed views (`winfo_exists() == False`) never
receive stale callbacks.

### Startup Validation

Verified that the application:
- Does not require Google authentication
- Does not require Ollama
- Does not require a connected Google account
- Does not automatically authenticate or upload files
- Does not expose credentials

### Local Tool Validation

All local tools produce well-formed result contracts:
health, storage, large files, duplicates, cleanup
preview, dashboard cards.

### Packaging Preparation

- `.gitignore` covers credentials, tokens, `.env`,
  `cloud_data/`, virtual environments
- No credentials tracked in git
- No hardcoded paths in UI code
- Token storage separated from source directory

### Files Changed

| File | Change |
|---|---|
| `ui/app_controller.py` | Added `next_gen()`, `run_refresh()`, generation-based staleness checks in `wrapped_done`/`wrapped_error` |
| `ui/views/dashboard.py` | Uses `run_refresh` with `_gen_id` |
| `ui/views/health_view.py` | Uses `run_refresh` with `_gen_id` |
| `ui/views/storage_view.py` | Uses `run_refresh` with `_gen_id` |
| `ui/views/cleanup_view.py` | Uses `run_refresh` with `_gen_id` |
| `ui/views/cloud_view.py` | Uses `run_refresh` with `_gen_id` |
| `ui/views/accounts_view.py` | Uses `run_refresh` with `_gen_id` |
| `ui/views/settings_view.py` | Uses `run_refresh` with `_gen_id` |
| `tests/test_m13_real_world_readiness.py` | New: 59 tests across 10 classes |

### Tests

59 new tests covering:
- Live Tk smoke (when display available)
- Refresh robustness (stale gen discard, shutdown
  blocks, headless mode)
- Stale result protection (newer wins, completed allows
  later, failed newer doesn't corrupt)
- Startup validation (no auth, no Ollama, no cloud)
- Local tool validation (all tools return valid dicts)
- Cloud safety (mocked, no implicit calls)
- Ollama validation (unavailable gracefully handled)
- Packaging exclusions (credentials not tracked)
- Security regressions (no secret leaks)
- Navigation consistency, resource path safety

### Test Results

770 tests pass, 0 fail, 3 skipped (2 Windows symlinks,
1 Tk environment limitation).

---

## Milestone 14 — Release Candidate & Windows Packaging

### What Changed

M14 turns the project into a Windows release candidate with
centralized versioning, packaging infrastructure, startup
validation, minimal logging, and first-run environment checks.

### Centralized Version

`app/version.py` contains `__version__ = "0.14.0"` — the
single source of truth for the application version. The
controller and Settings view now read from this module.

### Resource Path Helpers

`app/paths.py` provides four helpers for source vs packaged
modes:

- `app_root()` — application root (project root or PyInstaller `_MEIPASS`)
- `user_data_dir()` — writable directory for mutable state
- `ensure_user_data_dir()` — create data + tokens dirs
- `resource_path(rel)` — resolve bundled resource paths

In packaged mode, `user_data_dir()` defaults to
`%LOCALAPPDATA%/AI-Laptop-Guardian` so tokens and account
registry are stored outside the app bundle.

### First-Run Environment Checks

`app/env_check.py` validates the runtime environment at
startup:

- Python version (>= 3.9)
- CustomTkinter availability
- psutil availability
- Ollama client (optional)
- Google Drive deps (optional)
- User data directory creation

Critical check failures abort with a clear error message.
Optional failures are logged but allow startup to proceed.

### Minimal Logging

`app/logging_setup.py` configures a root logger that writes
to `<user_data_dir>/logs/app.log`. Logs never contain
credentials, OAuth tokens, client secrets, or sensitive
file contents.

### Packaging Infrastructure

| Artifact | Purpose |
|---|---|
| `AI-Laptop-Guardian.spec` | PyInstaller folder-based build |
| `scripts/build_windows.py` | Clean, build, report release size |
| `.gitignore` additions | `build/`, `dist/` excluded |

The build excludes credentials, tokens, cloud data, virtual
environments, tests, and non-essential third-party packages.

### Startup Integration

`ui/app.py` now runs `app.env_check.run_all_checks()`
before creating the window. Critical failures (missing
Python, missing CustomTkinter, missing psutil) are caught
before the first widget is drawn.

### Files Changed

| File | Change |
|---|---|
| `app/__init__.py` | New: application package |
| `app/version.py` | New: centralized version |
| `app/paths.py` | New: resource path helpers |
| `app/env_check.py` | New: startup validation |
| `app/logging_setup.py` | New: minimal logging |
| `ui/app_controller.py` | Imports `__version__`, uses it in `get_settings()` |
| `ui/app.py` | Runs `run_all_checks()` on startup |
| `AI-Laptop-Guardian.spec` | New: PyInstaller spec |
| `scripts/build_windows.py` | New: build script |
| `.gitignore` | Added `build/`, `dist/` |
| `README.md` | Updated version, added build/run instructions |
| `tests/test_m14_release_candidate.py` | New: 58 M14 tests |

### Tests

58 new tests covering:

- Version module (shape, import, non-placeholder)
- Resource paths (root, resource_path, user data, tokens)
- Environment checks (all checks, summary, critical failure)
- Logging setup
- Packaging config (spec file, build script validity)
- .gitignore coverage
- Safety regression (no tracked credentials, controller uses version)
- Data directory creation
- Navigation consistency

### Test Results

828 tests pass, 0 fail, 3 skipped (2 Windows symlinks,
1 Tk environment limitation).
