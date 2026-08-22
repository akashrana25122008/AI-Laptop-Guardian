"""End-to-end local cleanup confirmation flow tests.

Runs entirely inside a sandboxed TEMP directory.
No real user files are ever touched; no cloud access.
"""

import os
import sys
import time
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


MB = 1024 * 1024

DAYS = 60 * 60 * 24


class FakeAI:
    """Records prompts. Guarantees no real Ollama call."""

    def __init__(self):
        self.prompts = []

    def ask(self, prompt):
        self.prompts.append(str(prompt))
        return "FAKE AI RESPONSE"


def make_old_tmp(directory, name, size_bytes=2 * MB):
    path = directory / name
    path.write_bytes(b"T" * size_bytes)

    old = time.time() - 10 * DAYS
    os.utime(path, (old, old))

    return path


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """
    Sandbox TEMP BEFORE the agent stack is constructed so
    CleanupTool scans only the sandbox directory.
    """

    monkeypatch.setenv("TEMP", str(tmp_path))

    agent = AIAgent()
    agent.ai = FakeAI()

    return {
        "agent": agent,
        "tmp_path": tmp_path,
    }


def pending_paths(agent):
    return sorted(
        item["path"]
        for item in agent.safety.get_pending().items
    )


# =========================================================
# PROPOSAL
# =========================================================


class TestCleanupProposal:

    def test_delete_request_proposes_never_deletes(
        self,
        env,
    ):
        agent = env["agent"]
        tmp = env["tmp_path"]

        a = make_old_tmp(tmp, "a.tmp")
        b = make_old_tmp(tmp, "b.tmp")

        response = agent.chat(
            "Delete the temporary files you found."
        )

        assert a.exists() and b.exists()

        assert agent.safety.has_pending() is True
        assert (
            agent.safety.get_pending().action_type
            == "cleanup_delete"
        )
        assert len(agent.safety.get_pending().items) == 2
        assert "a.tmp" in response
        assert "confirm" in response.lower()
        assert "cancel" in response.lower()
        assert agent.ai.prompts == []

    def test_exact_identity_is_snapshotted(self, env):
        agent = env["agent"]
        tmp = env["tmp_path"]

        a = make_old_tmp(tmp, "one.tmp")
        b = make_old_tmp(tmp, "two.tmp")

        agent.chat("Delete the temporary files.")

        assert pending_paths(agent) == sorted(
            [str(a), str(b)]
        )

        for item in agent.safety.get_pending().items:
            stat = os.stat(item["path"])
            assert item["size_bytes"] == stat.st_size
            assert item["mtime"] == stat.st_mtime

    def test_no_candidates_stays_safe(self, env):
        agent = env["agent"]

        response = agent.chat(
            "Delete the temporary files."
        )

        assert "no safe" in response.lower()
        assert agent.safety.has_pending() is False

    def test_protected_files_are_never_proposed(self, env):
        agent = env["agent"]
        tmp = env["tmp_path"]

        exe = make_old_tmp(tmp, "setup.exe", 5 * MB)
        good = make_old_tmp(tmp, "cache_data.tmp")

        response = agent.chat(
            "Delete the temporary files."
        )

        assert "setup.exe" not in response
        assert exe.exists()
        assert pending_paths(agent) == [str(good)]


# =========================================================
# CONFIRMED EXECUTION
# =========================================================


