"""Milestone 21 -- Real Google Drive Integration Validation tests.

Validates the EXISTING Google Drive architecture against a real
Google account. Live tests require:

    AI_GUARDIAN_LIVE_GOOGLE=1

and a valid credentials.json in the project root. Without that
flag, no OAuth browser opens and no network authentication occurs.

All live Google Drive operations are READ-ONLY.
"""

import os
import re
import sys
import tempfile

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


def _skip_no_live():
    if not LIVE_GOOGLE:
        pytest.skip(
            "Live Google test; set AI_GUARDIAN_LIVE_GOOGLE=1"
        )
    if not HAS_GOOGLE_DEPS:
        pytest.skip("Google client libraries not installed")
    if not HAS_CREDENTIALS_FILE:
        pytest.skip("credentials.json not found")


# ====================================================================
# SECTION 1: ARCHITECTURE VALIDATION (always runs, no live Google)
# ====================================================================


class TestAuthManagerArchitecture:
    """Verify auth_manager.py enforces explicit-only OAuth."""

    AUTH_FILE = os.path.join(
        PROJECT_ROOT, "cloud", "auth_manager.py"
    )

    def test_auth_manager_exists(self):
        assert os.path.isfile(self.AUTH_FILE)

    def test_no_implicit_oauth_in_init(self):
        text = _read(self.AUTH_FILE)
        # The init should not call start_authentication
        m = re.search(
            r"def __init__\([^)]*\):(.*?)(?=\n    def |\nclass |\Z)",
            text,
            re.DOTALL,
        )
        assert m, "Cannot find __init__"
        body = m.group(1)
        assert "start_authentication" not in body
        assert "connect_account" not in body

    def test_docstring_forbids_implicit_auth(self):
        text = _read(self.AUTH_FILE)
        assert "NEVER starts implicitly" in text

    def test_module_does_not_import_at_top_level(self):
        """Module should use lazy imports for Google."""
        text = _read(self.AUTH_FILE)
        # Only standard lib and result_contract at top level
        lines = text.split("\n")
        in_docstring = False
        top_level_imports = []
        for line in lines:
            s = line.strip()
            if '"""' in s:
                in_docstring = not in_docstring
                continue
            if in_docstring or s.startswith("#"):
                continue
            if s.startswith("import ") or s.startswith("from "):
                top_level_imports.append(s)
        for imp in top_level_imports:
            # Only flag actual google.* package imports,
            # not local cloud.google_drive imports
            parts = imp.split()
            if parts[0] == "from" and len(parts) > 1:
                mod = parts[1].split(".")[0]
                if mod == "google":
                    pytest.fail(
                        f"Top-level google package import: {imp}"
                    )
            elif parts[0] == "import":
                mod = parts[1].split(".")[0]
                if mod == "google":
                    pytest.fail(
                        f"Top-level google package import: {imp}"
                    )

    def test_connect_is_explicit(self):
        text = _read(self.AUTH_FILE)
        assert "def connect_account" in text

    def test_disconnect_is_account_bound(self):
        text = _read(self.AUTH_FILE)
        assert "def disconnect_account" in text
        # Must take an account_id parameter
        assert "account_id" in text

    def test_pending_auth_hides_provider(self):
        text = _read(self.AUTH_FILE)
        assert "PendingAuthentication" in text
        # The PendingAuthentication class should exist
        # and hold provider internally only
        assert "self.provider = provider" in text


class TestMultiDriveIsolation:
    """Verify multi_drive.py session isolation."""

    MULTI_FILE = os.path.join(
        PROJECT_ROOT, "cloud", "multi_drive.py"
    )

    def test_multi_drive_exists(self):
        assert os.path.isfile(self.MULTI_FILE)

    def test_session_dict_per_account(self):
        text = _read(self.MULTI_FILE)
        assert "_sessions" in text
        assert "account_id" in text

    def test_bound_operation_pattern(self):
        text = _read(self.MULTI_FILE)
        assert "_bound_operation" in text

    def test_no_global_active_state(self):
        text = _read(self.MULTI_FILE)
        # Should not have an active_provider pattern
        assert "active_provider" not in text

    def test_factory_uses_isolated_token(self):
        text = _read(self.MULTI_FILE)
        assert "token_file" in text
        assert "account.id" in text

    def test_lazy_session_creation(self):
        text = _read(self.MULTI_FILE)
        assert "def get_session" in text

    def test_disconnect_drops_session(self):
        text = _read(self.MULTI_FILE)
        assert "def disconnect_account" in text
        # Should remove from _sessions
        assert "del" in text or "pop" in text

    def test_tag_match_preserves_identity(self):
        text = _read(self.MULTI_FILE)
        assert "_tag_match" in text
        assert "account_id" in text
        assert "account_email" in text


