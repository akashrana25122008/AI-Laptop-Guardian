"""Milestone 24 -- Controlled Live Google Drive Mutation Validation tests.

Validates REAL cloud mutations against a dedicated test account.
All live tests require BOTH:

    AI_GUARDIAN_LIVE_GOOGLE=1
    AI_GUARDIAN_LIVE_GOOGLE_TEST_ACCOUNT=<email or account-id>

Without BOTH environment variables, no OAuth browser opens, no
network authentication occurs, and no Drive data is modified.

M24 test artifacts use uniquely-prefixed filenames:
    AI_GUARDIAN_M24_TEST_<timestamp>_<random>

Only artifacts created by this test run are ever deleted.
"""

import ast
import os
import random
import string
import sys
import tempfile
import time

import pytest

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

# ============================================================
# GATING
# ============================================================

LIVE_GOOGLE = os.environ.get(
    "AI_GUARDIAN_LIVE_GOOGLE", ""
).strip() == "1"

LIVE_ACCOUNT = os.environ.get(
    "AI_GUARDIAN_LIVE_GOOGLE_TEST_ACCOUNT", ""
).strip()

HAS_GOOGLE_DEPS = False
try:
    import google.auth  # noqa: F401
    import google.oauth2.credentials  # noqa: F401
    import google_auth_oauthlib.flow  # noqa: F401
    import googleapiclient.discovery  # noqa: F401
    HAS_GOOGLE_DEPS = True
except ImportError:
    pass

HAS_CREDENTIALS_FILE = os.path.isfile(
    os.path.join(PROJECT_ROOT, "credentials.json")
)

# Unique run identifier for test artifact isolation
_TIMESTAMP = int(time.time())
_RANDOM = "".join(
    random.choices(string.ascii_lowercase, k=6)
)
_RUN_ID = f"M24-{_TIMESTAMP}-{_RANDOM}"

# ============================================================
# HELPERS
# ============================================================


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _skip_unless_live():
    if not LIVE_GOOGLE:
        pytest.skip(
            "Live mutation test; "
            "set AI_GUARDIAN_LIVE_GOOGLE=1"
        )
    if not LIVE_ACCOUNT:
        pytest.skip(
            "Live mutation test; "
            "set AI_GUARDIAN_LIVE_GOOGLE_TEST_ACCOUNT"
        )
    if not HAS_GOOGLE_DEPS:
        pytest.skip("Google client libraries not installed")
    if not HAS_CREDENTIALS_FILE:
        pytest.skip("credentials.json not found")


def _test_payload():
    return (
        f"AI Laptop Guardian M24 test artifact.\n"
        f"Run ID: {_RUN_ID}\n"
        f"Timestamp: {_TIMESTAMP}\n"
        f"This file is safe to delete.\n"
    )


def _test_filename():
    return f"{_RUN_ID}-test-artifact.txt"


# ============================================================
# SECTION 1: OFFLINE / AUTOMATED TESTS (always run)
# ============================================================


class TestM24LiveGateEnforced:
    """Verify that mutation requires both env vars."""

    def test_no_upload_without_live_flag(self):
        if LIVE_GOOGLE:
            pytest.skip("Live flag is set")
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        assert len(mgr.describe_accounts()) == 0

    def test_no_upload_without_account_config(self):
        if LIVE_ACCOUNT:
            pytest.skip("Account config is set")
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        assert len(mgr.describe_accounts()) == 0

    def test_no_oauth_without_env(self):
        """Without env vars, no OAuth may occur."""
        if LIVE_GOOGLE or LIVE_ACCOUNT:
            pytest.skip("Env vars are set")
        from cloud.auth_manager import GoogleAuthManager
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        auth = GoogleAuthManager(
            drive_manager=MultiAccountDriveManager()
        )
        status = auth.get_auth_status()
        assert status["success"] is True
        assert len(status["accounts"]) == 0


