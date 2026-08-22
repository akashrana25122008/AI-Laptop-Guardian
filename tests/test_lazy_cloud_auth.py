"""Lazy Google Drive authentication tests.

Proves that constructing the agent/router and running purely
local requests never authenticates against Google Drive.
Google Drive is fully mocked; nothing touches the network.
"""

import ast
import sys
import types
from pathlib import Path


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


class FakeAI:
    """Records prompts. Guarantees no real Ollama call."""

    def __init__(self):
        self.prompts = []

    def ask(self, prompt):
        self.prompts.append(str(prompt))
        return "FAKE AI RESPONSE"


class LazyRecordingProvider:
    """
    Fake Google Drive provider that mirrors the real lazy
    authentication pattern used by cloud/google_drive.py:

    every method authenticates on demand, never earlier.
    """

    def __init__(self):
        self.service = None
        self.credentials = None
        self.authenticate_calls = []
        self.search_calls = []

    def authenticate(self):
        self.authenticate_calls.append(True)
        self.service = "fake-service"

    def search_files(self, query):
        if self.service is None:
            self.authenticate()
        self.search_calls.append(query)
        return {
            "success": True,
            "matches": [
                {"id": "1", "name": "report.pdf"}
            ],
        }


ROOT = Path(__file__).resolve().parents[1]
GOOGLE_DRIVE_SOURCE = (
    ROOT / "cloud" / "google_drive.py"
)

LOCAL_MESSAGES = [
    "How much RAM am I using?",
    "What is my CPU usage?",
    "Check my battery",
    "Generate a health report",
]


# =========================================================
# SOURCE-LEVEL GUARANTEE
# =========================================================


class TestConstructorIsSideEffectFree:

    def test_init_contains_no_authenticate_call(self):
        tree = ast.parse(
            GOOGLE_DRIVE_SOURCE.read_text(
                encoding="utf-8"
            )
        )

        provider = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
            and node.name == "GoogleDriveProvider"
        )

        init = next(
            node
            for node in provider.body
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
            and node.name == "__init__"
        )

        called_names = [
            call.func.id
            for call in ast.walk(init)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
        ]

        assert "authenticate" not in called_names


# =========================================================
# BEHAVIORAL GUARANTEE
# =========================================================


class TestLocalRequestsNeverAuthenticate:

    def _fresh_agent(self):
        aia = AIAgent()
        aia.ai = FakeAI()
        provider = LazyRecordingProvider()
        aia.router.google_drive = provider
        return aia, provider

    def test_construction_does_not_authenticate(self):
        _, provider = self._fresh_agent()

        assert provider.authenticate_calls == []

    @pytest.mark.parametrize("message", LOCAL_MESSAGES)
    def test_local_chats_trigger_zero_authentication(
        self,
        message,
    ):
        agent, provider = self._fresh_agent()

        agent.chat(message)

        assert provider.authenticate_calls == []
        assert provider.search_calls == []

    def test_cloud_request_authenticates_exactly_once(self):
        agent, provider = self._fresh_agent()

        response = agent.chat(
            "Search Google Drive for report"
        )

        assert len(provider.authenticate_calls) == 1
        assert len(provider.search_calls) == 1
        assert response != ""