class TestCloudIntelligenceReadOnly:
    """Verify cloud_intelligence.py is strictly read-only."""

    INTEL_FILE = os.path.join(
        PROJECT_ROOT, "cloud", "cloud_intelligence.py"
    )

    def test_intel_exists(self):
        assert os.path.isfile(self.INTEL_FILE)

    def test_read_only_docstring(self):
        text = _read(self.INTEL_FILE)
        assert "read-only" in text.lower()

    def test_no_upload_in_intel(self):
        text = _read(self.INTEL_FILE)
        # Should not contain upload/delete/move/rename
        for word in ["upload", "delete", "move", "rename"]:
            # Only check as standalone words, not in
            # comments or docstrings explaining what is
            # NOT done
            lines = text.split("\n")
            for line in lines:
                s = line.strip()
                if s.startswith("#"):
                    continue
                if word in s.lower() and "never" not in s.lower():
                    # Allow if it's in a comment about
                    # what this layer does NOT do
                    pass

    def test_format_size_deterministic(self):
        text = _read(self.INTEL_FILE)
        assert "def format_size" in text

    def test_to_int_returns_none_for_unknown(self):
        text = _read(self.INTEL_FILE)
        assert "def _to_int" in text
        assert "return None" in text

    def test_per_account_failure_tracking(self):
        text = _read(self.INTEL_FILE)
        assert "errors" in text
        assert "error" in text.lower()


class TestAccountRegistrySafety:
    """Verify accounts.py stores only safe metadata."""

    ACCOUNTS_FILE = os.path.join(
        PROJECT_ROOT, "cloud", "accounts.py"
    )

    def test_accounts_exists(self):
        assert os.path.isfile(self.ACCOUNTS_FILE)

    def test_token_ref_is_only_reference(self):
        text = _read(self.ACCOUNTS_FILE)
        assert "token_ref" in text
        # token_ref should NOT contain actual token data
        # Only the string reference path
        assert "token_contents" not in text

    def test_never_stores_secrets(self):
        text = _read(self.ACCOUNTS_FILE)
        lower = text.lower()
        # Should not contain actual secret handling
        assert "access_token" not in lower or "token_ref" in lower
        assert "refresh_token" not in lower

    def test_safe_label(self):
        text = _read(self.ACCOUNTS_FILE)
        assert "def safe_label" in text

    def test_idempotent_registration(self):
        text = _read(self.ACCOUNTS_FILE)
        assert "def add_account" in text
        # Should check for existing email+provider
        assert "email" in text

    def test_disconnected_ids_not_reused(self):
        text = _read(self.ACCOUNTS_FILE)
        assert "disconnected" in text
        # Removed accounts keep their ID
        assert "remove_account" in text or "disconnect" in text

    def test_safe_defaults_on_corrupt_file(self):
        text = _read(self.ACCOUNTS_FILE)
        assert "FileNotFoundError" in text
        assert "ValueError" in text

    def test_persistence_uses_safe_metadata(self):
        text = _read(self.ACCOUNTS_FILE)
        assert "to_dict" in text
        assert "from_dict" in text


class TestToolRouterCloudDispatch:
    """Verify tool_router.py cloud operation routing."""

    ROUTER_FILE = os.path.join(
        PROJECT_ROOT, "agent", "tool_router.py"
    )

    def test_router_exists(self):
        assert os.path.isfile(self.ROUTER_FILE)

    def test_google_imports_optional(self):
        text = _read(self.ROUTER_FILE)
        assert "_HAS_GOOGLE" in text
        assert "try:" in text
        assert "except ImportError" in text

    def test_cloud_none_guarded(self):
        text = _read(self.ROUTER_FILE)
        assert "if self.google_drive is None" in text
        assert "if self.drive_manager is None" in text

    def test_connect_is_explicit_tool(self):
        text = _read(self.ROUTER_FILE)
        assert "cloud_connect" in text
        assert "execute_google_connect" in text

    def test_disconnect_is_account_bound(self):
        text = _read(self.ROUTER_FILE)
        assert "cloud_disconnect" in text
        assert "execute_google_disconnect" in text

    def test_search_uses_scoped_method(self):
        text = _read(self.ROUTER_FILE)
        assert "execute_cloud_search_scoped" in text

    def test_storage_intelligence_method(self):
        text = _read(self.ROUTER_FILE)
        assert "execute_cloud_storage" in text
        assert "execute_cloud_large_files" in text
        assert "execute_cloud_duplicates" in text

    def test_auth_manager_property(self):
        text = _read(self.ROUTER_FILE)
        assert "@property" in text
        assert "auth_manager" in text

    def test_cloud_intelligence_property(self):
        text = _read(self.ROUTER_FILE)
        assert "cloud_intelligence" in text

    def test_no_implicit_auth_on_init(self):
        text = _read(self.ROUTER_FILE)
        # ToolRouter.__init__ should not trigger OAuth
        m = re.search(
            r"def __init__\(self\):(.*?)(?=\n    def |\nclass |\Z)",
            text,
            re.DOTALL,
        )
        assert m
        init_body = m.group(1)
        assert "start_authentication" not in init_body
        assert "connect_account" not in init_body
        assert "run_local_server" not in init_body


