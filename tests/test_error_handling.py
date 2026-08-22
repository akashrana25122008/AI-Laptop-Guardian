"""Error handling and normalization tests for ToolRouter
and AIAgent.

Google Drive is replaced by an offline stub before the agent
modules are imported. No test authenticates with, reads
credentials for, or performs any real cloud operation.
"""

import sys
import types


# =========================================================
# OFFLINE GOOGLE DRIVE BOUNDARY
# =========================================================


def _install_cloud_stub() -> None:
    module = types.ModuleType("cloud.google_drive")

    class StubGoogleDriveProvider:
        authenticated = False

        def __init__(self, *args, **kwargs):
            self.service = None
            self.credentials = None

    module.GoogleDriveProvider = StubGoogleDriveProvider
    sys.modules["cloud.google_drive"] = module


_install_cloud_stub()

import pytest  # noqa: E402

from agent.ai_agent import AIAgent  # noqa: E402
from agent.tool_router import ToolRouter  # noqa: E402
from tools.cleanup.cleanup import CleanupTool  # noqa: E402


# =========================================================
# FAKES
# =========================================================


class FakeAI:
    def __init__(self):
        self.prompts = []

    def ask(self, prompt):
        self.prompts.append(str(prompt))
        return "FAKE AI RESPONSE"


class ExplodingProvider:
    """Simulates a provider whose network layer raises."""

    def search_files(self, query):
        raise ConnectionError("network unreachable")

    def upload_file(self, local_path):
        raise TimeoutError("upload timed out")

    def download_file(self, query):
        raise RuntimeError("drive exploded")

    def download_file_by_id(self, file_id):
        raise RuntimeError("drive exploded")

    def delete_file_by_id(self, file_id):
        raise RuntimeError("drive exploded")


class StaticProvider:
    """Returns canned results regardless of input."""

    def __init__(self, result):
        self.result = result

    def search_files(self, query):
        return self.result

    def upload_file(self, local_path):
        return self.result

    def download_file(self, query):
        return self.result


@pytest.fixture()
def router():
    return ToolRouter()


@pytest.fixture()
def agent():
    aia = AIAgent()
    aia.ai = FakeAI()
    return aia


# =========================================================
# TOOL ROUTER FAILURE HANDLING
# =========================================================


class TestRouterFailureHandling:

    @pytest.mark.parametrize(
        "tool_name",
        ["cloud_search", "cloud_upload", "cloud_download"],
    )
    def test_provider_exceptions_become_failure_results(
        self,
        router,
        tool_name,
    ):
        router.google_drive = ExplodingProvider()

        result = router.execute(tool_name, "whatever")

        assert result["success"] is False
        assert result["tool"] == tool_name
        assert isinstance(result["error"], str)
        assert result["error"]

    def test_cloud_delete_exception_is_caught(self, router):
        provider = ExplodingProvider()
        provider.search_files = lambda query: {
            "success": True,
            "matches": [{"id": "x", "name": "n"}],
        }
        router.google_drive = provider

        result = router.execute("cloud_delete", "n")

        assert result["success"] is False
        assert result["tool"] == "cloud_delete"
        assert "exploded" in result["error"]

    def test_non_dict_tool_output_is_wrapped_as_failure(
        self,
        router,
    ):
        router.battery_tool.execute = lambda: "battery is fine"

        result = router.execute("battery")

        assert result["success"] is False
        assert result["tool"] == "battery"
        assert "unexpected" in result["error"].lower()

    def test_dict_without_success_key_is_wrapped(self, router):
        router.ram_tool.execute = lambda: {"usage_percent": 50}

        result = router.execute("ram")

        assert result["success"] is False
        assert result["tool"] == "ram"
        assert result["data"] == {"usage_percent": 50}

    def test_failure_without_error_gets_message_fallback(
        self,
        router,
    ):
        router.health_tool.execute = lambda: {
            "success": False,
            "tool": "health",
            "message": "sensors unavailable",
        }

        result = router.execute("health")

        assert result["success"] is False
        assert result["error"] == "sensors unavailable"
        # Original message field preserved.
        assert result["message"] == "sensors unavailable"

    def test_successful_results_pass_through_unchanged(
        self,
        router,
    ):
        sentinel = {"success": True, "tool": "cpu", "data": {}}
        router.cpu_tool.execute = lambda: sentinel

        assert router.execute("cpu") is sentinel

    def test_valid_success_with_no_error_field_kept_intact(
        self,
        router,
    ):
        sentinel = {
            "success": False,
            "tool": "battery",
            "error": "Battery not detected.",
        }
        router.battery_tool.execute = lambda: sentinel

        assert router.execute("battery") is sentinel

    def test_long_errors_are_truncated_in_results(self, router):
        router.cpu_tool.execute = lambda: (_ for _ in ()).throw(
            RuntimeError("y" * 900)
        )

        result = router.execute("cpu")

        assert len(result["error"]) <= 300


