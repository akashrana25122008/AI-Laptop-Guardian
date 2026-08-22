from types import SimpleNamespace

import pytest

from tools.cpu import cpu as cpu_module
from tools.cpu.cpu import CPUTool


@pytest.mark.parametrize(
    ("usage", "expected_status"),
    [(0, "normal"), (49.99, "normal"), (50, "moderate"), (75, "high"), (90, "critical")],
)
def test_execute_reports_cpu_metrics_and_status(monkeypatch, usage, expected_status):
    frequency = SimpleNamespace(current=2400.126, min=800.0, max=3600.999)
    monkeypatch.setattr(cpu_module.psutil, "cpu_percent", lambda interval: usage)
    monkeypatch.setattr(cpu_module.psutil, "cpu_count", lambda logical: 12 if logical else 6)
    monkeypatch.setattr(cpu_module.psutil, "cpu_freq", lambda: frequency)

    result = CPUTool().execute()

    assert result["success"] is True
    assert result["tool"] == "cpu"
    assert result["data"] == {
        "usage_percent": round(usage, 2),
        "logical_cores": 12,
        "physical_cores": 6,
        "frequency_mhz": 2400.13,
        "min_frequency_mhz": 800.0,
        "max_frequency_mhz": 3601.0,
        "status": expected_status,
    }


def test_execute_allows_missing_frequency(monkeypatch):
    monkeypatch.setattr(cpu_module.psutil, "cpu_percent", lambda interval: 10)
    monkeypatch.setattr(cpu_module.psutil, "cpu_count", lambda logical: 4)
    monkeypatch.setattr(cpu_module.psutil, "cpu_freq", lambda: None)

    result = CPUTool().execute()

    assert result["success"] is True
    assert result["data"]["status"] == "normal"
    assert "frequency_mhz" not in result["data"]


def test_execute_returns_structured_error_when_metric_collection_fails(monkeypatch):
    def fail_cpu_percent(interval):
        raise RuntimeError("cpu unavailable")

    monkeypatch.setattr(cpu_module.psutil, "cpu_percent", fail_cpu_percent)

    result = CPUTool().execute()

    assert result == {
        "success": False,
        "tool": "cpu",
        "error": "cpu unavailable",
    }
