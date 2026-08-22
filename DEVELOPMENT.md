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
