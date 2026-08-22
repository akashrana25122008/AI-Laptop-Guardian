"""End-to-end confirmation safety for Google Drive deletion.

Proves that no provider.delete call can occur from natural
language alone. Google Drive is fully mocked; nothing in this
file touches the network or real credentials.
"""

import sys
import types


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


# =========================================================
# FAKES
# =========================================================


class RecordingProvider:
    """
    Fake Google Drive provider.

    Records every mutating call so tests can PROVE that no
    deletion happens before confirmation.
    """

    def __init__(self, matches=None, delete_result=None):
        self.matches = matches if matches is not None else []
        self.delete_result = (
            delete_result
            if delete_result is not None
            else {"success": True}
        )
        self.search_calls = []
        self.delete_by_id_calls = []

    def search_files(self, query):
        self.search_calls.append(query)
        return {
            "success": True,
            "matches": list(self.matches),
        }

    def delete_file_by_id(self, file_id):
        self.delete_by_id_calls.append(file_id)
        return dict(
            self.delete_result,
            data={
                "file_id": file_id,
                "name": "deleted",
            },
            message=(
                f"Successfully deleted file {file_id} "
                f"from Google Drive."
            ),
        )


def make_provider(matches=None, delete_result=None):
    return RecordingProvider(matches, delete_result)


class FakeAI:
    """Records prompts. Guarantees no real Ollama call."""

    def __init__(self):
        self.prompts = []

    def ask(self, prompt):
        self.prompts.append(str(prompt))
        return "FAKE AI RESPONSE"


@pytest.fixture()
def agent():
    aia = AIAgent()
    aia.ai = FakeAI()
    return aia


# =========================================================
# PART 7A - DELETE CONFIRMATION BOUNDARY
# =========================================================