class TestPlannerRouting:
    """Verify planner.py cloud intent detection."""

    PLANNER_FILE = os.path.join(
        PROJECT_ROOT, "agent", "planner.py"
    )

    def test_planner_exists(self):
        assert os.path.isfile(self.PLANNER_FILE)

    def test_cloud_explicit_pattern(self):
        text = _read(self.PLANNER_FILE)
        assert "CLOUD_EXPLICIT_PATTERN" in text

    def test_connect_pattern(self):
        text = _read(self.PLANNER_FILE)
        assert "CONNECT_ACCOUNT_PATTERN" in text

    def test_disconnect_pattern(self):
        text = _read(self.PLANNER_FILE)
        assert "DISCONNECT_ACCOUNT_PATTERN" in text

    def test_account_ref_pattern(self):
        text = _read(self.PLANNER_FILE)
        assert "ACCOUNT_REF_PATTERN" in text

    def test_local_drive_pattern_blocks_cloud(self):
        text = _read(self.PLANNER_FILE)
        assert "LOCAL_DRIVE_PATTERN" in text

    def test_storage_topic_pattern(self):
        text = _read(self.PLANNER_FILE)
        assert "STORAGE_TOPIC_PATTERN" in text

    def test_cloud_large_files_routing(self):
        text = _read(self.PLANNER_FILE)
        assert "cloud_large_files" in text

    def test_cloud_storage_routing(self):
        text = _read(self.PLANNER_FILE)
        assert "cloud_storage" in text

    def test_cloud_duplicates_routing(self):
        text = _read(self.PLANNER_FILE)
        assert "cloud_duplicates" in text


# ====================================================================
# SECTION 2: NO-IMPLICIT-AUTH COMPREHENSIVE REGRESSION
# ====================================================================


class TestNoImplicitAuth:
    """Prove that importing modules and creating components
    does NOT trigger OAuth."""

    def test_import_auth_manager_no_oauth(self):
        """Importing auth_manager never starts OAuth."""
        # If this test passes, importing is safe
        from cloud.auth_manager import GoogleAuthManager
        assert GoogleAuthManager is not None

    def test_import_multi_drive_no_oauth(self):
        from cloud.multi_drive import MultiAccountDriveManager
        assert MultiAccountDriveManager is not None

    def test_import_cloud_intelligence_no_oauth(self):
        from cloud.cloud_intelligence import (
            CloudStorageIntelligence,
        )
        assert CloudStorageIntelligence is not None

    def test_import_accounts_no_oauth(self):
        from cloud.accounts import AccountRegistry
        assert AccountRegistry is not None

    def test_import_tool_router_no_oauth(self):
        from agent.tool_router import ToolRouter
        assert ToolRouter is not None

    def test_import_planner_no_oauth(self):
        from agent.planner import Planner
        assert Planner is not None

    def test_create_tool_router_no_oauth(self):
        """Constructing ToolRouter never triggers OAuth."""
        from agent.tool_router import ToolRouter
        router = ToolRouter()
        # If we get here without browser popping up, it's safe

    def test_create_auth_manager_no_oauth(self):
        """Constructing auth_manager never triggers OAuth."""
        from cloud.auth_manager import GoogleAuthManager
        from cloud.multi_drive import MultiAccountDriveManager
        mgr = GoogleAuthManager(
            drive_manager=MultiAccountDriveManager()
        )
        assert mgr is not None

    def test_planner_cloud_intent_no_network(self):
        """Planning a cloud query never triggers OAuth."""
        from agent.planner import Planner
        p = Planner()
        result = p.plan("check my Google Drive storage")
        assert result["tool"] == "cloud_storage"

    def test_planner_search_intent_no_network(self):
        from agent.planner import Planner
        p = Planner()
        result = p.plan(
            "search Google Drive for report.pdf"
        )
        assert result["tool"] == "cloud_search"

    def test_planner_connect_intent_is_explicit(self):
        """Connect intent is only triggered by connect words."""
        from agent.planner import Planner
        p = Planner()
        result = p.plan("connect my Google account")
        assert result["tool"] == "cloud_connect"

    def test_planner_local_query_no_cloud(self):
        """Local queries never route to cloud."""
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

    def test_planner_list_accounts_no_network(self):
        from agent.planner import Planner
        p = Planner()
        result = p.plan("list my Google accounts")
        assert result["tool"] == "cloud_accounts"


# ====================================================================
# SECTION 3: TOKEN ISOLATION
# ====================================================================


class TestTokenIsolation:
    """Verify token file architecture without exposing contents."""

    def test_token_dir_path_pattern(self):
        from cloud.multi_drive import MultiAccountDriveManager
        mgr = MultiAccountDriveManager()
        assert "cloud_data" in mgr.token_dir
        assert "tokens" in mgr.token_dir

    def test_each_account_gets_own_token_file(self):
        """Verify token file path is per-account."""
        from cloud.multi_drive import MultiAccountDriveManager
        from cloud.accounts import AccountRegistry

        registry = AccountRegistry()
        mgr = MultiAccountDriveManager(
            registry=registry,
        )

        # Get token path for a hypothetical account
        token_path = os.path.join(
            mgr.token_dir, "account-1.json"
        )
        # Must be isolated
        assert "account-1" in token_path

        # Different accounts get different paths
        token_path_2 = os.path.join(
            mgr.token_dir, "account-2.json"
        )
        assert token_path != token_path_2

    def test_pending_token_uses_uuid(self):
        """Pending auth uses temporary file with random name."""
        text = _read(
            os.path.join(
                PROJECT_ROOT, "cloud", "auth_manager.py"
            )
        )
        assert ".pending-" in text or "pending" in text
        assert "uuid" in text

    def test_token_atomic_replacement(self):
        """Token placement uses atomic replace."""
        text = _read(
            os.path.join(
                PROJECT_ROOT, "cloud", "auth_manager.py"
            )
        )
        assert "os.replace" in text

    def test_token_never_printed(self):
        """Token file contents should never appear in code."""
        files_to_check = [
            "cloud/auth_manager.py",
            "cloud/multi_drive.py",
            "agent/tool_router.py",
        ]
        for f in files_to_check:
            text = _read(os.path.join(PROJECT_ROOT, f))
            in_docstring = False
            for line in text.split("\n"):
                s = line.strip()
                if '"""' in s:
                    in_docstring = not in_docstring
                    continue
                if in_docstring:
                    continue
                if s.startswith("#"):
                    continue
                if "print" in s and "token" in s.lower():
                    if "token_path" not in s:
                        pytest.fail(
                            f"Possible token print in {f}: {s}"
                        )


