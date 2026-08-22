from unittest.mock import Mock

from tools.health.health import HealthTool


def configure_health_tool(cpu, ram, battery, drives):
    tool = HealthTool()
    tool.cpu = Mock(execute=Mock(return_value=cpu))
    tool.ram = Mock(execute=Mock(return_value=ram))
    tool.battery = Mock(execute=Mock(return_value=battery))
    tool.storage = Mock(
        get_drive_info=Mock(return_value=drives),
        get_temp_files_size=Mock(return_value={"user_temp_gb": 0, "windows_temp_gb": 0}),
    )
    tool.large = Mock(scan=Mock(return_value=[]))
    return tool


def successful_result(tool_name, data):
    return {"success": True, "tool": tool_name, "data": data}


def test_execute_calculates_deterministic_healthy_report_from_mocked_tools():
    tool = configure_health_tool(
        successful_result("cpu", {"usage_percent": 10}),
        successful_result("ram", {"usage_percent": 50}),
        successful_result("battery", {"percent": 80, "charging": True}),
        [{"drive": "C:", "percent_used": 50}],
    )

    result = tool.execute()

    assert result["success"] is True
    assert result["tool"] == "health"
    assert result["data"]["overall"] == {"score": 100, "status": "Excellent"}
    assert result["data"]["component_scores"] == {
        "cpu": 100,
        "ram": 100,
        "battery": 100,
        "storage": 100,
    }
    assert result["data"]["priority_issues"] == []
    assert result["data"]["recommendations"] == []


def test_execute_prioritizes_critical_measurements_and_builds_recommendations():
    tool = configure_health_tool(
        successful_result("cpu", {"usage_percent": 96}),
        successful_result("ram", {"usage_percent": 82}),
        successful_result("battery", {"percent": 10, "charging": False}),
        [{"drive": "C:", "percent_used": 96}],
    )

    result = tool.execute()

    assert result["data"]["overall"] == {"score": 34, "status": "Critical"}
    assert result["data"]["component_scores"] == {
        "cpu": 25,
        "ram": 70,
        "battery": 20,
        "storage": 20,
    }
    assert [issue["component"] for issue in result["data"]["priority_issues"]] == [
        "CPU", "Battery", "Storage", "RAM",
    ]
    assert result["data"]["recommendations"] == [
        "Check Task Manager for applications causing high CPU usage.",
        "Connect the laptop to a charger soon because the battery is critically low.",
        "Review large files, temporary files, and unused applications on the affected drive.",
        "Close unnecessary applications and browser tabs to reduce memory usage.",
    ]


def test_execute_returns_structured_error_when_a_dependency_fails():
    tool = HealthTool()
    tool.cpu = Mock(execute=Mock(side_effect=RuntimeError("cpu collector failed")))

    assert tool.execute() == {
        "success": False,
        "tool": "health",
        "error": "cpu collector failed",
    }
