"""Routing tests for ToolRouter and AIAgent.

Google Drive is replaced by an offline stub before the agent
modules are imported. No test in this file authenticates with,
reads credentials for, or performs any real cloud operation.

Local tools are replaced by fakes so no hardware state is
required and nothing on disk is modified.
"""

import sys
import types


# =========================================================
# OFFLINE GOOGLE DRIVE BOUNDARY
# =========================================================


def _install_cloud_stub() -> None:
    """
    Replace the Google Drive provider boundary with a stub
    that cannot authenticate or reach the network.
    """

    module = types.ModuleType("cloud.google_drive")

    class StubGoogleDriveProvider:
        """Inert stand-in. Performs no I/O whatsoever."""

        authenticated = False

        def __init__(self, *args, **kwargs):
            self.service = None
            self.credentials = None

    module.GoogleDriveProvider = StubGoogleDriveProvider
    sys.modules["cloud.google_drive"] = module


_install_cloud_stub()

from agent.ai_agent import AIAgent  # noqa: E402
from agent.tool_router import ToolRouter  # noqa: E402


# =========================================================
# FAKES
# =========================================================


class FakeAI:
    """Records prompts instead of calling Ollama."""

    def __init__(self):
        self.prompts = []

    def ask(self, prompt):
        self.prompts.append(str(prompt))
        return "FAKE AI RESPONSE"


class FakeProvider:
    """Fake Google Drive provider. Records calls, returns canned data."""

    def __init__(self, search_result=None, download_result=None,
                 delete_result=None):
        self.search_calls = []
        self.download_by_id_calls = []
        self.delete_by_id_calls = []
        self.upload_calls = []
        self.download_calls = []
        self._search_result = search_result
        self._download_result = download_result
        self._delete_result = delete_result

    def search_files(self, query):
        self.search_calls.append(query)
        if isinstance(self._search_result, Exception):
            raise self._search_result
        return self._search_result

    def download_file_by_id(self, file_id):
        self.download_by_id_calls.append(file_id)
        return self._download_result

    def delete_file_by_id(self, file_id):
        self.delete_by_id_calls.append(file_id)
        return self._delete_result

    def upload_file(self, local_path):
        self.upload_calls.append(local_path)
        return {"success": True}

    def download_file(self, query):
        self.download_calls.append(query)
        return self._download_result


def make_health_report():
    return {
        "success": True,
        "tool": "health",
        "data": {
            "overall": {"score": 86, "status": "Good"},
            "component_scores": {
                "cpu": 90,
                "ram": 85,
                "battery": 80,
                "storage": 75,
            },
            "priority_issues": [],
            "recommendations": [],
        },
    }


import pytest  # noqa: E402


@pytest.fixture()
def agent():
    """AIAgent whose AI client can never reach Ollama."""
    aia = AIAgent()
    aia.ai = FakeAI()
    return aia


@pytest.fixture()
def router():
    return ToolRouter()


# =========================================================
# TOOL ROUTER DISPATCH
# =========================================================


