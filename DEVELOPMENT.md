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
