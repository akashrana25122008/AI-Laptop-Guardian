"""Milestone 8 - Planner cloud intelligence intents.

Storage questions route to the new read-only analytics
tools while every Milestone 1-7 intent keeps its exact
behavior, including cleanup precedence.
"""

import pytest

from agent.planner import Planner


@pytest.fixture()
def planner():
    return Planner()


# =========================================================
# CLOUD STORAGE QUOTA / SUMMARY
# =========================================================


class TestCloudStorageIntent:

    @pytest.mark.parametrize(
        "message",
        [
            "How much Google Drive storage do I have?",
            "How much space is left across my Google "
            "accounts?",
            "Which account has the most free space?",
            "Give me a storage report for all my "
            "accounts.",
            "What is my Google Drive quota?",
        ],
    )
    def test_storage_questions_route_to_cloud_storage(
        self,
        planner,
        message,
    ):
        decision = planner.plan(message)

        assert decision["tool"] == "cloud_storage"

    def test_explicit_account_selector_is_captured(
        self,
        planner,
    ):
        decision = planner.plan("How much storage does account 2 have on "
            "Google Drive?"
        )

        assert decision["tool"] == "cloud_storage"

    def test_local_storage_question_still_routes_to_storage(
        self,
        planner,
    ):
        for message in [
            "Check D drive space",
            "Analyze my storage",
            "Check C drive usage",
        ]:

            decision = planner.plan(message)

            assert decision["tool"] == "storage", (
                message
            )


# =========================================================
# LARGE FILES
# =========================================================


class TestLargeFilesIntent:

    def test_largest_files_default_threshold(
        self,
        planner,
    ):
        decision = planner.plan("Find my largest files in Google Drive."
        )

        assert (
            decision["tool"] == "cloud_large_files"
        )
        assert decision.get("min_mb") is None

    def test_mb_threshold_parsed(
        self,
        planner,
    ):
        decision = planner.plan("Show me files larger than 500 MB in "
            "Google Drive"
        )

        assert (
            decision["tool"] == "cloud_large_files"
        )
        assert decision["min_mb"] == 500.0

    def test_gb_threshold_converted_to_mb(
        self,
        planner,
    ):
        decision = planner.plan("files larger than 1 GB in google drive"
        )

        assert (
            decision["tool"] == "cloud_large_files"
        )
        assert decision["min_mb"] == 1024.0

    def test_tb_threshold_converted_to_mb(
        self,
        planner,
    ):
        decision = planner.plan("show files larger than 1 TB in Google "
            "Drive"
        )

        assert (
            decision["tool"] == "cloud_large_files"
        )
        assert decision["min_mb"] == (
            1024.0 * 1024.0
        )


# =========================================================
# DUPLICATES + OVERVIEW
# =========================================================


class TestDuplicatesAndOverview:

    def test_duplicate_candidates_intent(
        self,
        planner,
    ):
        decision = planner.plan("Show me possible duplicate files across my "
            "Google Drives."
        )

        assert decision["tool"] == "cloud_duplicates"

    def test_unified_overview_intent(
        self,
        planner,
    ):
        decision = planner.plan("Show me a local and cloud storage overview"
        )

        assert (
            decision["tool"] == "storage_overview"
        )


# =========================================================
# MILESTONE 1-7 REGRESSIONS
# =========================================================


class TestLegacyRoutingUnchanged:

    @pytest.mark.parametrize(
        "message,expected_tool",
        [
            ("Check CPU usage", "cpu"),
            ("Check RAM usage", "ram"),
            ("Battery status?", "battery"),
            ("Generate a laptop health report", "health"),
            (
                "Search Google Drive for invoices",
                "cloud_search",
            ),
            (
                "Delete notes.txt from Google Drive",
                "cloud_delete",
            ),
            (
                "Upload report.pdf to Google Drive",
                "cloud_upload",
            ),
            (
                "Download backup.zip from Google Drive",
                "cloud_download",
            ),
            (
                "Free up space on my laptop",
                "cleanup_preview",
            ),
        ],
    )
    def test_existing_intents_unchanged(
        self,
        planner,
        message,
        expected_tool,
    ):
        decision = planner.plan(message)

        assert decision["tool"] == expected_tool, (
            message
        )

