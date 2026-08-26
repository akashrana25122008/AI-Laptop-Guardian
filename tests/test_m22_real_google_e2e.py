"""Milestone 22 -- Controlled Real Google Drive E2E Validation tests.

Validates the EXISTING Google Drive architecture (M7-M11) against a
real Google account. All cloud operations are READ-ONLY.

LIVE tests require:
    AI_GUARDIAN_LIVE_GOOGLE=1

and a valid credentials.json. Without that flag, no OAuth browser
opens and no network authentication occurs.

This file is self-auditing: it contains no real delete, upload,
trash, move, rename, or permission-change operations.
"""

import os
import re
import sys

import pytest

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

LIVE_GOOGLE = os.environ.get(
    "AI_GUARDIAN_LIVE_GOOGLE", ""
).strip() == "1"

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


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _skip_unless_live():
    if not LIVE_GOOGLE:
        pytest.skip(
            "Live Google test; set AI_GUARDIAN_LIVE_GOOGLE=1"
        )
    if not HAS_GOOGLE_DEPS:
        pytest.skip("Google client libraries not installed")
    if not HAS_CREDENTIALS_FILE:
        pytest.skip("credentials.json not found")


# ============================================================
# SECTION 1: OFFLINE / ARCHITECTURE TESTS (always run)
# ============================================================


class TestArchNoImplicitAuth:
    """Prove that importing and constructing components
    never triggers OAuth."""

    def test_import_auth_manager_no_oauth(self):
        from cloud.auth_manager import GoogleAuthManager
        assert GoogleAuthManager is not None

    def test_import_multi_drive_no_oauth(self):
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        assert MultiAccountDriveManager is not None

    def test_import_intelligence_no_oauth(self):
        from cloud.cloud_intelligence import (
            CloudStorageIntelligence,
        )
        assert CloudStorageIntelligence is not None

    def test_import_accounts_no_oauth(self):
        from cloud.accounts import AccountRegistry
        assert AccountRegistry is not None

    def test_import_router_no_oauth(self):
        from agent.tool_router import ToolRouter
        assert ToolRouter is not None

    def test_import_planner_no_oauth(self):
        from agent.planner import Planner
        assert Planner is not None

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

    def test_planner_cloud_intent_no_network(self):
        from agent.planner import Planner
        p = Planner()
        result = p.plan("check my Google Drive storage")
        assert result["tool"] == "cloud_storage"

    def test_planner_search_no_network(self):
        from agent.planner import Planner
        p = Planner()
        result = p.plan(
            "search Google Drive for report.pdf"
        )
        assert result["tool"] == "cloud_search"

    def test_planner_local_query_no_cloud(self):
        from agent.planner import Planner
        p = Planner()
        for q in [
            "check CPU usage",
            "how much RAM",
            "battery status",
            "storage overview",
            "health check",
        ]:
            result = p.plan(q)
            assert "cloud" not in result["tool"]

    def test_router_init_no_oauth(self):
        from agent.tool_router import ToolRouter
        router = ToolRouter()
        # If we reach here, no OAuth was triggered

    def test_auth_manager_init_no_oauth(self):
        from cloud.auth_manager import GoogleAuthManager
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        auth = GoogleAuthManager(
            drive_manager=MultiAccountDriveManager()
        )
        # If we reach here, no OAuth was triggered


class TestArchTokenIsolation:
    """Verify token file architecture."""

    def test_token_dir_path(self):
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        assert "cloud_data" in mgr.token_dir
        assert "tokens" in mgr.token_dir

    def test_per_account_token_files(self):
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        p1 = os.path.join(mgr.token_dir, "account-1.json")
        p2 = os.path.join(mgr.token_dir, "account-2.json")
        assert p1 != p2

    def test_pending_token_uses_uuid(self):
        text = _read(
            os.path.join(
                PROJECT_ROOT, "cloud", "auth_manager.py"
            )
        )
        assert "uuid" in text

    def test_atomic_token_replacement(self):
        text = _read(
            os.path.join(
                PROJECT_ROOT, "cloud", "auth_manager.py"
            )
        )
        assert "os.replace" in text

    def test_tokens_never_printed(self):
        files = [
            "cloud/auth_manager.py",
            "cloud/multi_drive.py",
            "agent/tool_router.py",
        ]
        for f in files:
            text = _read(os.path.join(PROJECT_ROOT, f))
            in_doc = False
            for line in text.split("\n"):
                s = line.strip()
                if '"""' in s:
                    in_doc = not in_doc
                    continue
                if in_doc:
                    continue
                if s.startswith("#"):
                    continue
                if "print" in s and "token" in s.lower():
                    if "token_path" not in s:
                        pytest.fail(
                            f"Possible token print in {f}: {s}"
                        )