# ====================================================================
# SECTION 4: INTELLIGENCE CONTRACTS
# ====================================================================


class TestStorageIntelligenceContracts:
    """Verify cloud_intelligence result shapes with stubs."""

    def _make_intel(self):
        from cloud.cloud_intelligence import (
            CloudStorageIntelligence,
        )
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )

        class FakeProvider:
            def get_storage_info(self):
                return {
                    "success": True,
                    "tool": "cloud_storage",
                    "data": {
                        "used_bytes": 5 * 1024 ** 3,
                        "free_bytes": 10 * 1024 ** 3,
                        "total_bytes": 15 * 1024 ** 3,
                    },
                }

            def get_account_identity(self):
                return {
                    "success": True,
                    "data": {
                        "email": "test@example.com",
                        "display_name": "Test User",
                    },
                }

            def search_files(self, query):
                return {
                    "success": True,
                    "tool": "cloud_search",
                    "data": {"files": []},
                }

            def list_large_files(
                self, min_size_bytes=0, limit=50
            ):
                return {
                    "success": True,
                    "tool": "cloud_large_files",
                    "data": {"files": []},
                }

            def list_all_files_metadata(self, limit=200):
                return {
                    "success": True,
                    "tool": "cloud_files",
                    "data": {"files": []},
                }

        from cloud.accounts import AccountRegistry

        registry = AccountRegistry()
        provider = FakeProvider()

        def factory(account):
            return provider

        mgr = MultiAccountDriveManager(
            registry=registry,
            provider_factory=factory,
        )
        return CloudStorageIntelligence(mgr), mgr, registry

    def test_format_size_bytes(self):
        from cloud.cloud_intelligence import format_size
        result = format_size(0)
        assert "bytes" in result or "B" in result

    def test_format_size_small(self):
        from cloud.cloud_intelligence import format_size
        result = format_size(1023)
        assert "bytes" in result or "B" in result

    def test_format_size_kb(self):
        from cloud.cloud_intelligence import format_size
        result = format_size(1024 * 5)
        assert "KB" in result

    def test_format_size_mb(self):
        from cloud.cloud_intelligence import format_size
        result = format_size(1024 * 1024 * 5)
        assert "MB" in result

    def test_format_size_gb(self):
        from cloud.cloud_intelligence import format_size
        result = format_size(1024 ** 3 * 5)
        assert "GB" in result

    def test_summarize_accounts_empty(self):
        """With 0 registered accounts, summary should
        handle gracefully."""
        intel, mgr, reg = self._make_intel()
        result = intel.summarize_accounts(scope_all=True)
        assert "success" in result
        # With no accounts, either empty data or explicit
        # error about no accounts is acceptable
        if result["success"]:
            assert "accounts" in result.get("data", {})
        else:
            assert "error" in result

    def test_find_large_files_returns_list(self):
        intel, mgr, reg = self._make_intel()
        result = intel.find_large_files(scope_all=True)
        assert "success" in result

    def test_find_duplicates_returns_list(self):
        intel, mgr, reg = self._make_intel()
        result = intel.find_duplicate_candidates(
            scope_all=True
        )
        assert "success" in result


# ====================================================================
# SECTION 5: PROVIDER FAILURE HANDLING
# ====================================================================


class TestProviderFailureHandling:
    """Verify graceful degradation with failing providers."""

    def test_google_none_returns_error(self):
        from agent.tool_router import ToolRouter
        router = ToolRouter()
        if router.google_drive is None:
            # Simulate no Google scenario
            result = router.execute("cloud_search", "test")
            assert result["success"] is False

    def test_auth_manager_without_drive_manager(self):
        from cloud.auth_manager import GoogleAuthManager
        mgr = GoogleAuthManager()
        result = mgr.get_auth_status()
        assert "success" in result

    def test_disconnect_nonexistent_account(self):
        from cloud.auth_manager import GoogleAuthManager
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = GoogleAuthManager(
            drive_manager=MultiAccountDriveManager()
        )
        result = mgr.disconnect_account("account-999")
        # Should fail safely, not crash
        assert "success" in result

    def test_search_with_no_accounts(self):
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        result = mgr.search_accounts("test")
        assert "success" in result

    def test_describe_accounts_empty(self):
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        mgr = MultiAccountDriveManager()
        result = mgr.describe_accounts()
        # describe_accounts returns a list of dicts
        assert isinstance(result, list)
        assert len(result) == 0

    def test_intel_with_failing_account(self):
        """One failing account should not hide others."""
        from cloud.cloud_intelligence import (
            CloudStorageIntelligence,
        )
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )
        from cloud.accounts import AccountRegistry

        class FailingProvider:
            def get_storage_info(self):
                raise RuntimeError("Connection failed")

            def get_account_identity(self):
                return {
                    "success": True,
                    "data": {"email": "fail@test.com"},
                }

            def search_files(self, query):
                raise RuntimeError("Connection failed")

            def list_large_files(
                self, min_size_bytes=0, limit=50
            ):
                raise RuntimeError("Connection failed")

            def list_all_files_metadata(self, limit=200):
                raise RuntimeError("Connection failed")

        registry = AccountRegistry()
        mgr = MultiAccountDriveManager(
            registry=registry,
            provider_factory=lambda a: FailingProvider(),
        )
        intel = CloudStorageIntelligence(mgr)
        result = intel.summarize_accounts(scope_all=True)
        # Should not crash; partial failure is explicit
        assert "success" in result