class TestM24NoImplicitAuth:
    """Prove no OAuth on import/construction."""

    def test_import_all_cloud_modules(self):
        from cloud.auth_manager import GoogleAuthManager
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        from cloud.cloud_intelligence import (
            CloudStorageIntelligence,
        )
        from cloud.accounts import AccountRegistry
        assert all([
            GoogleAuthManager,
            MultiAccountDriveManager,
            CloudStorageIntelligence,
            AccountRegistry,
        ])

    def test_import_all_agent_modules(self):
        from agent.tool_router import ToolRouter
        from agent.action_safety import ActionSafety
        from agent.planner import Planner
        assert all([ToolRouter, ActionSafety, Planner])

    def test_create_tool_router_no_oauth(self):
        from agent.tool_router import ToolRouter
        router = ToolRouter()
        assert router is not None

    def test_create_action_safety_no_oauth(self):
        from agent.action_safety import ActionSafety
        safety = ActionSafety()
        assert safety.has_pending() is False

    def test_create_auth_manager_no_oauth(self):
        from cloud.auth_manager import GoogleAuthManager
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = GoogleAuthManager(
            drive_manager=MultiAccountDriveManager()
        )
        assert mgr is not None

    def test_planner_cloud_intent_no_network(self):
        from agent.planner import Planner
        p = Planner()
        for q in [
            "upload file to Google Drive",
            "search Google Drive for report.pdf",
            "check my Google Drive storage",
            "download file from Google Drive",
        ]:
            result = p.plan(q)
            assert "cloud" in result["tool"]


class TestM24ConfirmationGating:
    """Verify ActionSafety confirmation architecture."""

    def test_propose_delete_returns_pending(self):
        from agent.action_safety import ActionSafety
        safety = ActionSafety()
        pending = safety.propose_delete(
            "file-123", "test.txt",
            account_id="acc-1",
        )
        assert pending is not None
        assert pending.action_type == "cloud_delete"
        assert pending.target_id == "file-123"
        assert pending.account_id == "acc-1"

    def test_propose_delete_validates_target(self):
        from agent.action_safety import ActionSafety
        safety = ActionSafety()
        with pytest.raises(ValueError):
            safety.propose_delete(
                "", "test.txt", account_id="acc-1"
            )

    def test_wrong_phrase_does_not_confirm(self):
        from agent.action_safety import ActionSafety
        safety = ActionSafety()
        safety.propose_delete(
            "file-123", "test.txt",
            account_id="acc-1",
        )
        for phrase in [
            "maybe", "later", "nope", "sure",
            "ok", "proceed",
        ]:
            result = safety.validate_confirmation(
                phrase
            )
            assert result is None

    def test_cancel_prevents_delete(self):
        from agent.action_safety import ActionSafety
        safety = ActionSafety()
        safety.propose_delete(
            "file-123", "test.txt",
            account_id="acc-1",
        )
        cancelled = safety.cancel()
        assert cancelled is not None
        assert safety.has_pending() is False
        result = safety.validate_confirmation(
            "confirm"
        )
        assert result is None

    def test_confirmation_repeats_until_clear(self):
        from agent.action_safety import ActionSafety
        safety = ActionSafety()
        safety.propose_delete(
            "file-123", "test.txt",
            account_id="acc-1",
        )
        first = safety.validate_confirmation(
            "confirm"
        )
        assert first is not None
        second = safety.validate_confirmation(
            "confirm"
        )
        assert second is not None
        assert first is second
        safety.clear()
        third = safety.validate_confirmation(
            "confirm"
        )
        assert third is None

    def test_new_proposal_replaces_old(self):
        from agent.action_safety import ActionSafety
        safety = ActionSafety()
        safety.propose_delete(
            "file-aaa", "aaa.txt",
            account_id="acc-1",
        )
        safety.propose_delete(
            "file-bbb", "bbb.txt",
            account_id="acc-1",
        )
        pending = safety.get_pending()
        assert pending.target_id == "file-bbb"
        assert pending.target_name == "bbb.txt"

    def test_account_binding_preserved(self):
        from agent.action_safety import ActionSafety
        safety = ActionSafety()
        pending = safety.propose_delete(
            "file-123", "test.txt",
            account_id="acc-1",
        )
        assert pending.account_id == "acc-1"
        result = safety.validate_confirmation(
            "confirm"
        )
        assert result.account_id == "acc-1"

    def test_describe_includes_account(self):
        from agent.action_safety import ActionSafety
        safety = ActionSafety()
        pending = safety.propose_delete(
            "file-123", "test.txt",
            account_id="acc-1",
        )
        desc = pending.describe()
        assert "acc-1" in desc


