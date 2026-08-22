from types import SimpleNamespace

import pytest

from tools.ram import ram as ram_module
from tools.ram.ram import RAMTool


GIB = 1024 ** 3


@pytest.mark.parametrize(
    ("percent", "expected_status"),
    [(0, "normal"), (59.9, "normal"), (60, "moderate"), (80, "high"), (90, "critical")],
)
def test_execute_reports_memory_metrics_and_status(monkeypatch, percent, expected_status):
    memory = SimpleNamespace(
        total=16 * GIB,
        used=int(6.25 * GIB),
        available=int(9.75 * GIB),
        percent=percent,
    )
    monkeypatch.setattr(ram_module.psutil, "virtual_memory", lambda: memory)

    result = RAMTool().execute()

    assert result == {
        "success": True,
        "tool": "ram",
        "data": {
            "total_gb": 16.0,
            "used_gb": 6.25,
            "available_gb": 9.75,
            "usage_percent": round(percent, 1),
            "status": expected_status,
        },
    }


def test_execute_returns_structured_error_when_memory_collection_fails(monkeypatch):
    def fail_virtual_memory():
        raise RuntimeError("memory unavailable")

    monkeypatch.setattr(ram_module.psutil, "virtual_memory", fail_virtual_memory)

    result = RAMTool().execute()

    assert result == {
        "success": False,
        "tool": "ram",
        "error": "memory unavailable",
    }