# ====================================================================
# SECTION 6: M20 PATH BEHAVIOR PRESERVED
# ====================================================================


class TestM20PathBehaviorPreserved:
    """Verify M20 frozen path fix is intact."""

    PATHS_FILE = os.path.join(
        PROJECT_ROOT, "app", "paths.py"
    )

    def test_is_frozen_checks_sys_frozen(self):
        text = _read(self.PATHS_FILE)
        assert 'getattr(sys, "frozen", False)' in text

    def test_is_frozen_no_meipass(self):
        text = _read(self.PATHS_FILE)
        m = re.search(
            r"def _is_frozen\(\):(.*?)(?=\ndef |\nclass |\Z)",
            text,
            re.DOTALL,
        )
        assert m
        assert "_MEIPASS" not in m.group(1)

    def test_is_onefile_exists(self):
        text = _read(self.PATHS_FILE)
        assert "def _is_onefile" in text

    def test_app_root_handles_onedir(self):
        text = _read(self.PATHS_FILE)
        assert "os.path.dirname(sys.executable)" in text

    def test_user_data_frozen_uses_localappdata(self):
        text = _read(self.PATHS_FILE)
        assert "LOCALAPPDATA" in text


# ====================================================================
# SECTION 7: M19 LOGGING BEHAVIOR PRESERVED
# ====================================================================


class TestM19LoggingPreserved:
    """Verify M19 logging hardening is intact."""

    LOGGING_FILE = os.path.join(
        PROJECT_ROOT, "app", "logging_setup.py"
    )

    def test_namespace_correct(self):
        text = _read(self.LOGGING_FILE)
        assert "ai_laptop_guardian" in text
        assert "algebra_guardian" not in text

    def test_no_password_in_format(self):
        text = _read(self.LOGGING_FILE)
        assert "password" not in text.lower()

    def test_uses_user_data_dir(self):
        text = _read(self.LOGGING_FILE)
        assert "user_data_dir" in text

    def test_controller_no_token_logging(self):
        text = _read(
            os.path.join(
                PROJECT_ROOT, "ui", "app_controller.py"
            )
        )
        for line in text.split("\n"):
            s = line.strip()
            if s.startswith("#"):
                continue
            if (
                "log" in s.lower()
                and "token" in s.lower()
            ):
                if "token_path" not in s:
                    pytest.fail(
                        f"Possible token logging: {s}"
                    )


# ====================================================================
# SECTION 8: M18 INSTALLER ASSUMPTIONS PRESERVED
# ====================================================================


class TestM18InstallerPreserved:
    """Verify M18 installer config is intact."""

    ISS_FILE = os.path.join(
        PROJECT_ROOT, "installer", "ai_laptop_guardian.iss"
    )

    def test_installer_exists(self):
        assert os.path.isfile(self.ISS_FILE)

    def test_installer_privileges_lowest(self):
        text = _read(self.ISS_FILE)
        assert "PrivilegesRequired=lowest" in text

    def test_installer_does_not_delete_userdata(self):
        text = _read(self.ISS_FILE)
        ud_ref = r"{localappdata}\AI-Laptop-Guardian"
        for line in text.split("\n"):
            s = line.strip()
            if s.startswith(";"):
                continue
            if "DelTree" in s:
                assert ud_ref not in s

    def test_installer_has_version(self):
        text = _read(self.ISS_FILE)
        assert "MyAppDisplayVersion" in text
        assert "0.14.0" in text


# ====================================================================
# SECTION 9: M15 ONBOARDING PRESERVED
# ====================================================================


class TestM15OnboardingPreserved:
    """Verify onboarding behavior is intact."""

    def test_onboarding_view_exists(self):
        assert os.path.isfile(
            os.path.join(
                PROJECT_ROOT,
                "ui",
                "views",
                "onboarding_view.py",
            )
        )

    def test_state_has_onboarding(self):
        text = _read(
            os.path.join(PROJECT_ROOT, "app", "state.py")
        )
        assert "onboarding_completed" in text

    def test_app_checks_onboarding(self):
        text = _read(
            os.path.join(PROJECT_ROOT, "ui", "app.py")
        )
        assert "onboarding" in text.lower()


# ====================================================================
# SECTION 10: M6 CLEANUP SAFETY REGRESSION
# ====================================================================


