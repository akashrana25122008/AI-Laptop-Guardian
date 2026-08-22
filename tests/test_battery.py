from types import SimpleNamespace

import pytest

from tools.battery import battery as battery_module
from tools.battery.battery import BatteryTool


def test_execute_reports_missing_battery(monkeypatch):
    monkeypatch.setattr(battery_module.psutil, "sensors_battery", lambda: None)

    assert BatteryTool().execute() == {
        "success": False,
        "tool": "battery",
        "message": "Battery not detected.",
    }


@pytest.mark.parametrize(
    ("seconds", "expected_remaining"),
    [(90 * 60, "1h 30m"), (battery_module.psutil.POWER_TIME_UNKNOWN, "Unknown"), (battery_module.psutil.POWER_TIME_UNLIMITED, "Unknown")],
)
def test_execute_reports_charge_state_and_remaining_time(monkeypatch, seconds, expected_remaining):
    battery = SimpleNamespace(percent=42, power_plugged=False, secsleft=seconds)
    monkeypatch.setattr(battery_module.psutil, "sensors_battery", lambda: battery)

    result = BatteryTool().execute()

    assert result == {
        "success": True,
        "tool": "battery",
        "data": {
            "percent": 42,
            "charging": False,
            "time_remaining": expected_remaining,
        },
    }