class TestToolRouterDispatch:

    def test_no_tool_returns_error(self, router):
        result = router.execute(None)

        assert result["success"] is False
        assert "No tool" in result["error"]

    def test_unknown_tool_returns_error(self, router):
        result = router.execute("does_not_exist")

        assert result["success"] is False
        assert "Unknown tool" in result["error"]

    @pytest.mark.parametrize(
        "tool_name,attribute",
        [
            ("battery", "battery_tool"),
            ("cpu", "cpu_tool"),
            ("ram", "ram_tool"),
            ("health", "health_tool"),
        ],
    )
    def test_local_tool_dispatch(self, router, tool_name, attribute):
        sentinel = {
            "success": True,
            "tool": tool_name,
            "data": {},
        }

        class FakeTool:
            def execute(self_inner):
                return sentinel

        setattr(router, attribute, FakeTool())

        assert router.execute(tool_name) is sentinel

    def test_storage_normalization_and_status(self, router):
        drive = {
            "drive": "C:\\",
            "mount": "C:\\",
            "total_gb": 100.0,
            "used_gb": 95.0,
            "free_gb": 5.0,
            "percent_used": 95.0,
        }

        router.storage_tool.get_drive_info = lambda: [drive]
        router.storage_tool.get_temp_files_size = lambda: 123

        result = router.execute("storage")

        assert result["success"] is True
        assert result["tool"] == "storage"
        assert result["data"]["temp_files"] == 123

        normalized = result["data"]["drives"][0]
        assert normalized["status"] == "Critical"

    def test_storage_drive_without_percentage_gets_unknown(
        self,
        router,
    ):
        router.storage_tool.get_drive_info = (
            lambda: [{"drive": "X:\\", "mount": "X:\\"}]
        )
        router.storage_tool.get_temp_files_size = lambda: 0

        result = router.execute("storage")

        assert result["success"] is True
        assert result["data"]["drives"][0]["status"] == "Unknown"

    def test_file_inspector_requires_path(self, router):
        result = router.execute("file_inspector", None)

        assert result["success"] is False
        assert "path" in result["error"].lower()

    def test_file_inspector_delegates(self, router):
        inspected = {"success": True, "tool": "file_inspector"}

        router.file_inspector.inspect = lambda path: inspected

        assert router.execute("file_inspector", "log.txt") is inspected

    def test_cloud_search_delegates(self, router):
        provider = FakeProvider(search_result={"success": True})
        router.google_drive = provider

        result = router.execute("cloud_search", "invoices")

        assert result == {"success": True}
        assert provider.search_calls == ["invoices"]

    def test_cloud_upload_and_download_delegate(self, router):
        provider = FakeProvider(download_result={"success": True})
        router.google_drive = provider

        assert router.execute("cloud_upload", "a.txt") == {
            "success": True
        }
        assert provider.upload_calls == ["a.txt"]

        assert router.execute("cloud_download", "b.txt") == {
            "success": True
        }
        assert provider.download_calls == ["b.txt"]


# =========================================================
# TOOL ROUTER - DELETE SAFETY FLOW (MOCKED)
# =========================================================


class TestCloudDeleteSafetyFlow:

    def test_empty_query_is_rejected_without_search(self, router):
        provider = FakeProvider(search_result={"success": True})
        router.google_drive = provider

        result = router.execute("cloud_delete", "   ")

        assert result["success"] is False
        assert provider.search_calls == []
        assert provider.delete_by_id_calls == []

    def test_failed_search_cancels_delete(self, router):
        provider = FakeProvider(search_result={"success": False})
        router.google_drive = provider

        result = router.execute("cloud_delete", "notes.txt")

        assert result["success"] is False
        assert provider.delete_by_id_calls == []

    def test_zero_matches_cancels_delete(self, router):
        provider = FakeProvider(
            search_result={"success": True, "matches": []}
        )
        router.google_drive = provider

        result = router.execute("cloud_delete", "missing.txt")

        assert result["success"] is False
        assert provider.delete_by_id_calls == []

    def test_multiple_matches_cancel_delete(self, router):
        provider = FakeProvider(
            search_result={
                "success": True,
                "matches": [
                    {"id": "1", "name": "notes.txt"},
                    {"id": "2", "name": "notes copy.txt"},
                ],
            }
        )
        router.google_drive = provider

        result = router.execute("cloud_delete", "notes.txt")

        assert result["success"] is False
        assert "cancelled" in result["message"].lower()
        assert provider.delete_by_id_calls == []

    def test_single_match_deletes_by_id_once(self, router):
        provider = FakeProvider(
            search_result={
                "success": True,
                "matches": [{"id": "abc123", "name": "notes.txt"}],
            },
            delete_result={"success": True},
        )
        router.google_drive = provider

        result = router.execute("cloud_delete", "notes.txt")

        assert result["success"] is True
        assert provider.delete_by_id_calls == ["abc123"]
        assert "notes.txt" in result["message"]


# =========================================================
# AI AGENT - NUMBERED DOWNLOAD HANDLING (MOCKED)
# =========================================================


class TestNumberedDownloads:

    SUCCESS_DOWNLOAD = {
        "success": True,
        "tool": "cloud_download",
        "data": {
            "name": "report.pdf",
            "path": "downloads/report.pdf",
            "size_bytes": 2048,
        },
    }

    def _arm_memory(self, agent):
        provider = FakeProvider(
            download_result=self.SUCCESS_DOWNLOAD
        )
        agent.router.google_drive = provider
        agent.last_cloud_matches = [
            {"id": "f1", "name": "first.pdf"},
            {"id": "f2", "name": "report.pdf"},
        ]
        return provider

    def test_download_number_selects_correct_file(self, agent):
        provider = self._arm_memory(agent)

        response = agent.chat("Download number 2")

        assert "Downloaded successfully" in response
        assert "report.pdf" in response
        assert provider.download_by_id_calls == ["f2"]

    def test_word_selection_downloads_second_one(self, agent):
        provider = self._arm_memory(agent)

        response = agent.chat("Download the second one")

        assert provider.download_by_id_calls == ["f2"]

    def test_out_of_range_number_is_rejected(self, agent):
        provider = self._arm_memory(agent)

        response = agent.chat("Download number 9")

        assert "between 1 and 2" in response
        assert provider.download_by_id_calls == []

    def test_missing_memory_asks_for_search_first(self, agent):
        provider = FakeProvider(download_result=self.SUCCESS_DOWNLOAD)
        agent.router.google_drive = provider

        response = agent.chat("Download number 1")

        assert "search" in response.lower()
        assert provider.download_by_id_calls == []