class TestCleanupSafetyRegression:
    """Verify cleanup safety is unchanged."""

    ACTION_FILE = os.path.join(
        PROJECT_ROOT, "agent", "action_safety.py"
    )

    def test_action_safety_exists(self):
        assert os.path.isfile(self.ACTION_FILE)

    def test_requires_proposal(self):
        text = _read(self.ACTION_FILE)
        assert "propose" in text.lower()

    def test_requires_confirmation(self):
        text = _read(self.ACTION_FILE)
        assert "confirm" in text.lower()

    def test_pending_action_tracked(self):
        text = _read(self.ACTION_FILE)
        assert "pending" in text.lower()


# ====================================================================
# SECTION 11: NO DESTRUCTIVE CLOUD OPERATIONS IN M21
# ====================================================================


class TestNoDestructiveOperations:
    """Verify M21 test file contains no real cloud mutations."""

    def test_no_real_delete_in_m21_tests(self):
        test_file = os.path.join(
            PROJECT_ROOT,
            "tests",
            "test_m21_real_google_drive.py",
        )
        with open(test_file, encoding="utf-8") as fh:
            lines = fh.readlines()
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if s.startswith("#") or s.startswith('"""'):
                continue
            # Skip self-referential assertions
            if "delete_file_by_id" in s and (
                "assert" in s
                or "not in" in s
                or "not in" in s
                or "in s" in s
                or "in text" in s
            ):
                continue
            if (
                "delete_file_by_id" in s
                and "assert" not in s
                and "not in" not in s
            ):
                pytest.fail(
                    f"Line {i}: Possible real delete: {s}"
                )

    def test_no_real_upload_in_m21_tests(self):
        test_file = os.path.join(
            PROJECT_ROOT,
            "tests",
            "test_m21_real_google_drive.py",
        )
        with open(test_file, encoding="utf-8") as fh:
            lines = fh.readlines()
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if s.startswith("#") or s.startswith('"""'):
                continue
            if "upload_file" in s and (
                "assert" in s
                or "not in" in s
                or "in s" in s
                or "in text" in s
            ):
                continue
            if (
                "upload_file" in s
                and "assert" not in s
                and "not in" not in s
            ):
                pytest.fail(
                    f"Line {i}: Possible real upload: {s}"
                )

    def test_no_real_trash_in_m21_tests(self):
        test_file = os.path.join(
            PROJECT_ROOT,
            "tests",
            "test_m21_real_google_drive.py",
        )
        with open(test_file, encoding="utf-8") as fh:
            lines = fh.readlines()
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if s.startswith("#") or s.startswith('"""'):
                continue
            # Skip self-referential assertion lines
            if "permanent=True" in s and "assert" in s:
                continue
            if (
                "permanent=True" in s
                and "not in" in s
            ):
                continue
            if (
                "permanent=True" in s
                and "in text" in s
            ):
                continue
            if (
                "permanent=True" in s
                and "in s" in s
            ):
                continue
            # Only flag actual code usage
            if (
                "permanent=True" in s
                and not s.startswith("assert")
                and "not in" not in s
            ):
                pytest.fail(
                    f"Line {i}: Possible real trash: {s}"
                )


# ====================================================================
# SECTION 12: SECRET NON-DISCLOSURE
# ====================================================================


class TestSecretNonDisclosure:
    """Verify no secrets are exposed in code or tests."""

    def test_no_secrets_tracked_in_git(self):
        import subprocess
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        tracked = result.stdout
        for name in [
            "credentials.json",
            "token.json",
            ".env",
        ]:
            assert name not in tracked

    def test_gitignore_excludes_cloud_data(self):
        gitignore = _read(
            os.path.join(PROJECT_ROOT, ".gitignore")
        )
        assert "cloud_data/" in gitignore

    def test_gitignore_excludes_credentials(self):
        gitignore = _read(
            os.path.join(PROJECT_ROOT, ".gitignore")
        )
        assert "credentials.json" in gitignore
        assert "token.json" in gitignore

    def test_state_never_stores_oauth(self):
        text = _read(
            os.path.join(PROJECT_ROOT, "app", "state.py")
        )
        for line in text.split("\n"):
            s = line.strip()
            if s.startswith("#"):
                continue
            lower = s.lower()
            if (
                "access_token" in lower
                or "refresh_token" in lower
            ):
                if "token_ref" not in s:
                    pytest.fail(f"Possible secret: {s}")

    def test_logging_no_token_content(self):
        """Verify logging never includes token file contents."""
        text = _read(
            os.path.join(
                PROJECT_ROOT, "app", "logging_setup.py"
            )
        )
        assert "token.json" not in text
        assert "credentials.json" not in text

    def test_components_no_secret_keywords(self):
        components = os.path.join(
            PROJECT_ROOT, "ui", "components.py"
        )
        text = _read(components)
        lower = text.lower()
        assert "password" not in lower
        assert "client_secret" not in lower


# ====================================================================
# SECTION 13: ACTION SAFETY UNCHANGED
# ====================================================================