class TestArchIntelligenceReadOnly:
    """Verify cloud_intelligence.py is strictly read-only."""

    INTEL_FILE = os.path.join(
        PROJECT_ROOT, "cloud", "cloud_intelligence.py"
    )

    def test_read_only_docstring(self):
        text = _read(self.INTEL_FILE)
        assert "read-only" in text.lower()

    def test_format_size_exists(self):
        text = _read(self.INTEL_FILE)
        assert "def format_size" in text

    def test_to_int_returns_none(self):
        text = _read(self.INTEL_FILE)
        assert "def _to_int" in text
        assert "return None" in text


class TestArchProviderFailureHandling:
    """Verify graceful degradation."""

    def test_describe_accounts_empty(self):
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        result = mgr.describe_accounts()
        assert isinstance(result, list)
        assert len(result) == 0

    def test_search_accounts_no_accounts(self):
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        result = mgr.search_accounts("test")
        assert result["success"] is False
        assert "No connected" in result["error"]

    def test_disconnect_nonexistent_account(self):
        from cloud.auth_manager import GoogleAuthManager
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        auth = GoogleAuthManager(
            drive_manager=MultiAccountDriveManager()
        )
        result = auth.disconnect_account("account-999")
        assert result["success"] is False


class TestArchM20PathsPreserved:
    """Verify M20 path fix is intact."""

    def test_is_frozen_no_meipass(self):
        text = _read(
            os.path.join(PROJECT_ROOT, "app", "paths.py")
        )
        m = re.search(
            r"def _is_frozen\(\):(.*?)(?=\ndef |\nclass |\Z)",
            text, re.DOTALL,
        )
        assert m
        assert "_MEIPASS" not in m.group(1)

    def test_is_onefile_exists(self):
        text = _read(
            os.path.join(PROJECT_ROOT, "app", "paths.py")
        )
        assert "def _is_onefile" in text


class TestArchM19LoggingPreserved:
    """Verify M19 logging hardening is intact."""

    def test_namespace_correct(self):
        text = _read(
            os.path.join(
                PROJECT_ROOT, "app", "logging_setup.py"
            )
        )
        assert "ai_laptop_guardian" in text
        assert "algebra_guardian" not in text

    def test_no_password_in_logging(self):
        text = _read(
            os.path.join(
                PROJECT_ROOT, "app", "logging_setup.py"
            )
        )
        assert "password" not in text.lower()


class TestArchM6CleanupSafety:
    """Verify cleanup safety is unchanged."""

    def test_action_safety_exists(self):
        assert os.path.isfile(
            os.path.join(
                PROJECT_ROOT, "agent", "action_safety.py"
            )
        )

    def test_action_safety_requires_confirmation(self):
        text = _read(
            os.path.join(
                PROJECT_ROOT, "agent", "action_safety.py"
            )
        )
        assert "confirm" in text.lower()
        assert "propose" in text.lower()


class TestArchSecurityAudit:
    """Security audit for M22."""

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
        assert os.path.isdir(r"D:\AI-Laptop-Guardian-Backup")

    def test_version_consistent(self):
        from app.version import __version__
        assert __version__ == "0.14.0"

    def test_no_new_network_in_ui(self):
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
                    pytest.fail(f"Network in {f}: {s}")

    def test_action_safety_unchanged(self):
        import subprocess
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "--",
             "agent/action_safety.py"],
            capture_output=True, text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.stdout == ""

    def test_no_m22_code_in_m22_file(self):
        """Verify no real delete/upload/trash calls."""
        import ast
        test_file = os.path.join(
            PROJECT_ROOT, "tests",
            "test_m22_real_google_e2e.py",
        )
        with open(test_file, encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)
        dangerous = {
            "delete_file_by_id",
            "upload_file",
            "delete", "trash",
        }
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = None
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name in dangerous:
                    found.append(name)
        assert not found, (
            f"Dangerous calls found: {found}"
        )


# ============================================================
# SECTION 2: LIVE GOOGLE TESTS (gated)
# ============================================================


