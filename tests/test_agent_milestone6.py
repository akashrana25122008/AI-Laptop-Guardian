"""Agent-level storage intelligence dispatch tests.

Cloud boundary is stubbed, Ollama is faked; everything is
local and offline.
"""

import sys
import types


def _install_cloud_stub() -> None:
    module = types.ModuleType("cloud.google_drive")

    class StubGoogleDriveProvider:
        def __init__(self, *args, **kwargs):
            self.service = None
            self.credentials = None

    module.GoogleDriveProvider = StubGoogleDriveProvider
    sys.modules["cloud.google_drive"] = module


_install_cloud_stub()

import pytest  # noqa: E402

from agent.ai_agent import AIAgent  # noqa: E402
from agent.tool_router import ToolRouter  # noqa: E402


class FakeAI:
    def __init__(self):
        self.prompts = []

    def ask(self, prompt):
        self.prompts.append(str(prompt))
        return "FAKE AI RESPONSE"


@pytest.fixture()
def agent(monkeypatch, tmp_path):
    monkeypatch.setenv("TEMP", str(tmp_path))

    aia = AIAgent()
    aia.ai = FakeAI()

    return aia


# =========================================================
# STORAGE DISPATCH (UNCHANGED BEHAVIOR)
# =========================================================


class TestStorageDispatch:

    def test_storage_request_reaches_ai_with_data(
        self,
        agent,
    ):
        agent.router.storage_tool.get_drive_info = (
            lambda: [
                {
                    "drive": "C:",
                    "mount": "C:\\",
                    "total_gb": 100.0,
                    "used_gb": 25.0,
                    "free_gb": 75.0,
                    "percent_used": 25.0,
                    "status": "Healthy",
                }
            ]
        )
        agent.router.storage_tool.get_temp_files_size = (
            lambda: {
                "user_temp_gb": 0.5,
                "windows_temp_gb": 1.0,
            }
        )

        response = agent.chat(
            "How much space do I have?"
        )

        assert response == "FAKE AI RESPONSE"
        assert len(agent.ai.prompts) == 1
        assert "<tool_data>" in agent.ai.prompts[0]
        assert "total_gb" in agent.ai.prompts[0]

    def test_storage_failure_is_normalized(self, agent):
        def broken():
            raise OSError("drive unreadable")

        agent.router.storage_tool.get_drive_info = broken

        response = agent.chat("How much space do I have?")

        # Tool failures never reach the AI: deterministic
        # failure message instead.

        assert "couldn't complete" in response.lower()
        assert "drive unreadable" in response
        assert agent.ai.prompts == []


# =========================================================
# LARGE FILES + DUPLICATES DISPATCH
# =========================================================


class TestIntelligenceDispatch:

    def test_large_files_dispatch(self, agent):
        agent.router.large_file_scanner.scan = (
            lambda folders=None: [
                {
                    "name": "movie.bin",
                    "path": "X:\\movie.bin",
                    "size_gb": 4.0,
                    "size_mb": 4096.0,
                    "size_bytes": 4 * 1024 ** 3,
                }
            ]
        )

        response = agent.chat("Find large files")

        assert response == "FAKE AI RESPONSE"
        prompt = agent.ai.prompts[0]
        assert "movie.bin" in prompt
        assert "<tool_data>" in prompt

    def test_duplicates_dispatch(self, agent):
        agent.router.duplicate_scanner.scan = lambda: {
            "success": True,
            "tool": "duplicates",
            "data": {
                "groups": [],
                "group_count": 0,
                "duplicate_files": 0,
                "wasted_bytes": 0,
                "wasted_mb": 0.0,
                "scanned_files": 5,
                "skipped_sensitive": 0,
                "inaccessible": 0,
            },
        }

        response = agent.chat("Find duplicate files")

        assert response == "FAKE AI RESPONSE"
        prompt = agent.ai.prompts[0]
        assert "Duplicate File Scanner" in prompt

    def test_large_files_failure_never_fakes_success(
        self,
        agent,
    ):
        def broken():
            raise RuntimeError("boom")

        monkey_broken = broken

        agent.router.large_file_scanner.scan = (
            monkey_broken
        )

        result = agent.router.execute("large_files")

        assert result["success"] is False
        assert "boom" in result["error"]


# =========================================================
# ROUTER NORMALIZATION FOR NEW TOOLS
# =========================================================


class TestRouterNormalization:

    def test_cleanup_preview_contract(self, agent, tmp_path):
        agent.router.cleanup_preview_tool.user_temp = (
            str(tmp_path)
        )

        result = agent.router.execute("cleanup_preview")

        assert result["success"] is True
        assert result["tool"] == "cleanup_preview"
        assert "candidates" in result["data"]

    def test_unknown_tool_still_fails_normally(self):
        router = ToolRouter()

        result = router.execute("no_such_tool")

        assert result["success"] is False
        assert "Unknown tool" in result["error"]

    def test_confirmed_cleanup_requires_items(self):
        router = ToolRouter()

        result = router.execute_cleanup_deletion([])

        assert result["success"] is False
        assert "approved" in result["error"].lower()


# =========================================================
# EXISTING BEHAVIOR REMAINS INTACT
# =========================================================


class TestExistingBehaviorIntact:

    def test_health_memory_still_works(self, agent):
        report = {
            "success": True,
            "tool": "health",
            "data": {"overall_score": 90},
        }

        agent._remember_health_report(report)

        assert agent.last_health_report is report

        non_health = {"success": True, "tool": "ram"}

        agent._remember_health_report(non_health)

        assert agent.last_health_report is report

    def test_numbered_download_detection_intact(self, agent):
        # Phrase-based detection (memory is checked later
        # during selection, exactly as before Milestone 6).

        assert (
            agent._is_download_selection("download number 1")
            is True
        )
        assert (
            agent._is_download_selection("download the second")
            is True
        )
        assert (
            agent._is_download_selection("hello there")
            is False
        )
        assert (
            agent._is_download_selection(
                "find large files"
            )
            is False
        )

    def test_cloud_delete_confirmation_flow_untouched(
        self,
        agent,
    ):
        class FakeProvider:
            def __init__(self):
                self.deleted = []

            def search_files(self, query):
                return {
                    "success": True,
                    "matches": [
                        {"id": "abc", "name": "n.txt"}
                    ],
                }

            def delete_file_by_id(self, file_id):
                self.deleted.append(file_id)
                return {"success": True}

        provider = FakeProvider()
        agent.router.google_drive = provider

        agent.chat("Delete n.txt from Google Drive")
        agent.chat("confirm delete")

        assert provider.deleted == ["abc"]