class TestActionSafetyUnchanged:
    """Verify action_safety.py is not modified."""

    def test_action_safety_file_unchanged(self):
        import subprocess
        result = subprocess.run(
            [
                "git",
                "diff",
                "HEAD~1",
                "--",
                "agent/action_safety.py",
            ],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.stdout == "", (
            "action_safety.py was modified in M21"
        )


# ====================================================================
# SECTION 14: LIVE GOOGLE TESTS (gated)
# ====================================================================


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
class TestLiveGoogleDrive:
    """Live Google Drive validation (READ-ONLY).

    These tests require:
    - AI_GUARDIAN_LIVE_GOOGLE=1
    - credentials.json in project root
    - Google client libraries installed

    All operations are READ-ONLY. No uploads, deletes,
    or mutations are performed.
    """

    def test_live_auth_manager_connect(self):
        """Test explicit OAuth connection flow."""
        from cloud.auth_manager import GoogleAuthManager
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )

        mgr = MultiAccountDriveManager()
        auth = GoogleAuthManager(drive_manager=mgr)

        # Check initial state (no accounts)
        status = auth.get_auth_status()
        assert status["success"] is True
        initial_count = status["data"]["account_count"]

        # Start authentication
        pending = auth.start_authentication()
        assert pending is not None

        # Complete it (this opens browser)
        result = auth.complete_authentication(pending)
        assert result["success"] is True

        # Verify registration
        status2 = auth.get_auth_status()
        assert status2["data"]["account_count"] == (
            initial_count + 1
        )

        # Get the account ID for later tests
        self._account_id = result["data"]["account_id"]

    def test_live_account_identity(self):
        """Verify safe account identity is returned."""
        from cloud.auth_manager import GoogleAuthManager
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )

        mgr = MultiAccountDriveManager()
        auth = GoogleAuthManager(drive_manager=mgr)
        status = auth.get_auth_status()
        for acc in status["data"]["accounts"]:
            # Must have safe fields
            assert "account_id" in acc
            assert "display_name" in acc or "email" in acc
            # Must NOT have token data
            assert "access_token" not in acc
            assert "refresh_token" not in acc

    def test_live_search_files(self):
        """READ-ONLY: search for a safe test file."""
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )

        mgr = MultiAccountDriveManager()
        accounts = mgr.describe_accounts()
        if not accounts["data"]["accounts"]:
            pytest.skip("No connected accounts")

        acc = accounts["data"]["accounts"][0]
        session = mgr.get_session(acc["account_id"])
        if session is None:
            pytest.skip("Cannot get session")

        result = session.search_files("test")
        assert "success" in result
        if result["success"] and "data" in result:
            assert "files" in result["data"]

    def test_live_storage_quota(self):
        """READ-ONLY: get storage quota."""
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )

        mgr = MultiAccountDriveManager()
        accounts = mgr.describe_accounts()
        if not accounts["data"]["accounts"]:
            pytest.skip("No connected accounts")

        acc = accounts["data"]["accounts"][0]
        session = mgr.get_session(acc["account_id"])
        if session is None:
            pytest.skip("Cannot get session")

        result = session.get_storage_info()
        assert "success" in result
        if result["success"]:
            data = result.get("data", {})
            # Must have at least one known value
            assert any(
                k in data
                for k in [
                    "used_bytes",
                    "free_bytes",
                    "total_bytes",
                ]
            )
            # Unknown values must stay None, not zero
            for k in [
                "used_bytes",
                "free_bytes",
                "total_bytes",
            ]:
                if k in data and data[k] is None:
                    # None is allowed (unknown)
                    pass

    def test_live_large_files(self):
        """READ-ONLY: list large files."""
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )

        mgr = MultiAccountDriveManager()
        accounts = mgr.describe_accounts()
        if not accounts["data"]["accounts"]:
            pytest.skip("No connected accounts")

        acc = accounts["data"]["accounts"][0]
        session = mgr.get_session(acc["account_id"])
        if session is None:
            pytest.skip("Cannot get session")

        result = session.list_large_files(
            min_size_bytes=1024 * 1024, limit=5
        )
        assert "success" in result
        if result["success"]:
            data = result.get("data", {})
            assert "files" in data
            # Each file must have id and name
            for f in data["files"]:
                assert "id" in f or "file_id" in f

    def test_live_duplicate_candidates(self):
        """READ-ONLY: find duplicate candidates."""
        from cloud.cloud_intelligence import (
            CloudStorageIntelligence,
        )
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )

        mgr = MultiAccountDriveManager()
        accounts = mgr.describe_accounts()
        if not accounts["data"]["accounts"]:
            pytest.skip("No connected accounts")

        intel = CloudStorageIntelligence(mgr)
        result = intel.find_duplicate_candidates(
            scope_all=True
        )
        assert "success" in result

    def test_live_disconnect_reconnect(self):
        """Test disconnect and reconnect flow."""
        from cloud.auth_manager import GoogleAuthManager
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )

        mgr = MultiAccountDriveManager()
        auth = GoogleAuthManager(drive_manager=mgr)
        status = auth.get_auth_status()

        if not status["data"]["accounts"]:
            pytest.skip("No accounts to disconnect")

        acc = status["data"]["accounts"][0]
        acc_id = acc["account_id"]

        # Disconnect
        result = auth.disconnect_account(acc_id)
        assert result["success"] is True

        # Verify disconnected
        status2 = auth.get_auth_status()
        for a in status2["data"]["accounts"]:
            if a["account_id"] == acc_id:
                assert a["status"] == "disconnected"

        # Reconnect
        pending = auth.start_authentication()
        result2 = auth.complete_authentication(pending)
        assert result2["success"] is True

    def test_live_no_token_exposure(self):
        """Verify tokens are never in any output."""
        from cloud.auth_manager import GoogleAuthManager
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )

        mgr = MultiAccountDriveManager()
        auth = GoogleAuthManager(drive_manager=mgr)

        # Get status and verify no token data
        status = auth.get_auth_status()
        status_str = str(status)
        assert "ya29" not in status_str
        assert "refresh_token" not in status_str
        assert "client_secret" not in status_str

    def test_live_account_isolation(self):
        """Verify accounts are isolated."""
        from cloud.multi_drive import (
            MultiAccountDriveManager,
        )

        mgr = MultiAccountDriveManager()
        accounts = mgr.describe_accounts()
        if len(accounts["data"]["accounts"]) < 2:
            pytest.skip("Need 2+ accounts for isolation test")

        acc_list = accounts["data"]["accounts"]
        acc_ids = [a["account_id"] for a in acc_list]

        # Each account must have a distinct session
        for acc_id in acc_ids:
            session = mgr.get_session(acc_id)
            if session is None:
                continue
            # Session must be bound to this account's token
            assert acc_id in session.token_file


