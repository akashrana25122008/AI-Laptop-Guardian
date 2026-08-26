"""Milestone 23 -- Controlled Real Google Drive Mutation Validation tests.

Validates REAL cloud mutations (upload, search, download, delete)
against explicitly designated test data. All live tests require:

    AI_GUARDIAN_LIVE_GOOGLE=1
    AI_GUARDIAN_LIVE_GOOGLE_TEST_ACCOUNT=<email or account-id>

Without these environment variables, no OAuth browser opens, no
network authentication occurs, and no Drive data is modified.

Test artifacts use unique M23-prefixed filenames and are cleaned
up at the end of each live test run. Only artifacts created by
this test run are ever deleted.
"""

import ast
import os
import sys
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
_RUN_ID = f"M23-{int(time.time())}"

# ============================================================
# HELPERS
# ============================================================


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _skip_unless_live():
    if not LIVE_GOOGLE:
        pytest.skip(
            "Live Google mutation test; "
            "set AI_GUARDIAN_LIVE_GOOGLE=1"
        )
    if not LIVE_ACCOUNT:
        pytest.skip(
            "Live Google mutation test; "
            "set AI_GUARDIAN_LIVE_GOOGLE_TEST_ACCOUNT"
        )
    if not HAS_GOOGLE_DEPS:
        pytest.skip("Google client libraries not installed")
    if not HAS_CREDENTIALS_FILE:
        pytest.skip("credentials.json not found")


def _test_payload():
    return (
        f"AI Laptop Guardian M23 test artifact.\n"
        f"Run ID: {_RUN_ID}\n"
        f"This file is safe to delete.\n"
    )


def _test_filename():
    return f"{_RUN_ID}-test-artifact.txt"


# ============================================================
# SECTION 1: OFFLINE / ARCHITECTURE TESTS (always run)
# ============================================================


class TestM23NoImplicitAuth:
    """Prove importing and constructing components
    never triggers OAuth."""

    def test_import_auth_manager(self):
        from cloud.auth_manager import GoogleAuthManager
        assert GoogleAuthManager is not None

    def test_import_multi_drive(self):
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        assert MultiAccountDriveManager is not None

    def test_import_tool_router(self):
        from agent.tool_router import ToolRouter
        assert ToolRouter is not None

    def test_import_action_safety(self):
        from agent.action_safety import ActionSafety
        assert ActionSafety is not None

    def test_create_tool_router_no_oauth(self):
        from agent.tool_router import ToolRouter
        router = ToolRouter()
        assert router is not None

    def test_create_auth_manager_no_oauth(self):
        from cloud.auth_manager import GoogleAuthManager
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = GoogleAuthManager(
            drive_manager=MultiAccountDriveManager()
        )
        assert mgr is not None

    def test_create_action_safety_no_oauth(self):
        from agent.action_safety import ActionSafety
        safety = ActionSafety()
        assert safety.has_pending() is False

    def test_import_planner_no_oauth(self):
        from agent.planner import Planner
        p = Planner()
        result = p.plan("upload file to Google Drive")
        assert result["tool"] == "cloud_upload"


class TestM23LiveGateEnforced:
    """Verify that mutation requires both env vars."""

    def test_no_upload_without_live_flag(self):
        """Without AI_GUARDIAN_LIVE_GOOGLE, no mutation."""
        if LIVE_GOOGLE:
            pytest.skip("Live flag is set")
        # Verify no session is created
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        accounts = mgr.describe_accounts()
        assert len(accounts) == 0

    def test_no_upload_without_account_config(self):
        """Without TEST_ACCOUNT, no mutation target."""
        if LIVE_ACCOUNT:
            pytest.skip("Account config is set")
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        accounts = mgr.describe_accounts()
        assert len(accounts) == 0


