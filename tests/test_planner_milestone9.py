"""Milestone 9 - planner routing for account management.

Covers:

    - connect / list / disconnect intents route to the
      three new tools,
    - selectors (account numbers, emails) are extracted
      exactly and never guessed,
    - ordinary file requests mentioning accounts KEEP
      their Milestone 5-8 routing,
    - local topics, cleanup, and chat are unaffected.

The planner never triggers authentication itself; it
only classifies intent.
"""

import pytest

from agent.planner import Planner


@pytest.fixture(scope="module")

def planner():
    return Planner()


# =========================================================
# CONNECT INTENT
# =========================================================


class TestConnectRouting:

    @pytest.mark.parametrize(
        "message",
        [
            "Connect my Google Drive",
            "connect google drive",
            "Add another Google account",
            "add a new Google account please",
            "Link my Google Drive",
        ],
    )

    def test_connect_phrases(self, planner, message):

        decision = planner.plan(message)

        assert decision["tool"] == "cloud_connect"


# =========================================================
# LIST INTENT
# =========================================================


class TestListRouting:

    @pytest.mark.parametrize(
        "message",
        [
            "Show my connected accounts",
            "List my connected Google accounts",
            "What Google accounts do I have?",
            "Which accounts are connected?",
            "show signed in accounts",
            "display my accounts",
        ],
    )

    def test_list_phrases(self, planner, message):

        decision = planner.plan(message)

        assert decision["tool"] == "cloud_accounts"


# =========================================================
# DISCONNECT INTENT AND SELECTORS
# =========================================================


class TestDisconnectRouting:

    def test_disconnect_by_account_number(
        self, planner
    ):
        decision = planner.plan(
            "Disconnect account 2"
        )

        assert decision["tool"] == "cloud_disconnect"

        assert decision["selector"] == "2"

    def test_disconnect_by_email(self, planner):

        decision = planner.plan(
            "Disconnect user@example.com"
        )

        assert decision["tool"] == "cloud_disconnect"

        assert (
            decision["selector"]
            == "user@example.com"
        )

    @pytest.mark.parametrize(
        "message",
        [
            "Sign out of Google",
            "Unlink my Google account",
            "log out of gdrive",
        ],
    )

    def test_disconnect_phrases_without_selector(
        self, planner, message
    ):
        decision = planner.plan(message)

        assert decision["tool"] == "cloud_disconnect"

        # No selector: the agent must ask which account,
        # never guess one.

        assert decision.get("selector") is None


# =========================================================
# NON-INTERFERENCE WITH FILE ROUTING
# =========================================================


class TestFileRequestsUnaffected:

    def test_search_with_account_ref(self, planner):

        decision = planner.plan(
            "Search account 2 for report.pdf"
        )

        assert decision["tool"] == "cloud_search"

    def test_list_files_in_account_stays_large_files(
        self, planner
    ):
        decision = planner.plan(
            "List files larger than 100MB in account 2"
        )

        assert decision["tool"] == "cloud_large_files"

    def test_delete_with_account_ref(self, planner):

        decision = planner.plan(
            "Delete report.pdf from account 2"
        )

        assert decision["tool"] == "cloud_delete"

    def test_download_from_google_drive(
        self, planner
    ):
        decision = planner.plan(
            "Download backup.zip from Google Drive"
        )

        assert decision["tool"] == "cloud_download"

    def test_upload_to_google_drive(self, planner):

        decision = planner.plan(
            "Upload notes.txt to Google Drive"
        )

        assert decision["tool"] == "cloud_upload"

    def test_storage_question_stays_cloud_storage(
        self, planner
    ):
        decision = planner.plan(
            "How much storage do I have across "
            "my Google accounts?"
        )

        assert decision["tool"] == "cloud_storage"


# =========================================================
# UNRELATED REQUESTS
# =========================================================


class TestOtherIntents:

    def test_local_cpu_question(self, planner):

        decision = planner.plan("What is my CPU usage?")

        assert decision["tool"] == "cpu"

    def test_cleanup_intent_unchanged(self, planner):

        decision = planner.plan(
            "Clean up temp files"
        )

        assert decision["tool"] in {
            "cleanup_preview",
            "cleanup_delete",
        }

    def test_plain_chat(self, planner):

        decision = planner.plan("hello there")

        assert decision["tool"] == "chat"

    def test_battery_question(self, planner):

        decision = planner.plan(
            "How is my battery doing?"
        )

        assert decision["tool"] == "battery"