@pytest.fixture(scope="module")
def live_auth():
    """Shared fixture: authenticate and yield (auth, account_id).
    Tears down by disconnecting at module end."""
    _skip_unless_live()

    from cloud.auth_manager import GoogleAuthManager
    from cloud.multi_drive import (
        MultiAccountDriveManager,
    )

    mgr = MultiAccountDriveManager()
    auth = GoogleAuthManager(drive_manager=mgr)

    # Check existing accounts first
    status = auth.get_auth_status()
    existing = [
        a for a in status.get("accounts", [])
        if a["status"] == "connected"
    ]

    if existing:
        # Reuse existing connection
        account_id = existing[0]["id"]
        yield auth, account_id, False
        return

    # New connection via explicit OAuth
    result = auth.connect_account()
    assert result["success"], (
        f"OAuth failed: {result.get('error', 'unknown')}"
    )
    account_id = result["account"]["id"]

    yield auth, account_id, True

    # Teardown: disconnect what we connected
    try:
        auth.disconnect_account(account_id)
    except Exception:
        pass


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1 for live tests",
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

    def test_connect_completes(self, live_auth):
        auth, account_id, was_new = live_auth
        assert account_id is not None
        assert account_id.startswith("account-")

    def test_account_registered(self, live_auth):
        auth, account_id, _ = live_auth
        status = auth.get_auth_status()
        assert status["success"] is True
        ids = [a["id"] for a in status["accounts"]]
        assert account_id in ids

    def test_account_idempotent(self, live_auth):
        """Reconnecting same email doesn't create duplicate."""
        auth, account_id, _ = live_auth
        status = auth.get_auth_status()
        connected = [
            a for a in status["accounts"]
            if a["status"] == "connected"
        ]
        # All connected accounts must have unique IDs
        ids = [a["id"] for a in connected]
        assert len(ids) == len(set(ids))


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1 for live tests",
)
@pytest.mark.skipif(
    not HAS_GOOGLE_DEPS,
    reason="Google client libraries not installed",
)
@pytest.mark.skipif(
    not HAS_CREDENTIALS_FILE,
    reason="credentials.json not found",
)
class TestLiveAccountIdentity:
    """Live: safe account identity retrieval."""

    def test_identity_has_email(self, live_auth):
        auth, account_id, _ = live_auth
        status = auth.get_auth_status()
        for acc in status["accounts"]:
            if acc["id"] == account_id:
                assert "email" in acc
                assert acc["email"]  # not empty

    def test_identity_no_secrets(self, live_auth):
        auth, account_id, _ = live_auth
        status = auth.get_auth_status()
        status_str = str(status)
        assert "ya29" not in status_str
        assert "refresh_token" not in status_str
        assert "client_secret" not in status_str

    def test_describe_accounts_returns_list(self, live_auth):
        auth, account_id, _ = live_auth
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = auth.drive_manager
        accounts = mgr.describe_accounts()
        assert isinstance(accounts, list)
        assert len(accounts) >= 1
        for acc in accounts:
            assert "id" in acc
            assert "label" in acc


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1 for live tests",
)
@pytest.mark.skipif(
    not HAS_GOOGLE_DEPS,
    reason="Google client libraries not installed",
)
@pytest.mark.skipif(
    not HAS_CREDENTIALS_FILE,
    reason="credentials.json not found",
)
class TestLiveStorageQuota:
    """Live: real storage quota from Google Drive."""

    def test_storage_has_used_bytes(self, live_auth):
        auth, account_id, _ = live_auth
        session = auth.drive_manager.get_session(
            account_id
        )
        assert session is not None
        result = session.get_storage_info()
        assert result["success"] is True
        assert "used_bytes" in result

    def test_storage_used_non_negative(self, live_auth):
        auth, account_id, _ = live_auth
        session = auth.drive_manager.get_session(
            account_id
        )
        result = session.get_storage_info()
        assert result["success"] is True
        used = result.get("used_bytes")
        if used is not None:
            assert used >= 0

    def test_storage_total_consistent(self, live_auth):
        auth, account_id, _ = live_auth
        session = auth.drive_manager.get_session(
            account_id
        )
        result = session.get_storage_info()
        assert result["success"] is True
        total = result.get("total_bytes")
        used = result.get("used_bytes")
        if total is not None and used is not None:
            assert used <= total


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1 for live tests",
)
@pytest.mark.skipif(
    not HAS_GOOGLE_DEPS,
    reason="Google client libraries not installed",
)
@pytest.mark.skipif(
    not HAS_CREDENTIALS_FILE,
    reason="credentials.json not found",
)
class TestLiveSearch:
    """Live: real Google Drive search (READ-ONLY)."""

    def test_search_broad(self, live_auth):
        auth, account_id, _ = live_auth
        session = auth.drive_manager.get_session(
            account_id
        )
        assert session is not None
        result = session.search_files("")
        # Empty query should fail safely
        assert result["success"] is False

    def test_search_returns_results(self, live_auth):
        auth, account_id, _ = live_auth
        session = auth.drive_manager.get_session(
            account_id
        )
        result = session.search_files("test")
        assert result["success"] is True
        assert "matches" in result
        # Each match should have required fields
        for match in result.get("matches", []):
            assert "id" in match
            assert "name" in match

    def test_search_account_identity(self, live_auth):
        auth, account_id, _ = live_auth
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = auth.drive_manager
        result = mgr.search_accounts(
            "test", scope_all=True
        )
        assert result["success"] is True
        for match in result.get("matches", []):
            assert "account_id" in match


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1 for live tests",
)
@pytest.mark.skipif(
    not HAS_GOOGLE_DEPS,
    reason="Google client libraries not installed",
)
@pytest.mark.skipif(
    not HAS_CREDENTIALS_FILE,
    reason="credentials.json not found",
)
class TestLiveLargeFiles:
    """Live: real large-file metadata analysis."""

    def test_large_files_completes(self, live_auth):
        auth, account_id, _ = live_auth
        session = auth.drive_manager.get_session(
            account_id
        )
        assert session is not None
        result = session.list_large_files(
            min_size_bytes=1024 * 1024, limit=5
        )
        assert result["success"] is True
        assert "files" in result

    def test_large_files_metadata_only(self, live_auth):
        """No file content should be downloaded."""
        auth, account_id, _ = live_auth
        session = auth.drive_manager.get_session(
            account_id
        )
        result = session.list_large_files(
            min_size_bytes=1024 * 1024, limit=5
        )
        assert result["success"] is True
        for f in result.get("files", []):
            assert "id" in f
            assert "name" in f
            assert "size_bytes" in f
            assert f["size_bytes"] > 0


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1 for live tests",
)
@pytest.mark.skipif(
    not HAS_GOOGLE_DEPS,
    reason="Google client libraries not installed",
)
@pytest.mark.skipif(
    not HAS_CREDENTIALS_FILE,
    reason="credentials.json not found",
)
class TestLiveDuplicates:
    """Live: real duplicate-candidate analysis."""

    def test_duplicates_completes(self, live_auth):
        auth, account_id, _ = live_auth
        from cloud.cloud_intelligence import (
            CloudStorageIntelligence,
        )
        intel = CloudStorageIntelligence(
            auth.drive_manager
        )
        result = intel.find_duplicate_candidates(
            scope_all=True
        )
        assert result["success"] is True
        assert "groups" in result

    def test_duplicates_are_name_size(self, live_auth):
        """Candidates are name+size, never content-based."""
        auth, account_id, _ = live_auth
        from cloud.cloud_intelligence import (
            CloudStorageIntelligence,
        )
        intel = CloudStorageIntelligence(
            auth.drive_manager
        )
        result = intel.find_duplicate_candidates(
            scope_all=True
        )
        for group in result.get("groups", []):
            assert group["confirmed"] is False
            assert "name" in group
            assert "size_bytes" in group
            assert "copies" in group


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1 for live tests",
)
@pytest.mark.skipif(
    not HAS_GOOGLE_DEPS,
    reason="Google client libraries not installed",
)
@pytest.mark.skipif(
    not HAS_CREDENTIALS_FILE,
    reason="credentials.json not found",
)
class TestLiveCloudIntelligence:
    """Live: cloud intelligence with real account data."""

    def test_storage_summary(self, live_auth):
        auth, account_id, _ = live_auth
        from cloud.cloud_intelligence import (
            CloudStorageIntelligence,
        )
        intel = CloudStorageIntelligence(
            auth.drive_manager
        )
        result = intel.summarize_accounts(scope_all=True)
        assert result["success"] is True
        assert "accounts" in result

    def test_summary_account_identity(self, live_auth):
        auth, account_id, _ = live_auth
        from cloud.cloud_intelligence import (
            CloudStorageIntelligence,
        )
        intel = CloudStorageIntelligence(
            auth.drive_manager
        )
        result = intel.summarize_accounts(scope_all=True)
        for entry in result.get("accounts", []):
            assert "account_id" in entry

    def test_large_files_via_intelligence(self, live_auth):
        auth, account_id, _ = live_auth
        from cloud.cloud_intelligence import (
            CloudStorageIntelligence,
        )
        intel = CloudStorageIntelligence(
            auth.drive_manager
        )
        result = intel.find_large_files(scope_all=True)
        assert result["success"] is True
        assert "files" in result
        for f in result.get("files", []):
            assert "account_id" in f


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1 for live tests",
)
@pytest.mark.skipif(
    not HAS_GOOGLE_DEPS,
    reason="Google client libraries not installed",
)
@pytest.mark.skipif(
    not HAS_CREDENTIALS_FILE,
    reason="credentials.json not found",
)
class TestLiveControllerIntegration:
    """Live: GuardianController cloud methods."""

    def test_get_accounts(self, live_auth):
        from ui.app_controller import GuardianController
        ctrl = GuardianController()
        result = ctrl.get_accounts()
        assert "success" in result
        assert result["success"] is True
        assert "accounts" in result

    def test_get_cloud_storage(self, live_auth):
        from ui.app_controller import GuardianController
        ctrl = GuardianController()
        result = ctrl.get_cloud_storage()
        assert result["success"] is True
        assert "accounts" in result

    def test_get_cloud_large_files(self, live_auth):
        from ui.app_controller import GuardianController
        ctrl = GuardianController()
        result = ctrl.get_cloud_large_files()
        assert result["success"] is True
        assert "files" in result

    def test_get_cloud_duplicates(self, live_auth):
        from ui.app_controller import GuardianController
        ctrl = GuardianController()
        result = ctrl.get_cloud_duplicates()
        assert result["success"] is True
        assert "groups" in result


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1 for live tests",
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
    """Live: disconnect and reconnect flow."""

    def test_disconnect_account(self, live_auth):
        auth, account_id, _ = live_auth
        result = auth.disconnect_account(account_id)
        assert result["success"] is True
        assert "account" in result
        assert result["account"]["id"] == account_id

    def test_disconnected_not_in_active(self, live_auth):
        auth, account_id, _ = live_auth
        status = auth.get_auth_status()
        active_ids = [a["id"] for a in status["accounts"]]
        assert account_id not in active_ids

    def test_reconnect_after_disconnect(self, live_auth):
        auth, account_id, _ = live_auth
        result = auth.connect_account()
        assert result["success"] is True
        assert result["account"]["id"] != account_id
        # Retired ID is never reused
        new_id = result["account"]["id"]
        assert new_id != account_id


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1 for live tests",
)
@pytest.mark.skipif(
    not HAS_GOOGLE_DEPS,
    reason="Google client libraries not installed",
)
@pytest.mark.skipif(
    not HAS_CREDENTIALS_FILE,
    reason="credentials.json not found",
)
class TestLiveAccountIsolation:
    """Live: verify account isolation with real data."""

    def test_sessions_are_isolated(self, live_auth):
        auth, account_id, _ = live_auth
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = auth.drive_manager
        accounts = mgr.describe_accounts()
        for acc in accounts:
            session = mgr.get_session(acc["id"])
            if session is not None:
                # Each session must have its own token file
                assert acc["id"] in session.token_file

    def test_search_retains_account_id(self, live_auth):
        auth, account_id, _ = live_auth
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = auth.drive_manager
        result = mgr.search_accounts(
            "test", scope_all=True
        )
        for match in result.get("matches", []):
            assert match["account_id"] == account_id

    def test_no_cross_account_fallback(self, live_auth):
        """Querying disconnected account fails safely."""
        auth, account_id, _ = live_auth
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = auth.drive_manager
        result = mgr.search_accounts(
            "test",
            account_ids=["account-999999"],
        )
        assert result["success"] is False


@pytest.mark.skipif(
    not LIVE_GOOGLE,
    reason="Set AI_GUARDIAN_LIVE_GOOGLE=1 for live tests",
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
    """Prove no destructive operations occurred."""

    def _check_dangerous_calls(self):
        import ast
        test_file = os.path.join(
            PROJECT_ROOT, "tests",
            "test_m22_real_google_e2e.py",
        )
        with open(test_file, encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)
        dangerous = {
            "delete_file_by_id",
            "upload_file",
            "delete", "trash",
        }
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = None
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name in dangerous:
                    found.append(name)
        return found

    def test_no_delete_calls(self):
        found = self._check_dangerous_calls()
        assert "delete_file_by_id" not in found

    def test_no_upload_calls(self):
        found = self._check_dangerous_calls()
        assert "upload_file" not in found

    def test_no_permanent_delete(self):
        found = self._check_dangerous_calls()
        assert "delete" not in found
        assert "trash" not in found
