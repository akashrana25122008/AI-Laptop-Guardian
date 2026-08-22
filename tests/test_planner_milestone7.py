"""Milestone 7 - Planner multi-account routing.

Deterministic extraction of account references and
ALL-accounts scoping, without breaking Milestone 1-6
routing behavior.
"""

import pytest

from agent.planner import Planner


@pytest.fixture()
def planner():
    return Planner()


# =========================================================
# EXPLICIT ACCOUNT REFERENCES
# =========================================================


class TestAccountReferences:

    def test_search_account_number(self, planner):
        decision = planner.plan(
            "Search account 2 for report.pdf"
        )

        assert decision["tool"] == "cloud_search"
        assert decision["query"] == "report.pdf"
        assert decision["account_refs"] == ["2"]

    def test_find_with_account_in_middle(self, planner):
        decision = planner.plan(
            "Find invoices in account 1"
        )

        assert decision["tool"] == "cloud_search"
        assert decision["account_refs"] == ["1"]

    def test_download_from_account(self, planner):
        decision = planner.plan(
            "Download backup.zip from account number 3"
        )

        assert decision["tool"] == "cloud_download"
        assert decision["query"] == "backup.zip"
        assert decision["account_refs"] == ["3"]

    def test_upload_to_account(self, planner):
        decision = planner.plan(
            "Upload notes.txt to account 1"
        )

        assert decision["tool"] == "cloud_upload"
        assert decision["path"] == "notes.txt"
        assert decision["account_refs"] == ["1"]

    def test_delete_from_account(self, planner):
        decision = planner.plan(
            "Delete old.txt from account 2"
        )

        assert decision["tool"] == "cloud_delete"
        assert decision["query"] == "old.txt"
        assert decision["account_refs"] == ["2"]

    def test_remove_from_account_routes_as_cloud_delete(
        self,
        planner,
    ):
        decision = planner.plan(
            "Remove draft.docx from account 2"
        )

        assert decision["tool"] == "cloud_delete"
        assert decision["account_refs"] == ["2"]

    def test_account_ref_without_drive_word_is_cloud(self, planner):
        decision = planner.plan("search account 2 for x")

        assert decision["tool"] == "cloud_search"

    def test_local_drive_reference_stays_local(self, planner):
        decision = planner.plan(
            "list files on D drive"
        )

        assert decision["tool"] == "storage"


# =========================================================
# ALL-ACCOUNTS SCOPING
# =========================================================


class TestAllAccountsScope:

    def test_all_my_drives_sets_scope_all(self, planner):
        decision = planner.plan(
            "Search all my Google Drives for resume"
        )

        assert decision["tool"] == "cloud_search"
        assert decision["scope"] == "all"

    def test_all_connected_drives_wording(self, planner):
        decision = planner.plan(
            "Search all my connected Google Drives "
            "for resume"
        )

        assert decision["scope"] == "all"
        assert decision["query"] == "resume"

    def test_single_drive_has_no_scope(self, planner):
        decision = planner.plan(
            "Search my drive for reports"
        )

        assert decision["scope"] is None

    def test_legacy_google_drive_search_unchanged(
        self,
        planner,
    ):
        decision = planner.plan(
            "Search Google Drive for invoices"
        )

        assert decision["tool"] == "cloud_search"
        assert decision["query"] == "invoices"
        assert decision["account_refs"] == []
        assert decision["scope"] is None


# =========================================================
# LEGACY BEHAVIOR PRESERVED
# =========================================================


class TestLegacyBehaviorPreserved:

    def test_cloud_delete_without_account_unchanged(
        self,
        planner,
    ):
        decision = planner.plan(
            "Delete contract.pdf from Google Drive"
        )

        assert decision["tool"] == "cloud_delete"
        assert decision["query"] == "contract.pdf"
        assert decision["account_refs"] == []

    def test_storage_question_unaffected(self, planner):
        decision = planner.plan(
            "Why is my C drive warning?"
        )

        assert decision["tool"] == "storage"

    def test_cpu_question_unaffected(self, planner):
        decision = planner.plan("what is my cpu usage")

        assert decision["tool"] == "cpu"
