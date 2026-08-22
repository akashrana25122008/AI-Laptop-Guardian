"""Run non-cloud import validation and return a failing exit code on errors."""

import importlib
import sys
import types
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def isolate_cloud_boundary() -> None:
    """Keep this validation independent of Google Drive dependencies."""
    module = types.ModuleType("cloud.google_drive")

    class GoogleDriveProvider:
        pass

    module.GoogleDriveProvider = GoogleDriveProvider
    sys.modules["cloud.google_drive"] = module


MODULES = [
    "agent.ollama_client", "agent.planner", "agent.templates", "tools.cpu.cpu",
    "tools.ram.ram", "tools.battery.battery", "tools.storage.scanner",
    "tools.storage.large_files", "tools.health.health", "tools.cleanup.cleanup",
    "tools.file_inspector.inspector", "agent.tool_router", "agent.ai_agent",
]


def main() -> int:
    isolate_cloud_boundary()
    failures = []
    for module_name in MODULES:
        try:
            importlib.import_module(module_name)
            print(f"PASS {module_name}")
        except Exception as error:
            failures.append((module_name, error))
            print(f"FAIL {module_name}: {error}")
    print(f"Imported {len(MODULES) - len(failures)}/{len(MODULES)} modules.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
