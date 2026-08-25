# AI Laptop Guardian

An offline AI-powered Windows assistant that analyzes your laptop's health, explains issues in plain English, and helps clean unnecessary files safely.

## Features

### Storage Analysis
- Drive usage
- Temporary files
- Large file detection
- Downloads analysis (In Progress)
- Duplicate finder (Planned)
- Empty folder detection (Planned)

### System Health
- Battery health (Planned)
- CPU monitoring (Planned)
- RAM monitoring (Planned)
- Disk health (Planned)

### AI Assistant
- Local LLM using Ollama
- Natural language chat
- Intelligent recommendations
- Safe cleanup confirmation

## Tech Stack

- Python
- Ollama
- Llama 3.2 (3B)
- psutil
- CustomTkinter

## Project Structure

```text
AI-Laptop-Guardian/
├── app/
├── ui/
├── cloud/
├── tools/
├── agent/
├── reports/
├── tests/
└── logs/
```

## Running from source

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m ui.app
```

## Building a Windows release

Requires PyInstaller (`pip install pyinstaller`):

```powershell
.\.venv\Scripts\python.exe scripts\build_windows.py
```

The release is placed in `dist/AI-Laptop-Guardian/`.

## Roadmap

- [x] Drive Scanner
- [x] Temporary File Scanner
- [x] Large File Scanner
- [ ] Downloads Analyzer
- [ ] Duplicate Finder
- [ ] Battery Health
- [ ] CPU Monitor
- [ ] RAM Monitor
- [ ] AI Chat
- [ ] Desktop Dashboard

## Status

Current Version: **v0.14.0**

This project is under active development.
