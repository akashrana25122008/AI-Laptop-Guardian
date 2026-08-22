"""Deterministic intent routing tests for Planner.

These tests never touch the network, the file system,
or any Google Drive service.
"""

import pytest

from agent.planner import Planner


@pytest.fixture(scope="module")
def planner():
    return Planner()


def tool_of(planner, message):
    return planner.plan(message)["tool"]


# =========================================================
# 1. NORMAL INTENTS
# =========================================================


class TestNormalIntents:

    def test_storage_analysis(self, planner):
        assert tool_of(planner, "Analyze my storage") == "storage"

    def test_battery_health(self, planner):
        assert (
            tool_of(planner, "Check my battery health")
            == "battery"
        )

    def test_ram_usage(self, planner):
        assert tool_of(planner, "How much RAM am I using?") == "ram"

    def test_cpu_temperature(self, planner):
        assert tool_of(planner, "Is my CPU overheating?") == "cpu"

    def test_general_chat(self, planner):
        assert tool_of(planner, "Hello there") == "chat"

    def test_empty_message_falls_back_to_chat(self, planner):
        assert tool_of(planner, "") == "chat"


# =========================================================
# 2. LOCAL STORAGE VS GOOGLE DRIVE AMBIGUITY
# =========================================================


class TestLocalStorageVersusGoogleDrive:

    @pytest.mark.parametrize(
        "message",
        [
            "Why is my C drive warning?",
            "Why is my C drive full?",
            "How much space is left on C drive?",
            "What is using space on my D drive?",
            "Is my disk healthy?",
            "Check my storage",
            "How much free space do I have?",
            "My hard disk is almost full",
            "Is my SSD failing?",
            "Clean up my local drive",
        ],
    )
    def test_local_drive_questions_route_to_storage(
        self,
        planner,
        message,
    ):
        decision = planner.plan(message)

        assert decision["tool"] == "storage"

    @pytest.mark.parametrize(
        "message",
        [
            "Search my Google Drive",
            "Search my Google Drive for invoices",
            "Find my files in Google Drive",
            "Find report.pdf in Google Drive",
            "Download a file from Google Drive",
            "Download report.pdf from Google Drive",
            "Upload report.pdf to Google Drive",
            "Backup report.pdf to Google Drive",
            "Delete upload_test_2.txt from Google Drive",
            "Remove test.txt from Google Drive",
        ],
    )
    def test_google_drive_requests_stay_cloud(
        self,
        planner,
        message,
    ):
        decision = planner.plan(message)

        assert decision["tool"].startswith("cloud_")

    def test_local_question_is_not_mistaken_for_cloud_search(
        self,
        planner,
    ):
        decision = planner.plan("Why is my C drive warning?")

        assert decision["tool"] != "cloud_search"

    def test_local_delete_request_never_routes_to_cloud_delete(
        self,
        planner,
    ):
        decision = planner.plan("Delete old files from my C drive")

        assert decision["tool"] != "cloud_delete"


# =========================================================
# 3. CPU / RAM / BATTERY / HEALTH ROUTING
# =========================================================


class TestComponentRouting:

    @pytest.mark.parametrize(
        "message,expected",
        [
            ("How is my battery doing?", "battery"),
            ("Am I still charging?", "battery"),
            ("What is my processor temperature?", "cpu"),
            ("Is my memory usage high?", "ram"),
            ("System health check", "health"),
            ("Is my laptop healthy?", "health"),
            ("Give me a health report", "health"),
            ("Anything wrong with my laptop?", "health"),
        ],
    )
    def test_component_routing(self, planner, message, expected):
        assert tool_of(planner, message) == expected


# =========================================================
# 4. FILE INSPECTOR ROUTING
# =========================================================


class TestFileInspectorRouting:

    def test_whats_in_file(self, planner):
        decision = planner.plan("What's in report.txt?")

        assert decision["tool"] == "file_inspector"
        assert decision["action"] == "inspect"
        assert decision["path"] == "report.txt"

    def test_contents_of_file(self, planner):
        decision = planner.plan("Show me the contents of log.txt")

        assert decision["tool"] == "file_inspector"

    def test_errors_in_log_file(self, planner):
        decision = planner.plan("Are there any errors in app.log?")

        assert decision["tool"] == "file_inspector"


# =========================================================
# 5. GOOGLE DRIVE QUERY EXTRACTION
# =========================================================


class TestGoogleDriveExtraction:

    def test_search_query_extracted(self, planner):
        decision = planner.plan("Search my Google Drive for invoices")

        assert decision["tool"] == "cloud_search"
        assert decision["query"] == "invoices"

    def test_download_query_extracted(self, planner):
        decision = planner.plan("Download report.pdf from Google Drive")

        assert decision["tool"] == "cloud_download"
        assert decision["query"] == "report.pdf"

    def test_upload_path_extracted(self, planner):
        decision = planner.plan("Upload my report.pdf to Google Drive")

        assert decision["tool"] == "cloud_upload"
        assert decision["path"] == "report.pdf"

    def test_delete_query_extracted(self, planner):
        decision = planner.plan(
            "Delete upload_test_2.txt from Google Drive"
        )

        assert decision["tool"] == "cloud_delete"
        assert decision["query"] == "upload_test_2.txt"


# =========================================================
# 6. AMBIGUOUS BARE DRIVE REQUESTS
# =========================================================


class TestAmbiguousBareDriveRequests:

    def test_bare_drive_download_stays_cloud(self, planner):
        decision = planner.plan("Download report.pdf from drive")

        assert decision["tool"] == "cloud_download"

    def test_bare_drive_upload_stays_cloud(self, planner):
        decision = planner.plan("Upload notes.txt to my drive")

        assert decision["tool"] == "cloud_upload"

    def test_bare_drive_delete_stays_cloud(self, planner):
        decision = planner.plan("Delete notes.txt from Drive")

        assert decision["tool"] == "cloud_delete"

    def test_bare_drive_search_stays_cloud(self, planner):
        decision = planner.plan("Search my drive for reports")

        assert decision["tool"] == "cloud_search"

    def test_bare_drive_without_verb_routes_local(self, planner):
        decision = planner.plan("My drive is running out of space")

        assert decision["tool"] == "storage"


# =========================================================
# 7. UNKNOWN / GENERAL CHAT REQUESTS
# =========================================================


class TestGeneralChatRouting:

    @pytest.mark.parametrize(
        "message",
        [
            "Tell me a joke",
            "What is the capital of France?",
            "Good morning",
            "Who are you?",
        ],
    )
    def test_unrelated_messages_route_to_chat(
        self,
        planner,
        message,
    ):
        assert tool_of(planner, message) == "chat"


# =========================================================
# 8. REGRESSION CASES (EXISTING MANUAL SCRIPT)
# =========================================================


class TestRegressionBehavior:

    @pytest.mark.parametrize(
        "message,expected",
        [
            ("Analyze my storage", "storage"),
            ("Why is my C drive full?", "storage"),
            ("Check my battery health", "battery"),
            ("How much RAM am I using?", "ram"),
            ("Is my CPU overheating?", "cpu"),
            ("Hello", "chat"),
        ],
    )
    def test_legacy_manual_script_questions(
        self,
        planner,
        message,
        expected,
    ):
        assert tool_of(planner, message) == expected

    def test_plan_result_is_dict_with_tool(self, planner):
        decision = planner.plan("check storage")

        assert isinstance(decision, dict)
        assert "tool" in decision