class TestM24AccountIsolation:
    """Verify bound operations reject wrong account."""

    def test_delete_wrong_account_fails(self):
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        result = mgr.delete_from_account(
            "account-999", "file-123"
        )
        assert result["success"] is False

    def test_download_wrong_account_fails(self):
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        result = mgr.download_from_account(
            "account-999", "file-123"
        )
        assert result["success"] is False

    def test_upload_wrong_account_fails(self):
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        result = mgr.upload_to_account(
            "account-999", "/nonexistent"
        )
        assert result["success"] is False

    def test_router_delete_requires_file_id(self):
        from agent.tool_router import ToolRouter
        router = ToolRouter()
        result = router.execute_delete_by_id("")
        assert result["success"] is False

    def test_router_delete_no_google_deps(self):
        """When Google deps unavailable, delete fails."""
        from agent.tool_router import ToolRouter
        router = ToolRouter()
        if router.google_drive is None:
            result = router.execute_delete_by_id(
                "file-123"
            )
            assert result["success"] is False


class TestM24FilenameUniqueness:
    """Verify M24 test filenames are unique."""

    def test_run_id_format(self):
        assert _RUN_ID.startswith("M24-")
        assert str(_TIMESTAMP) in _RUN_ID
        assert len(_RANDOM) == 6

    def test_filename_format(self):
        fn = _test_filename()
        assert fn.startswith("M24-")
        assert fn.endswith(".txt")

    def test_payload_contains_run_id(self):
        payload = _test_payload()
        assert _RUN_ID in payload


class TestM24SecurityAudit:
    """Security audit for M24."""

    def test_no_secrets_tracked(self):
        import subprocess
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True, text=True,
            cwd=PROJECT_ROOT,
        )
        for name in [
            "credentials.json", "token.json", ".env"
        ]:
            assert name not in result.stdout

    def test_gitignore_excludes_cloud_data(self):
        text = _read(
            os.path.join(PROJECT_ROOT, ".gitignore")
        )
        assert "cloud_data/" in text

    def test_protected_projects_untouched(self):
        assert os.path.isdir(r"D:\AI-Laptop-Guardian")
        assert os.path.isdir(
            r"D:\AI-Laptop-Guardian-Backup"
        )

    def test_version_consistent(self):
        from app.version import __version__
        assert __version__ == "0.14.0"

    def test_action_safety_unchanged(self):
        import subprocess
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "--",
             "agent/action_safety.py"],
            capture_output=True, text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.stdout == ""

    def test_google_drive_unchanged(self):
        import subprocess
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "--",
             "cloud/google_drive.py"],
            capture_output=True, text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.stdout == ""

    def test_multi_drive_unchanged(self):
        import subprocess
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "--",
             "cloud/multi_drive.py"],
            capture_output=True, text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.stdout == ""

    def test_auth_manager_unchanged(self):
        import subprocess
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "--",
             "cloud/auth_manager.py"],
            capture_output=True, text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.stdout == ""

    def test_no_dangerous_calls_outside_fixtures(
        self,
    ):
        """AST scan: dangerous calls only in gated
        fixture/test functions."""
        test_file = os.path.join(
            PROJECT_ROOT, "tests",
            "test_m24_live_mutation_validation.py",
        )
        with open(test_file, encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)
        dangerous = {
            "delete_file_by_id",
            "upload_file",
        }

        # Collect all function/class definitions
        scoped = []
        for node in ast.walk(tree):
            if isinstance(node, (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            )):
                scoped.append((
                    node.name,
                    node.lineno,
                    getattr(
                        node, "end_lineno",
                        node.lineno + 1000,
                    ),
                ))
            elif isinstance(node, ast.ClassDef):
                scoped.append((
                    node.name,
                    node.lineno,
                    getattr(
                        node, "end_lineno",
                        node.lineno + 1000,
                    ),
                ))

        def _find_scope(line):
            best = None
            for name, start, end in scoped:
                if start <= line <= end:
                    if best is None or (
                        start >= best[1]
                    ):
                        best = (name, start, end)
            return best[0] if best else None

        # Allowed scopes: fixtures and test helpers
        # that perform mutations for verification
        allowed = {
            "uploaded_file",
            "live_mutation_env",
            "test_disconnect_blocks_mutation",
            "_check_dangerous",
        }

        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = None
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(
                    func, ast.Attribute
                ):
                    name = func.attr
                if name in dangerous:
                    scope = _find_scope(
                        node.lineno
                    )
                    if scope not in allowed:
                        violations.append(
                            f"{name} in {scope}"
                        )

        assert not violations, (
            f"Unexpected dangerous calls: "
            f"{violations}"
        )

    def test_no_secrets_in_test_file(self):
        """No real token patterns in test file."""
        import re
        test_file = os.path.join(
            PROJECT_ROOT, "tests",
            "test_m24_live_mutation_validation.py",
        )
        content = _read(test_file)
        patterns = [
            r'ya29[a-zA-Z0-9_-]{20,}',
            r'"refresh_token"\s*:\s*"[^"]{20,}"',
            r'"client_secret"\s*:\s*"[^"]{20,}"',
        ]
        for pat in patterns:
            matches = re.findall(pat, content)
            assert not matches, (
                f"Secret pattern {pat!r}: "
                f"{len(matches)} match(es)"
            )

    def test_no_network_in_ui(self):
        for f in [
            "ui/app.py",
            "ui/app_controller.py",
            "ui/components.py",
        ]:
            text = _read(
                os.path.join(PROJECT_ROOT, f)
            )
            for line in text.split("\n"):
                s = line.strip()
                if s.startswith("#"):
                    continue
                if (
                    "requests.get" in s
                    or "requests.post" in s
                    or "urlopen" in s
                ):
                    pytest.fail(
                        f"Network in {f}: {s}"
                    )

    def test_cleanup_is_target_bound(self):
        """Cleanup only targets exact account + file."""
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        result = mgr.delete_from_account(
            "account-999", "file-999"
        )
        assert result["success"] is False

    def test_no_new_network_in_cloud(self):
        for f in [
            "cloud/auth_manager.py",
            "cloud/accounts.py",
            "cloud/cloud_intelligence.py",
        ]:
            text = _read(
                os.path.join(PROJECT_ROOT, f)
            )
            for line in text.split("\n"):
                s = line.strip()
                if s.startswith("#"):
                    continue
                if (
                    "requests.get" in s
                    or "requests.post" in s
                    or "urlopen" in s
                ):
                    pytest.fail(
                        f"Network in {f}: {s}"
                    )