# =========================================================
# AI AGENT - HEALTH MEMORY AND FOLLOW-UPS (MOCKED)
# =========================================================


class TestHealthMemory:

    def test_successful_health_report_is_remembered(self, agent):
        report = make_health_report()

        agent._remember_health_report(report)

        assert agent.last_health_report is report

    @pytest.mark.parametrize(
        "tool_data",
        [
            {"success": False, "tool": "health"},
            {"success": True, "tool": "storage"},
            {"success": True, "tool": "health", "data": "bad"},
            "not a dict",
        ],
    )
    def test_invalid_results_are_not_remembered(
        self,
        agent,
        tool_data,
    ):
        agent._remember_health_report(tool_data)

        assert agent.last_health_report is None

    def test_followup_question_uses_remembered_report(self, agent):
        agent._remember_health_report(make_health_report())

        response = agent.chat("Why is my score 86?")

        assert response == "FAKE AI RESPONSE"
        assert len(agent.ai.prompts) == 1
        assert "86" in agent.ai.prompts[0]

    def test_followup_shortcircuits_planner_and_router(self, agent):
        agent._remember_health_report(make_health_report())
        provider = FakeProvider(search_result={"success": True})
        agent.router.google_drive = provider

        def explode(message):
            raise AssertionError("Planner must not run for follow-ups")

        agent.planner.plan = explode

        agent.chat("Why is my score 86?")

        assert provider.search_calls == []


# =========================================================
# AI AGENT - LOCAL VS CLOUD END-TO-END (MOCKED)
# =========================================================


class TestAgentEndToEndRouting:

    def test_c_drive_warning_routes_to_local_storage(self, agent):
        drive = {
            "drive": "C:\\",
            "mount": "C:\\",
            "total_gb": 100.0,
            "used_gb": 95.0,
            "free_gb": 5.0,
            "percent_used": 95.0,
        }

        agent.router.storage_tool.get_drive_info = lambda: [drive]
        agent.router.storage_tool.get_temp_files_size = lambda: 50

        provider = FakeProvider(search_result={"success": True})
        agent.router.google_drive = provider

        response = agent.chat("Why is my C drive warning?")

        assert response == "FAKE AI RESPONSE"
        assert provider.search_calls == []
        assert len(agent.ai.prompts) == 1

        prompt = agent.ai.prompts[0]
        assert "Storage Analyzer" in prompt
        assert '"tool": "storage"' in prompt
        assert "C:\\" in prompt

    def test_google_drive_search_stays_cloud(self, agent):
        provider = FakeProvider(
            search_result={
                "success": True,
                "matches": [
                    {
                        "id": "f1",
                        "name": "invoice.pdf",
                        "mime_type": "pdf",
                        "size_bytes": 512,
                    },
                ],
            }
        )
        agent.router.google_drive = provider

        response = agent.chat("Search my Google Drive for invoices")

        assert provider.search_calls == ["invoices"]
        assert "invoice.pdf" in response
        assert agent.last_cloud_matches == [
            {
                "id": "f1",
                "name": "invoice.pdf",
                "mime_type": "pdf",
                "size_bytes": 512,
            }
        ]
        assert agent.ai.prompts == []

    def test_general_chat_goes_to_ai_with_original_message(self, agent):
        response = agent.chat("Tell me a joke")

        assert response == "FAKE AI RESPONSE"
        assert agent.ai.prompts == ["Tell me a joke"]

    def test_failed_tool_reports_reason(self, agent):
        class FailingBattery:
            def execute(self_inner):
                raise RuntimeError("sensor exploded")

        agent.router.battery_tool = FailingBattery()

        response = agent.chat("Check my battery health")

        assert "couldn't complete" in response.lower()
        assert "sensor exploded" in response
        assert agent.ai.prompts == []
