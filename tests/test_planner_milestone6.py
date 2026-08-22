"""Milestone 6 planner intents + Milestone 3 regressions."""

import pytest

from agent.planner import Planner


@pytest.fixture(scope="module")
def planner():
    return Planner()


def plan(planner, message):
    return planner.plan(message)


# =========================================================
# NEW MILESTONE 6 INTENTS
# =========================================================


class TestStorageIntelligenceIntents:

    def test_large_files_intent(self, planner):
        decision = plan(planner, "Find large files.")

        assert decision["tool"] == "large_files"
        assert decision["action"] == "scan"

    def test_largest_file_singular_intent(self, planner):
        assert (
            plan(planner, "What is my largest file?")["tool"]
            == "large_files"
        )

    def test_duplicate_intent(self, planner):
        decision = plan(planner, "Find duplicate files")

        assert decision["tool"] == "duplicates"

    def test_duplicates_show_intent(self, planner):
        assert (
            plan(planner, "Show me duplicate files")["tool"]
            == "duplicates"
        )

    def test_cleanup_preview_intent(self, planner):
        decision = plan(planner, "Show me cleanup candidates")

        assert decision["tool"] == "cleanup_preview"
        assert decision["action"] == "preview"

    def test_safely_cleaned_intent(self, planner):
        assert (
            plan(
                planner,
                "Show me what can be safely cleaned",
            )["tool"]
            == "cleanup_preview"
        )

    def test_free_up_space_intent(self, planner):
        assert (
            plan(planner, "How do I free up space?")["tool"]
            == "cleanup_preview"
        )

    def test_cleanup_delete_intent(self, planner):
        decision = plan(
            planner,
            "Delete the temporary files you found.",
        )

        assert decision["tool"] == "cleanup_delete"

    def test_junk_removal_intent_is_destructive_proposal(
        self,
        planner,
    ):
        assert (
            plan(planner, "Remove junk from my computer")[
                "tool"
            ]
            == "cleanup_delete"
        )


# =========================================================
# PRESERVED STORAGE / AMBIGUITY BEHAVIOR
# =========================================================


class TestPreservedStorageBehavior:

    @pytest.mark.parametrize(
        "message",
        [
            "How much space do I have?",
            "Why is my C drive full?",
            "Analyze my storage",
            "Clean up my local drive",
            "My drive is running out of space",
        ],
    )
    def test_storage_questions_stay_storage(
        self,
        planner,
        message,
    ):
        assert plan(planner, message)["tool"] == "storage"


# =========================================================
# TEMPERATURE NEVER MATCHES TEMP CLEANUP
# =========================================================


class TestTemperatureIsNotCleanup:

    @pytest.mark.parametrize(
        "message",
        [
            "Is my CPU temperature high?",
            "What is my processor temperature?",
            "The temperature outside is nice",
        ],
    )
    def test_temperature_routes_to_cpu_or_chat_not_cleanup(
        self,
        planner,
        message,
    ):
        tool = plan(planner, message)["tool"]

        assert tool not in {
            "cleanup_preview",
            "cleanup_delete",
            "duplicates",
            "large_files",
        }


# =========================================================
# MILESTONE 3 CLOUD REGRESSIONS
# =========================================================


class TestCloudRegressions:

    @pytest.mark.parametrize(
        "message,expected",
        [
            ("Search my Google Drive", "cloud_search"),
            ("Find report.pdf in Google Drive", "cloud_search"),
            ("Download report.pdf from Google Drive", "cloud_download"),
            ("Upload report.pdf to Google Drive", "cloud_upload"),
            ("Delete notes.txt from Google Drive", "cloud_delete"),
            ("Download report.pdf from drive", "cloud_download"),
            ("Search my drive for reports", "cloud_search"),
            ("Delete notes.txt from Drive", "cloud_delete"),
        ],
    )
    def test_cloud_routing_unchanged(
        self,
        planner,
        message,
        expected,
    ):
        assert plan(planner, message)["tool"] == expected

    def test_local_delete_never_becomes_cloud(self, planner):
        assert plan(
            planner, "Remove junk from my computer"
        )["tool"] == "cleanup_delete"

    @pytest.mark.parametrize(
        "message,expected",
        [
            ("Check my battery health", "battery"),
            ("How much RAM am I using?", "ram"),
            ("Is my CPU overheating?", "cpu"),
            ("System health check", "health"),
            ("Hello", "chat"),
        ],
    )
    def test_core_intents_unchanged(
        self,
        planner,
        message,
        expected,
    ):
        assert plan(planner, message)["tool"] == expected