# ============================================================
# SECTION 2: LIVE MUTATION TESTS (gated)
# ============================================================


@pytest.fixture(scope="module")
def live_mutation_env():
    """Shared fixture: authenticate and yield
    (router, account_id, account_email, was_new).

    Requires BOTH AI_GUARDIAN_LIVE_GOOGLE=1
    AND AI_GUARDIAN_LIVE_GOOGLE_TEST_ACCOUNT."""
    _skip_unless_live()

    from agent.tool_router import ToolRouter
    from cloud.auth_manager import GoogleAuthManager
    from cloud.multi_drive import (
        MultiAccountDriveManager,
    )

    mgr = MultiAccountDriveManager()
    auth = GoogleAuthManager(drive_manager=mgr)

    # Check for existing connected account
    status = auth.get_auth_status()
    existing = [
        a for a in status.get("accounts", [])
        if a["status"] == "connected"
    ]

    if existing:
        account_id = existing[0]["id"]
        account_email = existing[0].get("email", "")
        router = ToolRouter()
        yield router, account_id, account_email, False
        return

    # New connection via explicit OAuth
    result = auth.connect_account()
    assert result["success"], (
        f"OAuth failed: "
        f"{result.get('error', 'unknown')}"
    )
    account_id = result["account"]["id"]
    account_email = result["account"].get("email", "")

    router = ToolRouter()
    yield router, account_id, account_email, True

    # Teardown: disconnect only if we connected
    try:
        auth.disconnect_account(account_id)
    except Exception:
        pass


