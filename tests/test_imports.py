"""Import validation for modules that do not perform cloud operations."""

import importlib
import sys
import types

import pytest


def _isolate_cloud_boundary() -> None:
    """Prevent transitive cloud imports while testing local agent modules."""
    module = types.ModuleType("cloud.google_drive")

    class GoogleDriveProvider:  # pragma: no cover - never instantiated here
        pass

    module.GoogleDriveProvider = GoogleDriveProvider
    sys.modules["cloud.google_drive"] = module


@pytest.mark.parametrize(
    "module_name",
    [
        "agent.ollama_client",
        "agent.planner",
        "agent.templates",
        "tools.cpu.cpu",
        "tools.ram.ram",
        "tools.battery.battery",
        "tools.storage.scanner",
        "tools.storage.large_files",
        "tools.health.health",
        "tools.cleanup.cleanup",
        "tools.file_inspector.inspector",
    ],
)
def test_non_cloud_module_imports(module_name: str) -> None:
    assert importlib.import_module(module_name) is not None


@pytest.mark.parametrize("module_name", ["agent.tool_router", "agent.ai_agent"])
def test_agent_module_imports_without_cloud_dependencies(module_name: str) -> None:
    _isolate_cloud_boundary()
    assert importlib.import_module(module_name) is not None