# =========================================================
# CLEANUP RESULT CONSISTENCY
# =========================================================


class TestCleanupResultConsistency:

    def test_missing_temp_reports_explicit_error(
        self,
        monkeypatch,
    ):
        monkeypatch.delenv("TEMP", raising=False)

        result = CleanupTool().scan()

        assert result["success"] is False
        assert result["error"]
        # Backward-compatible message kept.
        assert result["message"]

    def test_preview_propagates_normalized_scan_failure(
        self,
        monkeypatch,
    ):
        monkeypatch.delenv("TEMP", raising=False)

        result = CleanupTool().preview()

        assert result["success"] is False
        assert result["error"]


# =========================================================
# AI AGENT FAILURE HANDLING
# =========================================================


class TestAgentFailureHandling:

    def test_failed_tool_never_reaches_ollama(self, agent):
        agent.router.battery_tool.execute = lambda: {
            "success": False,
            "tool": "battery",
            "error": "no battery present",
        }

        response = agent.chat("Check my battery health")

        assert "couldn't complete" in response.lower()
        assert "no battery present" in response
        assert agent.ai.prompts == []

    def test_raising_tool_never_reaches_ollama(self, agent):
        def explode():
            raise RuntimeError("sensor gone")

        agent.router.battery_tool.execute = explode

        response = agent.chat("Check my battery health")

        assert "couldn't complete" in response.lower()
        assert "sensor gone" in response
        assert agent.ai.prompts == []

    def test_malformed_router_output_never_reaches_ollama(
        self,
        agent,
    ):
        class BrokenRouter:
            def execute(self_inner, tool, argument=None):
                return 12345

        agent.router = BrokenRouter()

        response = agent.chat("Check my battery health")

        assert "couldn't complete" in response.lower()
        assert agent.ai.prompts == []

    def test_failed_storage_request_stays_safe(self, agent):
        def broken_info():
            raise OSError("disk unreadable")

        agent.router.storage_tool.get_drive_info = broken_info

        response = agent.chat("Why is my C drive warning?")

        assert "couldn't complete" in response.lower()
        assert agent.ai.prompts == []


# =========================================================
# CLOUD DELETE USER-FACING FORMAT (MOCKED)
# =========================================================


class TestCloudDeleteUserFacingFormat:

    def test_single_match_delete_shows_message_not_raw_dict(
        self,
        agent,
    ):
        provider = StaticProvider({"success": True})
        provider.search_files = lambda query: {
            "success": True,
            "matches": [{"id": "abc", "name": "notes.txt"}],
        }
        provider.delete_file_by_id = (
            lambda file_id: {"success": True}
        )
        agent.router.google_drive = provider

        response = agent.chat(
            "Delete notes.txt from Google Drive"
        )

        assert isinstance(response, str)
        assert "notes.txt" in response
        assert "Successfully deleted" in response
        # Raw internal result must not be dumped to the user.
        assert "'success': True" not in response
        assert agent.ai.prompts == []