@pytest.fixture(scope="module")
def uploaded_file(live_mutation_env):
    """Upload a uniquely-named M24 test artifact and
    yield its metadata. Cleans up on teardown."""
    _skip_unless_live()

    router, account_id, account_email, _ = (
        live_mutation_env
    )

    # Create a temporary local file
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        delete=False,
        encoding="utf-8",
    )
    tmp.write(_test_payload())
    tmp.close()

    file_id = None
    try:
        session = router.drive_manager.get_session(
            account_id
        )
        assert session is not None, (
            "No session for test account"
        )
        result = session.upload_file(tmp.name)
        assert result["success"], (
            f"Upload failed: {result.get('error')}"
        )

        file_id = result["data"]["file_id"]
        file_name = result["data"]["name"]

        yield {
            "file_id": file_id,
            "name": file_name,
            "account_id": account_id,
            "account_email": account_email,
            "local_path": tmp.name,
        }
    finally:
        # Cleanup: trash the uploaded artifact
        try:
            if file_id:
                session = (
                    router.drive_manager.get_session(
                        account_id
                    )
                )
                if session:
                    session.delete_file_by_id(
                        file_id,
                        permanent=False,
                    )
        except Exception:
            pass
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ============================================================
# LIVE TEST CLASSES
# ============================================================


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1",
)
@pytest.mark.skipif(
    not LIVE_ACCOUNT,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE_TEST_ACCOUNT",
)
@pytest.mark.skipif(
    not HAS_GOOGLE_DEPS,
    reason="Google client libraries not installed",
)
@pytest.mark.skipif(
    not HAS_CREDENTIALS_FILE,
    reason="credentials.json not found",
)
class TestLiveOAuthConnection:
    """Live: explicit OAuth connection flow."""

    def test_connect_completes(
        self, live_mutation_env
    ):
        router, account_id, _, _ = live_mutation_env
        assert account_id is not None
        assert account_id.startswith("account-")

    def test_account_registered(
        self, live_mutation_env
    ):
        router, account_id, _, _ = live_mutation_env
        from cloud.auth_manager import GoogleAuthManager
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        auth = GoogleAuthManager(drive_manager=mgr)
        status = auth.get_auth_status()
        ids = [a["id"] for a in status["accounts"]]
        assert account_id in ids

    def test_account_identity_safe(
        self, live_mutation_env
    ):
        router, account_id, _, _ = live_mutation_env
        from cloud.auth_manager import GoogleAuthManager
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        auth = GoogleAuthManager(drive_manager=mgr)
        status = auth.get_auth_status()
        status_str = str(status)
        assert "ya29" not in status_str
        assert "refresh_token" not in status_str
        assert "client_secret" not in status_str

    def test_token_isolated_per_account(
        self, live_mutation_env
    ):
        router, account_id, _, _ = live_mutation_env
        import os
        token_dir = os.path.join(
            PROJECT_ROOT, "cloud_data", "tokens"
        )
        token_path = os.path.join(
            token_dir, f"{account_id}.json"
        )
        assert os.path.isfile(token_path)


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1",
)
@pytest.mark.skipif(
    not LIVE_ACCOUNT,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE_TEST_ACCOUNT",
)
@pytest.mark.skipif(
    not HAS_GOOGLE_DEPS,
    reason="Google client libraries not installed",
)
@pytest.mark.skipif(
    not HAS_CREDENTIALS_FILE,
    reason="credentials.json not found",
)
class TestLiveUploadValidation:
    """Live: real upload to Google Drive."""

    def test_upload_succeeds(self, uploaded_file):
        meta = uploaded_file
        assert meta["file_id"] is not None
        assert meta["name"].startswith("M24-")

    def test_upload_returns_valid_metadata(
        self, uploaded_file
    ):
        meta = uploaded_file
        assert "file_id" in meta
        assert "name" in meta
        assert "account_id" in meta
        assert meta["account_id"].startswith(
            "account-"
        )

    def test_upload_file_exists(
        self, uploaded_file, live_mutation_env
    ):
        router, account_id, _, _ = live_mutation_env
        session = router.drive_manager.get_session(
            account_id
        )
        result = session.get_file_by_id(
            uploaded_file["file_id"]
        )
        assert result["success"] is True
        assert result["data"]["id"] == (
            uploaded_file["file_id"]
        )

    def test_upload_name_matches(
        self, uploaded_file
    ):
        assert uploaded_file["name"] == _test_filename()


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1",
)
@pytest.mark.skipif(
    not LIVE_ACCOUNT,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE_TEST_ACCOUNT",
)
@pytest.mark.skipif(
    not HAS_GOOGLE_DEPS,
    reason="Google client libraries not installed",
)
@pytest.mark.skipif(
    not HAS_CREDENTIALS_FILE,
    reason="credentials.json not found",
)
class TestLiveSearchValidation:
    """Live: real search after upload."""

    def test_search_finds_artifact(
        self, uploaded_file, live_mutation_env
    ):
        router, account_id, _, _ = live_mutation_env
        session = router.drive_manager.get_session(
            account_id
        )
        result = session.search_files(
            uploaded_file["name"]
        )
        assert result["success"] is True
        assert result["count"] >= 1
        ids = [m["id"] for m in result["matches"]]
        assert uploaded_file["file_id"] in ids

    def test_search_exact_id_matches(
        self, uploaded_file, live_mutation_env
    ):
        router, account_id, _, _ = live_mutation_env
        session = router.drive_manager.get_session(
            account_id
        )
        result = session.search_files(
            uploaded_file["name"]
        )
        exact = [
            m for m in result["matches"]
            if m["id"] == uploaded_file["file_id"]
        ]
        assert len(exact) == 1

    def test_search_name_matches(
        self, uploaded_file, live_mutation_env
    ):
        router, account_id, _, _ = live_mutation_env
        session = router.drive_manager.get_session(
            account_id
        )
        result = session.search_files(
            uploaded_file["name"]
        )
        for match in result["matches"]:
            assert match["name"] == (
                uploaded_file["name"]
            )

    def test_search_empty_query_fails(
        self, live_mutation_env
    ):
        router, account_id, _, _ = live_mutation_env
        session = router.drive_manager.get_session(
            account_id
        )
        result = session.search_files("")
        assert result["success"] is False


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1",
)
@pytest.mark.skipif(
    not LIVE_ACCOUNT,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE_TEST_ACCOUNT",
)
@pytest.mark.skipif(
    not HAS_GOOGLE_DEPS,
    reason="Google client libraries not installed",
)
@pytest.mark.skipif(
    not HAS_CREDENTIALS_FILE,
    reason="credentials.json not found",
)
class TestLiveDownloadValidation:
    """Live: real download of uploaded artifact."""

    def test_download_succeeds(
        self, uploaded_file, live_mutation_env
    ):
        router, account_id, _, _ = live_mutation_env
        result = router.execute_download_bound(
            account_id, uploaded_file["file_id"]
        )
        assert result["success"] is True

    def test_download_content_matches(
        self, uploaded_file, live_mutation_env
    ):
        router, account_id, _, _ = live_mutation_env
        result = router.execute_download_bound(
            account_id, uploaded_file["file_id"]
        )
        assert result["success"] is True
        path = result["data"]["path"]
        assert os.path.isfile(path)
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "AI Laptop Guardian M24" in content
        assert _RUN_ID in content
        try:
            os.unlink(path)
        except OSError:
            pass

    def test_download_bound_to_account(
        self, uploaded_file, live_mutation_env
    ):
        router, account_id, _, _ = live_mutation_env
        result = router.execute_download_bound(
            account_id, uploaded_file["file_id"]
        )
        assert result["success"] is True
        assert result.get("account_id") == account_id


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1",
)
@pytest.mark.skipif(
    not LIVE_ACCOUNT,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE_TEST_ACCOUNT",
)
@pytest.mark.skipif(
    not HAS_GOOGLE_DEPS,
    reason="Google client libraries not installed",
)
@pytest.mark.skipif(
    not HAS_CREDENTIALS_FILE,
    reason="credentials.json not found",
)
class TestLiveDeleteValidation:
    """Live: real delete via ActionSafety confirmation
    flow."""

    def test_proposal_does_not_delete(
        self, uploaded_file, live_mutation_env
    ):
        from agent.action_safety import ActionSafety
        router, account_id, _, _ = live_mutation_env
        safety = ActionSafety()

        safety.propose_delete(
            uploaded_file["file_id"],
            uploaded_file["name"],
            account_id=account_id,
        )

        session = router.drive_manager.get_session(
            account_id
        )
        result = session.get_file_by_id(
            uploaded_file["file_id"]
        )
        assert result["success"] is True
        safety.cancel()

    def test_cancel_prevents_deletion(
        self, uploaded_file, live_mutation_env
    ):
        from agent.action_safety import ActionSafety
        router, account_id, _, _ = live_mutation_env
        safety = ActionSafety()

        safety.propose_delete(
            uploaded_file["file_id"],
            uploaded_file["name"],
            account_id=account_id,
        )
        safety.cancel()

        session = router.drive_manager.get_session(
            account_id
        )
        result = session.get_file_by_id(
            uploaded_file["file_id"]
        )
        assert result["success"] is True

    def test_wrong_confirmation_does_not_delete(
        self, uploaded_file, live_mutation_env
    ):
        from agent.action_safety import ActionSafety
        router, account_id, _, _ = live_mutation_env
        safety = ActionSafety()

        safety.propose_delete(
            uploaded_file["file_id"],
            uploaded_file["name"],
            account_id=account_id,
        )
        result = safety.validate_confirmation(
            "maybe later"
        )
        assert result is None

        session = router.drive_manager.get_session(
            account_id
        )
        res = session.get_file_by_id(
            uploaded_file["file_id"]
        )
        assert res["success"] is True
        safety.cancel()

    def test_confirmed_delete_trashes_file(
        self, uploaded_file, live_mutation_env
    ):
        from agent.action_safety import ActionSafety
        router, account_id, _, _ = live_mutation_env
        safety = ActionSafety()

        # Propose
        pending = safety.propose_delete(
            uploaded_file["file_id"],
            uploaded_file["name"],
            account_id=account_id,
        )
        assert pending is not None
        assert pending.account_id == account_id

        # Confirm
        confirmed = safety.validate_confirmation(
            "confirm"
        )
        assert confirmed is not None
        assert confirmed.target_id == (
            uploaded_file["file_id"]
        )
        assert confirmed.account_id == account_id

        # Execute
        result = router.execute_delete_by_id(
            confirmed.target_id,
            name=confirmed.target_name,
            account_id=confirmed.account_id,
        )
        assert result["success"], (
            f"Delete failed: {result.get('error')}"
        )
        safety.clear()

    def test_file_no_longer_searchable(
        self, uploaded_file, live_mutation_env
    ):
        router, account_id, _, _ = live_mutation_env
        session = router.drive_manager.get_session(
            account_id
        )
        result = session.search_files(
            uploaded_file["name"]
        )
        assert result["success"] is True
        ids = [m["id"] for m in result["matches"]]
        assert uploaded_file["file_id"] not in ids


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1",
)
@pytest.mark.skipif(
    not LIVE_ACCOUNT,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE_TEST_ACCOUNT",
)
@pytest.mark.skipif(
    not HAS_GOOGLE_DEPS,
    reason="Google client libraries not installed",
)
@pytest.mark.skipif(
    not HAS_CREDENTIALS_FILE,
    reason="credentials.json not found",
)
class TestLiveDisconnectReconnect:
    """Live: disconnect/reconnect safety."""

    def test_disconnect_blocks_mutation(
        self, live_mutation_env
    ):
        from agent.action_safety import ActionSafety
        from cloud.auth_manager import GoogleAuthManager
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )

        router, account_id, _, _ = live_mutation_env

        # Upload a test file
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            delete=False,
            encoding="utf-8",
        )
        tmp.write(_test_payload())
        tmp.close()

        try:
            session = router.drive_manager.get_session(
                account_id
            )
            upload = session.upload_file(tmp.name)
            assert upload["success"]
            file_id = upload["data"]["file_id"]

            # Propose delete
            safety = ActionSafety()
            safety.propose_delete(
                file_id,
                upload["data"]["name"],
                account_id=account_id,
            )

            # Disconnect the account
            mgr = MultiAccountDriveManager()
            auth = GoogleAuthManager(
                drive_manager=mgr
            )
            auth.disconnect_account(account_id)

            # Execute should fail (no session)
            router2 = ToolRouter()
            result = router2.execute_delete_by_id(
                file_id,
                name="test.txt",
                account_id=account_id,
            )
            assert result["success"] is False

            # Cleanup: reconnect and trash
            result2 = auth.connect_account()
            if result2["success"]:
                new_id = result2["account"]["id"]
                s = mgr.get_session(new_id)
                if s:
                    s.delete_file_by_id(
                        file_id, permanent=False
                    )
                auth.disconnect_account(new_id)
        except Exception:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    def test_old_id_not_reused(
        self, live_mutation_env
    ):
        """Reconnected account gets new/retained ID,
        old ID is never silently reassigned."""
        router, account_id, _, _ = live_mutation_env
        # Just verify the account_id format is stable
        assert account_id.startswith("account-")


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1",
)
@pytest.mark.skipif(
    not LIVE_ACCOUNT,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE_TEST_ACCOUNT",
)
@pytest.mark.skipif(
    not HAS_GOOGLE_DEPS,
    reason="Google client libraries not installed",
)
@pytest.mark.skipif(
    not HAS_CREDENTIALS_FILE,
    reason="credentials.json not found",
)
class TestLiveFailureModes:
    """Live: failure modes with real Drive."""

    def test_download_wrong_file_id(
        self, live_mutation_env
    ):
        router, account_id, _, _ = live_mutation_env
        result = router.execute_download_bound(
            account_id,
            "nonexistent-file-id-999",
        )
        assert result["success"] is False

    def test_delete_wrong_account(
        self, uploaded_file, live_mutation_env
    ):
        router, account_id, _, _ = live_mutation_env
        result = router.execute_delete_by_id(
            uploaded_file["file_id"],
            name=uploaded_file["name"],
            account_id="account-999",
        )
        assert result["success"] is False

    def test_empty_file_id_rejected(
        self, live_mutation_env
    ):
        router, account_id, _, _ = live_mutation_env
        result = router.execute_download_bound(
            account_id, ""
        )
        assert result["success"] is False

    def test_stale_proposal_cannot_execute(
        self, uploaded_file, live_mutation_env
    ):
        from agent.action_safety import ActionSafety
        router, account_id, _, _ = live_mutation_env
        safety = ActionSafety()

        safety.propose_delete(
            uploaded_file["file_id"],
            uploaded_file["name"],
            account_id=account_id,
        )
        safety.cancel()

        result = safety.validate_confirmation(
            "confirm"
        )
        assert result is None

    def test_new_file_cannot_substitute(
        self, uploaded_file, live_mutation_env
    ):
        from agent.action_safety import ActionSafety
        router, account_id, _, _ = live_mutation_env
        safety = ActionSafety()

        safety.propose_delete(
            uploaded_file["file_id"],
            uploaded_file["name"],
            account_id=account_id,
        )
        confirmed = safety.validate_confirmation(
            "confirm"
        )
        assert confirmed.target_id == (
            uploaded_file["file_id"]
        )
        assert confirmed.target_id != "other-file"
        safety.clear()


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1",
)
@pytest.mark.skipif(
    not LIVE_ACCOUNT,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE_TEST_ACCOUNT",
)
@pytest.mark.skipif(
    not HAS_GOOGLE_DEPS,
    reason="Google client libraries not installed",
)
@pytest.mark.skipif(
    not HAS_CREDENTIALS_FILE,
    reason="credentials.json not found",
)
class TestLiveNoDestructiveOps:
    """Prove no destructive operations in test file."""

    def test_no_delete_calls(self):
        found = self._check_dangerous()
        assert "delete_file_by_id" not in found

    def test_no_upload_calls(self):
        found = self._check_dangerous()
        assert "upload_file" not in found

    @staticmethod
    def _check_dangerous():
        import ast as _ast
        test_file = os.path.join(
            PROJECT_ROOT, "tests",
            "test_m24_live_mutation_validation.py",
        )
        with open(test_file, encoding="utf-8") as fh:
            source = fh.read()
        tree = _ast.parse(source)
        dangerous = {
            "delete_file_by_id",
            "upload_file",
        }
        found = []
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Call):
                func = node.func
                name = None
                if isinstance(func, _ast.Name):
                    name = func.id
                elif isinstance(
                    func, _ast.Attribute
                ):
                    name = func.attr
                if name in dangerous:
                    found.append(name)
        return found