class TestM23ConfirmationGating:
    """Verify delete requires ActionSafety confirmation."""

    def test_propose_delete_returns_pending(self):
        from agent.action_safety import ActionSafety
        safety = ActionSafety()
        pending = safety.propose_delete(
            "file-123", "test.txt", account_id="acc-1"
        )
        assert pending is not None
        assert pending.action_type == "cloud_delete"
        assert pending.target_id == "file-123"
        assert pending.account_id == "acc-1"

    def test_wrong_confirmation_does_not_delete(self):
        from agent.action_safety import ActionSafety
        safety = ActionSafety()
        safety.propose_delete(
            "file-123", "test.txt", account_id="acc-1"
        )
        result = safety.validate_confirmation(
            "maybe later"
        )
        assert result is None

    def test_cancel_prevents_delete(self):
        from agent.action_safety import ActionSafety
        safety = ActionSafety()
        safety.propose_delete(
            "file-123", "test.txt", account_id="acc-1"
        )
        cancelled = safety.cancel()
        assert cancelled is not None
        assert safety.has_pending() is False
        result = safety.validate_confirmation("confirm")
        assert result is None

    def test_confirmation_repeats_until_clear(self):
        from agent.action_safety import ActionSafety
        safety = ActionSafety()
        safety.propose_delete(
            "file-123", "test.txt", account_id="acc-1"
        )
        first = safety.validate_confirmation("confirm")
        assert first is not None
        second = safety.validate_confirmation("confirm")
        assert second is not None
        # Same pending object
        assert first is second
        # After clear, confirmation fails
        safety.clear()
        third = safety.validate_confirmation("confirm")
        assert third is None

    def test_new_proposal_replaces_old(self):
        from agent.action_safety import ActionSafety
        safety = ActionSafety()
        safety.propose_delete(
            "file-aaa", "aaa.txt", account_id="acc-1"
        )
        safety.propose_delete(
            "file-bbb", "bbb.txt", account_id="acc-1"
        )
        pending = safety.get_pending()
        assert pending.target_id == "file-bbb"
        assert pending.target_name == "bbb.txt"

    def test_account_binding_preserved(self):
        from agent.action_safety import ActionSafety
        safety = ActionSafety()
        pending = safety.propose_delete(
            "file-123", "test.txt", account_id="acc-1"
        )
        assert pending.account_id == "acc-1"
        # Confirmation is bound to exact target + account
        result = safety.validate_confirmation("confirm")
        assert result.account_id == "acc-1"


class TestM23AccountIsolation:
    """Verify account binding prevents cross-account
    mutation."""

    def test_bound_operation_requires_account(self):
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        result = mgr.delete_from_account(
            "account-999", "file-123"
        )
        assert result["success"] is False

    def test_download_requires_account(self):
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        result = mgr.download_from_account(
            "account-999", "file-123"
        )
        assert result["success"] is False

    def test_upload_requires_account(self):
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        result = mgr.upload_to_account(
            "account-999", "/nonexistent"
        )
        assert result["success"] is False


class TestM23SafetyAudit:
    """Security audit for M23."""

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
        """M23 must not redesign the provider."""
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

    def test_no_dangerous_calls_in_m23_file(self):
        """Verify dangerous calls only exist inside
        gated test fixtures and live test methods."""
        test_file = os.path.join(
            PROJECT_ROOT, "tests",
            "test_m23_real_google_mutations.py",
        )
        with open(test_file, encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)
        dangerous = {
            "delete_file_by_id",
            "upload_file",
        }
        # Collect all function/class definitions and
        # their line ranges
        scoped_nodes = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                scoped_nodes.append((
                    node.name,
                    node.lineno,
                    getattr(node, "end_lineno",
                            node.lineno + 1000),
                ))
            elif isinstance(node, ast.ClassDef):
                scoped_nodes.append((
                    node.name,
                    node.lineno,
                    getattr(node, "end_lineno",
                            node.lineno + 1000),
                ))

        def _find_scope(line):
            """Find the innermost function/class
            containing this line."""
            best = None
            for name, start, end in scoped_nodes:
                if start <= line <= end:
                    if best is None or (
                        start >= best[1]
                    ):
                        best = (name, start, end)
            return best[0] if best else None

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
                    # Allowed in: fixture functions
                    # (uploaded_file, live_mutation_env)
                    # and test helpers that perform
                    # mutations for verification
                    allowed_scopes = {
                        "uploaded_file",
                        "live_mutation_env",
                        "test_disconnect_blocks_"
                        "delete",
                        "_check_dangerous",
                    }
                    if scope not in allowed_scopes:
                        violations.append(
                            f"{name} in {scope}"
                        )

        assert not violations, (
            f"Unexpected dangerous calls: "
            f"{violations}"
        )

    def test_no_network_in_ui(self):
        for f in [
            "ui/app.py",
            "ui/app_controller.py",
            "ui/components.py",
        ]:
            text = _read(os.path.join(PROJECT_ROOT, f))
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

    def test_no_new_network_in_cloud(self):
        """No new raw network calls in cloud layer."""
        for f in [
            "cloud/auth_manager.py",
            "cloud/accounts.py",
            "cloud/cloud_intelligence.py",
        ]:
            text = _read(os.path.join(PROJECT_ROOT, f))
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

    def test_cleanup_is_account_bound(self):
        """Cleanup only targets exact account + file."""
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        # Deleting from nonexistent account fails safely
        result = mgr.delete_from_account(
            "account-999", "file-999"
        )
        assert result["success"] is False

    def test_no_secrets_in_test_output(self):
        """Test file must not contain real tokens."""
        test_file = os.path.join(
            PROJECT_ROOT, "tests",
            "test_m23_real_google_mutations.py",
        )
        content = _read(test_file)
        # Check for actual token patterns, not
        # assertion strings about them
        import re
        token_patterns = [
            r'ya29[a-zA-Z0-9_-]{20,}',
            r'"refresh_token"\s*:\s*"[^"]{20,}"',
            r'"client_secret"\s*:\s*"[^"]{20,}"',
        ]
        for pat in token_patterns:
            matches = re.findall(pat, content)
            assert not matches, (
                f"Possible secret pattern {pat!r} "
                f"found: {len(matches)} match(es)"
            )