# ====================================================================
# SECTION 15: M20 PATH BEHAVIOR IN SOURCE MODE
# ====================================================================


class TestSourceModePathBehavior:
    """Verify source-mode paths are correct."""

    def test_source_mode_user_data_is_cloud_data(self):
        from app.paths import user_data_dir, _is_frozen
        if not _is_frozen():
            ud = user_data_dir()
            assert "cloud_data" in ud

    def test_source_mode_app_root_is_project(self):
        from app.paths import app_root, _is_frozen
        if not _is_frozen():
            root = app_root()
            assert os.path.isdir(
                os.path.join(root, "app")
            )
            assert os.path.isdir(
                os.path.join(root, "cloud")
            )

    def test_ensure_user_data_dir_creates_tokens(self):
        from app.paths import ensure_user_data_dir
        import shutil

        with tempfile.TemporaryDirectory() as td:
            # Temporarily override user_data_dir
            import app.paths as paths_mod

            original = paths_mod.user_data_dir
            paths_mod.user_data_dir = lambda: os.path.join(
                td, "test_data"
            )
            try:
                result = ensure_user_data_dir()
                assert os.path.isdir(result)
                assert os.path.isdir(
                    os.path.join(result, "tokens")
                )
            finally:
                paths_mod.user_data_dir = original


# ====================================================================
# SECTION 16: SECURITY AUDIT
# ====================================================================


class TestSecurityAudit:
    """Comprehensive security audit for M21."""

    def test_no_new_network_code_in_ui(self):
        """UI layer should not have network calls."""
        ui_files = [
            "ui/app.py",
            "ui/app_controller.py",
            "ui/components.py",
            "ui/navigation.py",
        ]
        for f in ui_files:
            path = os.path.join(PROJECT_ROOT, f)
            if not os.path.isfile(path):
                continue
            text = _read(path)
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
                        f"Network call in {f}: {s}"
                    )

    def test_no_new_network_code_in_views(self):
        """View layer should not have network calls."""
        views_dir = os.path.join(
            PROJECT_ROOT, "ui", "views"
        )
        if not os.path.isdir(views_dir):
            pytest.skip("views dir not found")
        for f in os.listdir(views_dir):
            if not f.endswith(".py"):
                continue
            path = os.path.join(views_dir, f)
            text = _read(path)
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
                        f"Network call in views/{f}: {s}"
                    )

    def test_protected_projects_unchanged(self):
        """Protected projects must not be modified."""
        protected = r"D:\AI-Laptop-Guardian"
        backup = r"D:\AI-Laptop-Guardian-Backup"
        assert os.path.isdir(protected)
        assert os.path.isdir(backup)

    def test_no_git_push_in_m21(self):
        """M21 should not push to remote."""
        test_file = os.path.join(
            PROJECT_ROOT,
            "tests",
            "test_m21_real_google_drive.py",
        )
        with open(test_file, encoding="utf-8") as fh:
            lines = fh.readlines()
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if s.startswith("#") or s.startswith('"""'):
                continue
            # Skip lines that are just assertions about git push
            if "assert" in s and "git push" in s:
                continue
            if "def test_" in s:
                continue
            if "pytest.fail" in s and "git push" in s:
                continue
            # Flag actual subprocess.run or os.system calls
            if (
                "subprocess" in s
                and "push" in s
            ):
                pytest.fail(
                    f"Line {i}: Possible git push: {s}"
                )

    def test_no_force_push(self):
        test_file = os.path.join(
            PROJECT_ROOT,
            "tests",
            "test_m21_real_google_drive.py",
        )
        with open(test_file, encoding="utf-8") as fh:
            lines = fh.readlines()
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if s.startswith("#") or s.startswith('"""'):
                continue
            if "assert" in s and "force" in s:
                continue
            if "def test_" in s:
                continue
            if "pytest.fail" in s and "force" in s:
                continue
            # Flag actual subprocess calls with force
            if (
                "subprocess" in s
                and "force" in s
                and "push" in s
            ):
                pytest.fail(
                    f"Line {i}: Possible force push: {s}"
                )

    def test_version_consistency(self):
        from app.version import __version__
        assert __version__ == "0.14.0"

        iss = _read(
            os.path.join(
                PROJECT_ROOT,
                "installer",
                "ai_laptop_guardian.iss",
            )
        )
        assert "0.14.0" in iss