class TestConfirmedExecution:

    def test_confirmation_deletes_exactly_the_proposed_set(
        self,
        env,
    ):
        agent = env["agent"]
        tmp = env["tmp_path"]

        a = make_old_tmp(tmp, "a.tmp")
        b = make_old_tmp(tmp, "b.tmp")

        agent.chat("Delete the temporary files.")
        response = agent.chat("confirm delete")

        assert not a.exists()
        assert not b.exists()
        assert "deleted 2" in response.lower()
        assert agent.safety.has_pending() is False

    def test_confirmation_is_single_use(self, env):
        agent = env["agent"]
        tmp = env["tmp_path"]

        make_old_tmp(tmp, "only.tmp")

        agent.chat("Delete the temporary files.")
        agent.chat("yes")

        # Nothing left to delete; second confirm must not
        # resurrect the expired action.

        agent.chat("yes")

        assert agent.safety.has_pending() is False

    def test_cancel_clears_proposal_without_deletion(
        self,
        env,
    ):
        agent = env["agent"]
        tmp = env["tmp_path"]

        a = make_old_tmp(tmp, "keepme.tmp")

        agent.chat("Delete the temporary files.")
        response = agent.chat("cancel")

        assert a.exists()
        assert agent.safety.has_pending() is False
        assert "cancel" in response.lower()

    def test_unrelated_message_expires_then_confirm_does_nothing(
        self,
        env,
    ):
        agent = env["agent"]
        tmp = env["tmp_path"]

        a = make_old_tmp(tmp, "survivor.tmp")

        agent.chat("Delete the temporary files.")
        agent.chat("what is my battery level?")

        assert agent.safety.has_pending() is False

        agent.chat("yes")

        assert a.exists()

    def test_changed_file_fails_safely(self, env):
        agent = env["agent"]
        tmp = env["tmp_path"]

        changed = make_old_tmp(tmp, "changed.tmp")
        stable = make_old_tmp(tmp, "stable.tmp")

        agent.chat("Delete the temporary files.")

        with open(changed, "ab") as handle:
            handle.write(b"grew after approval")

        response = agent.chat("confirm delete")

        assert changed.exists(), (
            "A file that changed after approval was deleted!"
        )
        assert not stable.exists()
        assert "skip" in response.lower()

    def test_missing_file_fails_safely(self, env):
        agent = env["agent"]
        tmp = env["tmp_path"]

        gone = make_old_tmp(tmp, "gone.tmp")
        stable = make_old_tmp(tmp, "stable.tmp")

        agent.chat("Delete the temporary files.")
        gone.unlink()
        response = agent.chat("confirm delete")

        assert not stable.exists()
        assert "skip" in response.lower()

    def test_new_file_after_approval_cannot_be_deleted(
        self,
        env,
    ):
        agent = env["agent"]
        tmp = env["tmp_path"]

        approved = make_old_tmp(tmp, "approved.tmp")

        agent.chat("Delete the temporary files.")

        newcomer = make_old_tmp(tmp, "newcomer.tmp")

        agent.chat("confirm delete")

        assert not approved.exists()
        assert newcomer.exists(), (
            "A file outside the approved snapshot "
            "was deleted!"
        )

    def test_new_proposal_replaces_old_and_authorizes_new_set(
        self,
        env,
    ):
        agent = env["agent"]
        tmp = env["tmp_path"]

        first = make_old_tmp(tmp, "first.tmp")

        agent.chat("Delete the temporary files.")

        second = make_old_tmp(tmp, "second.tmp")

        agent.chat("delete the temp files please")
        response = agent.chat("confirm delete")

        assert not first.exists()
        assert not second.exists()
        assert "deleted 2" in response.lower()


# =========================================================
# PREVIEW REMAINS READ-ONLY
# =========================================================


class TestPreviewReadOnly:

    def test_preview_request_deletes_nothing(self, env):
        agent = env["agent"]
        tmp = env["tmp_path"]

        a = make_old_tmp(tmp, "preview1.tmp")
        b = make_old_tmp(tmp, "preview2.tmp")

        agent.chat("Show me cleanup candidates")

        assert a.exists() and b.exists()
        assert agent.safety.has_pending() is False

        # The deterministic result reached the AI prompt.

        assert len(agent.ai.prompts) == 1
        assert "<tool_data>" in agent.ai.prompts[0]

    def test_failed_preview_reports_failure_safely(
        self,
        env,
        monkeypatch,
    ):
        agent = env["agent"]

        def broken():
            raise RuntimeError("disk exploded")

        monkeypatch.setattr(
            agent.router.cleanup_preview_tool,
            "preview",
            broken,
        )

        response = agent.chat("Show me cleanup candidates")

        assert "couldn't" in response.lower()
        assert agent.safety.has_pending() is False