class TestDeleteRequiresConfirmation:

    def test_natural_language_never_deletes_immediately(
        self,
        agent,
    ):
        provider = make_provider(
            matches=[{"id": "f1", "name": "notes.txt"}]
        )
        agent.router.google_drive = provider

        response = agent.chat(
            "delete notes.txt from Google Drive"
        )

        # Proof: the provider never saw a delete call.
        assert provider.delete_by_id_calls == []
        assert agent.safety.has_pending() is True

    def test_proposal_describes_target_and_destructiveness(
        self,
        agent,
    ):
        provider = make_provider(
            matches=[{"id": "f1", "name": "notes.txt"}]
        )
        agent.router.google_drive = provider

        response = agent.chat("delete notes.txt from Drive")

        assert "notes.txt" in response
        assert "destructive" in response.lower()
        assert "confirm" in response.lower()
        assert "cancel" in response.lower()

    def test_valid_confirmation_deletes_intended_target(
        self,
        agent,
    ):
        provider = make_provider(
            matches=[{"id": "f1", "name": "notes.txt"}]
        )
        agent.router.google_drive = provider

        agent.chat("delete notes.txt from Drive")
        response = agent.chat("confirm delete")

        assert provider.delete_by_id_calls == ["f1"]
        assert "deleted" in response.lower()

    def test_confirmation_is_single_use(self, agent):
        provider = make_provider(
            matches=[{"id": "f1", "name": "notes.txt"}]
        )
        agent.router.google_drive = provider

        agent.chat("delete notes.txt from Drive")
        agent.chat("yes")

        assert agent.safety.has_pending() is False

        second = agent.chat("yes")

        # Expired confirmation cannot trigger another delete.
        assert provider.delete_by_id_calls == ["f1"]
        assert second != ""

    def test_cancellation_prevents_deletion(self, agent):
        provider = make_provider(
            matches=[{"id": "f1", "name": "notes.txt"}]
        )
        agent.router.google_drive = provider

        agent.chat("delete notes.txt from Drive")
        response = agent.chat("cancel")

        assert provider.delete_by_id_calls == []
        assert agent.safety.has_pending() is False
        assert "cancel" in response.lower()

    def test_unrelated_message_expires_pending_safely(
        self,
        agent,
    ):
        provider = make_provider(
            matches=[{"id": "f1", "name": "notes.txt"}]
        )
        agent.router.google_drive = provider

        agent.chat("delete notes.txt from Drive")
        agent.chat("how much RAM am I using?")

        # Stale confirmation expired; a later bare 'yes'
        # must NOT resurrect it.
        assert provider.delete_by_id_calls == []

        agent.chat("yes")

        assert provider.delete_by_id_calls == []
        assert agent.safety.has_pending() is False

    def test_confirmation_cannot_authorize_different_file(
        self,
        agent,
    ):
        provider = make_provider(
            matches=[{"id": "id-A", "name": "a.txt"}]
        )
        agent.router.google_drive = provider

        agent.chat("delete a.txt from Drive")

        # User now targets a different file; the unrelated
        # message expires the old proposal and a new one is
        # created for b.txt.
        provider.matches = [{"id": "id-B", "name": "b.txt"}]
        agent.chat("delete b.txt from Drive")
        agent.chat("confirm")

        # Only the newly confirmed target may be deleted.
        assert provider.delete_by_id_calls == ["id-B"]

    def test_zero_matches_stay_safe(self, agent):
        provider = make_provider(matches=[])
        agent.router.google_drive = provider

        response = agent.chat("delete ghost.txt from Drive")

        assert provider.delete_by_id_calls == []
        assert agent.safety.has_pending() is False
        assert "no files were changed" in response.lower()

    def test_multiple_matches_stay_safe(self, agent):
        provider = make_provider(
            matches=[
                {"id": "1", "name": "notes.txt"},
                {"id": "2", "name": "notes copy.txt"},
            ]
        )
        agent.router.google_drive = provider

        response = agent.chat("delete notes.txt from Drive")

        assert provider.delete_by_id_calls == []
        assert agent.safety.has_pending() is False
        assert "nothing has been deleted" in response.lower()
        assert "notes.txt" in response
        assert "notes copy.txt" in response

    def test_empty_query_never_touches_provider(self, agent):
        provider = make_provider(matches=[])
        agent.router.google_drive = provider

        # Planner can produce an empty query; propose must
        # refuse before any search or delete happens.
        response = agent._propose_cloud_delete("")

        assert "exact name" in response.lower()
        assert provider.search_calls == []
        assert provider.delete_by_id_calls == []
        assert agent.safety.has_pending() is False

    def test_failed_search_does_not_delete(self, agent):
        class BrokenSearchProvider(RecordingProvider):
            def search_files(self, query):
                self.search_calls.append(query)
                return {
                    "success": False,
                    "error": "drive offline",
                }

        provider = BrokenSearchProvider()
        agent.router.google_drive = provider

        response = agent.chat("delete notes.txt from Drive")

        assert provider.delete_by_id_calls == []
        assert "couldn't" in response.lower()


# =========================================================
# ROUTER CONFIRMED-DELETE ENTRY POINT
# =========================================================


class TestRouterConfirmedDelete:

    def test_empty_file_id_rejected_without_provider_call(self):
        router = ToolRouter()
        provider = make_provider()
        router.google_drive = provider

        result = router.execute_delete_by_id("   ")

        assert result["success"] is False
        assert provider.delete_by_id_calls == []

    def test_confirmed_delete_uses_exact_id_once(self):
        router = ToolRouter()
        provider = make_provider()
        router.google_drive = provider

        result = router.execute_delete_by_id("xyz", "n.txt")

        assert result["success"] is True
        assert provider.delete_by_id_calls == ["xyz"]

    def test_failed_delete_returns_failure_result(self):
        router = ToolRouter()

        class FailingProvider:
            def delete_file_by_id(self, file_id):
                raise RuntimeError("api error")

        router.google_drive = FailingProvider()

        result = router.execute_delete_by_id("xyz")

        assert result["success"] is False
        assert "api error" in result["error"]