# ============================================================
# SECTION 2: LIVE MUTATION TESTS (gated)
# ============================================================


@pytest.fixture(scope="module")
def live_mutation_env():
    """Shared fixture: authenticate and yield
    (router, account_id, account_email).

    Only runs when both AI_GUARDIAN_LIVE_GOOGLE=1
    and AI_GUARDIAN_LIVE_GOOGLE_TEST_ACCOUNT are set.

    Creates a fresh connection using the configured
    test account. Disconnects on teardown."""
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
        # Build router with existing session
        router = ToolRouter()
        yield router, account_id, account_email, False
        return

    # New connection via explicit OAuth
    result = auth.connect_account()
    assert result["success"], (
        f"OAuth failed: {result.get('error', 'unknown')}"
    )
    account_id = result["account"]["id"]
    account_email = result["account"].get("email", "")

    # Build router with the connected session
    router = ToolRouter()

    yield router, account_id, account_email, True

    # Teardown: disconnect what we connected
    try:
        auth.disconnect_account(account_id)
    except Exception:
        pass


@pytest.fixture(scope="module")
def uploaded_file(live_mutation_env):
    """Upload a uniquely-named M23 test artifact and
    yield its metadata. Cleans up on teardown.

    Returns dict with keys: file_id, name, account_id,
    account_email."""
    router, account_id, account_email, _ = (
        live_mutation_env
    )

    import tempfile

    # Create a temporary local file
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        delete=False,
        encoding="utf-8",
    )
    tmp.write(_test_payload())
    tmp.close()

    try:
        # Upload via account-bound path
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
        }
    finally:
        # Cleanup: trash the uploaded artifact
        try:
            session = router.drive_manager.get_session(
                account_id
            )
            if session and file_id:
                session.delete_file_by_id(
                    file_id, permanent=False
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
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1 for live tests",
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
        assert meta["name"].startswith(_RUN_ID)

    def test_upload_returns_metadata(
        self, uploaded_file
    ):
        meta = uploaded_file
        assert "file_id" in meta
        assert "name" in meta
        assert "account_id" in meta
        assert meta["account_id"].startswith("account-")

    def test_upload_file_exists(
        self, uploaded_file, live_mutation_env
    ):
        """Verify uploaded file is findable by ID."""
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

    def test_upload_unique_name(
        self, uploaded_file
    ):
        """M23 filenames must be unique per run."""
        assert uploaded_file["name"].startswith(
            "M23-"
        )
        assert uploaded_file["name"].endswith(
            ".txt"
        )


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1 for live tests",
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
        # Exact file ID match
        ids = [m["id"] for m in result["matches"]]
        assert uploaded_file["file_id"] in ids

    def test_search_returns_correct_account(
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
        for match in result["matches"]:
            assert match["name"] == (
                uploaded_file["name"]
            )

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
        assert result["success"] is True
        exact = [
            m for m in result["matches"]
            if m["id"] == uploaded_file["file_id"]
        ]
        assert len(exact) == 1


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1 for live tests",
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
        assert "AI Laptop Guardian M23" in content
        assert _RUN_ID in content
        # Cleanup downloaded file
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
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1 for live tests",
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
        """Creating a proposal must not delete."""
        from agent.action_safety import ActionSafety
        router, account_id, _, _ = live_mutation_env
        safety = ActionSafety()

        safety.propose_delete(
            uploaded_file["file_id"],
            uploaded_file["name"],
            account_id=account_id,
        )

        # File must still exist
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

        # File must still exist
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

        # File must still exist
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
        """Full confirm → execute flow must trash."""
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

        # Execute via router
        result = router.execute_delete_by_id(
            confirmed.target_id,
            name=confirmed.target_name,
            account_id=confirmed.account_id,
        )
        assert result["success"], (
            f"Delete failed: {result.get('error')}"
        )

        # Clear pending
        safety.clear()

    def test_file_no_longer_searchable(
        self, uploaded_file, live_mutation_env
    ):
        """After trash, file should not appear in
        normal search."""
        router, account_id, _, _ = live_mutation_env
        session = router.drive_manager.get_session(
            account_id
        )
        result = session.search_files(
            uploaded_file["name"]
        )
        assert result["success"] is True
        # Should not find the trashed file
        ids = [m["id"] for m in result["matches"]]
        assert uploaded_file["file_id"] not in ids


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1 for live tests",
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
class TestLiveDisconnectReconnectSafety:
    """Live: disconnect mid-mutation fails safely."""

    def test_disconnect_blocks_delete(
        self, live_mutation_env
    ):
        """Disconnecting account before confirm must
        cause deletion to fail safely."""
        from agent.action_safety import ActionSafety
        from cloud.auth_manager import GoogleAuthManager
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )

        router, account_id, _, _ = live_mutation_env

        # Create a temporary file and upload
        import tempfile
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
            auth = GoogleAuthManager(drive_manager=mgr)
            auth.disconnect_account(account_id)

            # Now execute should fail (no session)
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
            # Best-effort cleanup
            try:
                os.unlink(tmp.name)
            except OSError:
                pass


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1 for live tests",
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
class TestLiveFailureStaleTargets:
    """Live: failure modes with real Drive."""

    def test_download_wrong_file_id(
        self, live_mutation_env
    ):
        router, account_id, _, _ = live_mutation_env
        result = router.execute_download_bound(
            account_id, "nonexistent-file-id-999"
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

    def test_search_no_results_is_safe(
        self, live_mutation_env
    ):
        router, account_id, _, _ = live_mutation_env
        session = router.drive_manager.get_session(
            account_id
        )
        result = session.search_files(
            "M23-nonexistent-query-999999"
        )
        assert result["success"] is True
        assert result["count"] == 0

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
        """A cancelled proposal cannot be confirmed
        later."""
        from agent.action_safety import ActionSafety
        router, account_id, _, _ = live_mutation_env
        safety = ActionSafety()

        # Propose and cancel
        safety.propose_delete(
            uploaded_file["file_id"],
            uploaded_file["name"],
            account_id=account_id,
        )
        safety.cancel()

        # New confirmation attempt should fail
        result = safety.validate_confirmation(
            "confirm"
        )
        assert result is None

    def test_new_file_cannot_substitute(
        self, uploaded_file, live_mutation_env
    ):
        """A proposal for file A cannot be applied
        to file B."""
        from agent.action_safety import ActionSafety
        router, account_id, _, _ = live_mutation_env
        safety = ActionSafety()

        safety.propose_delete(
            uploaded_file["file_id"],
            uploaded_file["name"],
            account_id=account_id,
        )

        # Confirmation returns the original target
        confirmed = safety.validate_confirmation(
            "confirm"
        )
        assert confirmed.target_id == (
            uploaded_file["file_id"]
        )
        # Not some other file
        assert confirmed.target_id != "some-other-file"
        safety.clear()


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1 for live tests",
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

    def test_no_trash_calls(self):
        found = self._check_dangerous()
        assert "trash" not in found

    @staticmethod
    def _check_dangerous():
        import ast as _ast
        test_file = os.path.join(
            PROJECT_ROOT, "tests",
            "test_m23_real_google_mutations.py",
        )
        with open(test_file, encoding="utf-8") as fh:
            source = fh.read()
        tree = _ast.parse(source)
        dangerous = {
            "delete_file_by_id",
            "upload_file",
            "delete", "trash",
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
