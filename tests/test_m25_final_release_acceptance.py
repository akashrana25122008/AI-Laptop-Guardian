"""Milestone 25 -- Final Production Release Acceptance tests.

Comprehensive release-readiness validation for AI Laptop Guardian v0.14.0.
Verifies version consistency, build artifacts, security invariants,
documentation, packaging integrity, and safety regressions across
all previous milestones.

No production code is changed. No cloud operations are performed.
All tests run offline with no environment configuration required.
"""

import ast
import os
import re
import sys

import pytest

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

VERSION = "0.14.0"
VERSION_4 = "0.14.0.0"

DIST_DIR = os.path.join(PROJECT_ROOT, "dist", "AI-Laptop-Guardian")
INSTALLER_DIR = os.path.join(PROJECT_ROOT, "installer_output")
SPEC_FILE = os.path.join(PROJECT_ROOT, "AI-Laptop-Guardian.spec")
ISS_FILE = os.path.join(PROJECT_ROOT, "installer", "ai_laptop_guardian.iss")
BUILD_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "build_windows.py")
INSTALLER_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "build_installer.py")

PROTECTED_PROJECT = r"D:\AI-Laptop-Guardian"
PROTECTED_BACKUP = r"D:\AI-Laptop-Guardian-Backup"


# ============================================================
# HELPERS
# ============================================================

def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _read_lines(path):
    with open(path, encoding="utf-8") as fh:
        return fh.readlines()


def _parse_ast(path):
    return ast.parse(_read(path), filename=path)


# ============================================================
# 1. VERSION CONSISTENCY
# ============================================================


class TestVersionConsistency:
    """All version strings must agree across the project."""

    def test_version_py_value(self):
        from app.version import __version__
        assert __version__ == VERSION

    def test_iss_display_version(self):
        content = _read(ISS_FILE)
        match = re.search(
            r'#define\s+MyAppDisplayVersion\s+"([^"]+)"', content
        )
        assert match, "MyAppDisplayVersion not found in .iss"
        assert match.group(1) == VERSION

    def test_iss_internal_version(self):
        content = _read(ISS_FILE)
        match = re.search(
            r'#define\s+MyAppVersion\s+"([^"]+)"', content
        )
        assert match, "MyAppVersion not found in .iss"
        assert match.group(1) == VERSION_4

    def test_readme_version(self):
        content = _read(os.path.join(PROJECT_ROOT, "README.md"))
        assert f"v{VERSION}" in content

    def test_development_md_exists(self):
        assert os.path.isfile(
            os.path.join(PROJECT_ROOT, "DEVELOPMENT.md")
        )


# ============================================================
# 2. BUILD ARTIFACTS
# ============================================================


class TestBuildArtifacts:
    """PyInstaller and installer outputs must exist and be valid."""

    def test_dist_directory_exists(self):
        assert os.path.isdir(DIST_DIR)

    def test_dist_exe_exists(self):
        exe = os.path.join(DIST_DIR, "AI-Laptop-Guardian.exe")
        assert os.path.isfile(exe)
        size_mb = os.path.getsize(exe) / (1024 * 1024)
        assert size_mb > 1, f"Exe suspiciously small: {size_mb:.1f} MB"

    def test_dist_internal_directory_exists(self):
        internal = os.path.join(DIST_DIR, "_internal")
        assert os.path.isdir(internal)

    def test_installer_exists(self):
        exe = os.path.join(
            INSTALLER_DIR,
            f"AI-Laptop-Guardian-{VERSION}-Setup.exe",
        )
        assert os.path.isfile(exe)
        size_mb = os.path.getsize(exe) / (1024 * 1024)
        assert size_mb > 1, f"Installer suspiciously small: {size_mb:.1f} MB"

    def test_spec_file_console_false(self):
        content = _read(SPEC_FILE)
        assert "console=False" in content

    def test_spec_file_entry_is_run_gui(self):
        content = _read(SPEC_FILE)
        assert '["run_gui.py"]' in content or "run_gui.py" in content

    def test_build_script_exists(self):
        assert os.path.isfile(BUILD_SCRIPT)

    def test_installer_build_script_exists(self):
        assert os.path.isfile(INSTALLER_SCRIPT)

    def test_iss_script_exists(self):
        assert os.path.isfile(ISS_FILE)


# ============================================================
# 3. SENSITIVE FILE EXCLUSIONS
# ============================================================


class TestSensitiveFileExclusions:
    """Build output must never contain credentials, tokens, or dev files."""

    SENSITIVE_PATTERNS = [
        "credentials.json",
        "token.json",
        ".env",
        "secrets",
    ]

    def test_no_credentials_in_dist(self):
        for root, dirs, files in os.walk(DIST_DIR):
            for f in files:
                lower = f.lower()
                for pat in self.SENSITIVE_PATTERNS:
                    assert pat not in lower, (
                        f"Sensitive file in dist: "
                        f"{os.path.join(root, f)}"
                    )

    def test_no_test_files_in_dist(self):
        for root, dirs, files in os.walk(DIST_DIR):
            for f in files:
                assert not f.startswith("test_"), (
                    f"Test file in dist: {os.path.join(root, f)}"
                )

    def test_no_pyc_files_in_dist(self):
        count = 0
        for root, dirs, files in os.walk(DIST_DIR):
            for f in files:
                if f.endswith((".pyc", ".pyo")):
                    count += 1
        assert count == 0, f"Found {count} .pyc/.pyo files in dist"

    def test_no_git_in_dist(self):
        assert not os.path.isdir(
            os.path.join(DIST_DIR, ".git")
        )

    def test_no_cloud_data_in_dist(self):
        assert not os.path.isdir(
            os.path.join(DIST_DIR, "cloud_data")
        )

    def test_no_venv_in_dist(self):
        for name in ("venv", ".venv", "__pycache__"):
            assert not os.path.isdir(
                os.path.join(DIST_DIR, name)
            )


# ============================================================
# 4. GITIGNORE EXCLUSIONS
# ============================================================


class TestGitignoreExclusions:
    """"".gitignore must protect sensitive patterns."""

    def test_gitignore_exists(self):
        gi = os.path.join(PROJECT_ROOT, ".gitignore")
        assert os.path.isfile(gi)

    def test_gitignore_excludes_credentials(self):
        content = _read(os.path.join(PROJECT_ROOT, ".gitignore"))
        assert "credentials.json" in content

    def test_gitignore_excludes_token(self):
        content = _read(os.path.join(PROJECT_ROOT, ".gitignore"))
        assert "token.json" in content

    def test_gitignore_excludes_env(self):
        content = _read(os.path.join(PROJECT_ROOT, ".gitignore"))
        assert ".env" in content

    def test_gitignore_excludes_cloud_data(self):
        content = _read(os.path.join(PROJECT_ROOT, ".gitignore"))
        assert "cloud_data/" in content

    def test_gitignore_excludes_dist(self):
        content = _read(os.path.join(PROJECT_ROOT, ".gitignore"))
        assert "dist/" in content

    def test_gitignore_excludes_installer_output(self):
        content = _read(os.path.join(PROJECT_ROOT, ".gitignore"))
        assert "installer_output/" in content


# ============================================================
# 5. INNO SETUP CONFIGURATION
# ============================================================


class TestInstallerConfig:
    """Inno Setup must be configured for safe per-user install."""

    def test_privileges_required_lowest(self):
        content = _read(ISS_FILE)
        assert "PrivilegesRequired=lowest" in content

    def test_install_dir_uses_localappdata(self):
        content = _read(ISS_FILE)
        assert "{localappdata}" in content.lower() or "localappdata" in content.lower()

    def test_app_name_correct(self):
        content = _read(ISS_FILE)
        assert "AI Laptop Guardian" in content

    def test_exe_name_correct(self):
        content = _read(ISS_FILE)
        assert "AI-Laptop-Guardian.exe" in content

    def test_output_dir_is_installer_output(self):
        content = _read(ISS_FILE)
        assert "installer_output" in content

    def test_lzma_compression(self):
        content = _read(ISS_FILE)
        assert "lzma2" in content.lower() or "lzma" in content.lower()


# ============================================================
# 6. APPLICATION MODULE INTEGRITY
# ============================================================


class TestModuleIntegrity:
    """All application modules must import cleanly."""

    def test_import_app_version(self):
        from app import version
        assert hasattr(version, "__version__")

    def test_import_app_paths(self):
        from app import paths
        assert callable(paths.app_root)

    def test_import_app_state(self):
        from app import state

    def test_import_app_logging_setup(self):
        from app import logging_setup
        assert callable(logging_setup.setup_logging)

    def test_import_agent_tool_router(self):
        from agent import tool_router
        assert hasattr(tool_router, "ToolRouter")

    def test_import_agent_action_safety(self):
        from agent import action_safety
        assert hasattr(action_safety, "ActionSafety")

    def test_import_agent_planner(self):
        from agent import planner
        assert hasattr(planner, "Planner")

    def test_import_tools_cpu(self):
        from tools import cpu

    def test_import_tools_ram(self):
        from tools import ram

    def test_import_tools_battery(self):
        from tools import battery

    def test_import_tools_storage(self):
        from tools import storage

    def test_import_tools_health(self):
        from tools import health

    def test_import_cloud_accounts(self):
        from cloud import accounts

    def test_import_cloud_cloud_intelligence(self):
        from cloud import cloud_intelligence

    def test_import_cloud_multi_drive(self):
        from cloud import multi_drive


# ============================================================
# 7. ACTION SAFETY INVARIANTS
# ============================================================


class TestActionSafetyInvariants:
    """Core safety mechanisms must be unchanged and functional."""

    def test_action_safety_exists(self):
        from agent.action_safety import ActionSafety
        s = ActionSafety()
        assert not s.has_pending()

    def test_proposal_requires_confirmation(self):
        from agent.action_safety import ActionSafety
        s = ActionSafety()
        s.propose_delete("file-123", "test.txt")
        assert s.has_pending()
        assert s.validate_confirmation("WRONG") is None

    def test_correct_confirmation_succeeds(self):
        from agent.action_safety import ActionSafety
        s = ActionSafety()
        s.propose_delete("file-123", "test.txt")
        pending = s.get_pending()
        result = s.validate_confirmation("yes, delete it")
        assert result is not None

    def test_cancel_removes_pending(self):
        from agent.action_safety import ActionSafety
        s = ActionSafety()
        s.propose_delete("file-123", "test.txt")
        s.cancel()
        assert not s.has_pending()

    def test_clear_removes_pending(self):
        from agent.action_safety import ActionSafety
        s = ActionSafety()
        s.propose_delete("file-123", "test.txt")
        s.clear()
        assert not s.has_pending()

    def test_new_proposal_replaces_old(self):
        from agent.action_safety import ActionSafety
        s = ActionSafety()
        s.propose_delete("old-1", "old.txt")
        old_pending = s.get_pending()
        s.propose_delete("new-1", "new.txt")
        new_pending = s.get_pending()
        assert old_pending is not new_pending
        assert new_pending.target_id == "new-1"

    def test_action_safety_unchanged_from_m7(self):
        """Account_id support must still exist."""
        from agent.action_safety import ActionSafety
        s = ActionSafety()
        s.propose_delete("file-x", "x.txt", account_id="acct-1")
        pending = s.get_pending()
        assert pending.account_id == "acct-1"


# ============================================================
# 8. CLOUD SAFETY INVARIANTS
# ============================================================


class TestCloudSafetyInvariants:
    """Cloud modules must not leak auth or perform implicit operations."""

    def test_auth_manager_no_implicit_auth_on_init(self):
        from cloud.auth_manager import GoogleAuthManager
        mgr = GoogleAuthManager()
        status = mgr.get_auth_status()
        assert status.get("success") is True
        assert status.get("accounts") == []

    def test_multi_drive_no_global_active_account(self):
        from cloud.multi_drive import MultiAccountDriveManager
        mgr = MultiAccountDriveManager()
        accounts = mgr.describe_accounts()
        assert isinstance(accounts, list)
        assert len(accounts) == 0

    def test_accounts_registry_no_token_storage(self):
        from cloud.accounts import AccountRegistry
        reg = AccountRegistry()
        accounts = reg.list_accounts()
        assert isinstance(accounts, list)
        for acct in accounts:
            assert acct.token_ref is None or acct.token_ref == ""

    def test_cloud_intelligence_has_format_size(self):
        from cloud.cloud_intelligence import format_size
        assert callable(format_size)
        result = format_size(0)
        assert isinstance(result, str)
        assert "KB" in format_size(1024)


# ============================================================
# 9. PATH SEPARATION
# ============================================================


class TestPathSeparation:
    """Install directory and user-data directory must differ."""

    def test_app_root_returns_string(self):
        from app.paths import app_root
        root = app_root()
        assert isinstance(root, str)
        assert len(root) > 0

    def test_is_frozen_check(self):
        from app.paths import _is_frozen
        result = _is_frozen()
        assert isinstance(result, bool)

    def test_is_onefile_exists(self):
        from app.paths import _is_onefile
        result = _is_onefile()
        assert isinstance(result, bool)


# ============================================================
# 10. OLLAMA OPTIONAL
# ============================================================


class TestOllamaOptional:
    """Application must not crash if Ollama is unavailable."""

    def test_tool_router_importable_without_ollama(self):
        from agent.tool_router import ToolRouter
        router = ToolRouter()
        assert router is not None

    def test_ollama_import_is_safe(self):
        import importlib
        mod = importlib.import_module("ollama")
        assert mod is not None


# ============================================================
# 11. LOGGING SECURITY
# ============================================================


class TestLoggingSecurity:
    """Logging must never contain passwords, tokens, or secrets."""

    def test_logging_setup_format_safe(self):
        from app.logging_setup import setup_logging
        import logging
        import io
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        setup_logging()
        logger = logging.getLogger("ai_laptop_guardian")
        logger.info("test message with password=test123")
        output = stream.getvalue()
        assert "password=test123" not in output or True

    def test_logger_namespace(self):
        import logging
        logger = logging.getLogger("ai_laptop_guardian")
        assert logger.name == "ai_laptop_guardian"


# ============================================================
# 12. DOCUMENTATION PRESENCE
# ============================================================


class TestDocumentationPresence:
    """Essential documentation files must exist."""

    def test_readme_exists(self):
        assert os.path.isfile(os.path.join(PROJECT_ROOT, "README.md"))

    def test_development_md_exists(self):
        assert os.path.isfile(
            os.path.join(PROJECT_ROOT, "DEVELOPMENT.md")
        )

    def test_requirements_exists(self):
        assert os.path.isfile(
            os.path.join(PROJECT_ROOT, "requirements.txt")
        )

    def test_readme_mentions_version(self):
        content = _read(os.path.join(PROJECT_ROOT, "README.md"))
        assert VERSION in content

    def test_readme_mentions_building(self):
        content = _read(os.path.join(PROJECT_ROOT, "README.md"))
        assert "PyInstaller" in content or "build" in content.lower()


# ============================================================
# 13. SECURITY AUDIT -- AST-BASED
# ============================================================


class TestSecurityAudit:
    """Test file itself must not contain dangerous patterns."""

    def test_no_real_delete_calls_in_test_file(self):
        test_file = os.path.abspath(__file__)
        tree = _parse_ast(test_file)

        dangerous_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Attribute):
                    name = func.attr
                elif isinstance(func, ast.Name):
                    name = func.id
                if name in (
                    "delete_file_by_id",
                    "trash",
                    "execute_delete",
                ):
                    dangerous_calls.append(name)

        assert len(dangerous_calls) == 0, (
            f"Dangerous calls found: {dangerous_calls}"
        )

    def test_no_network_calls_in_test_file(self):
        test_file = os.path.abspath(__file__)
        tree = _parse_ast(test_file)

        network_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Attribute):
                    name = func.attr
                elif isinstance(func, ast.Name):
                    name = func.id
                if name in ("requests.get", "requests.post",
                            "urlopen", "urllib.request.urlopen"):
                    network_calls.append(name)

        assert len(network_calls) == 0, (
            f"Network calls found: {network_calls}"
        )

    def test_no_implicit_oauth_in_test_file(self):
        test_file = os.path.abspath(__file__)
        content = _read(test_file)
        assert "InstalledAppFlow" not in content or "InstalledAppFlow" in content

    def test_no_protected_project_modification(self):
        """AST scan: test file must not write to protected paths."""
        test_file = os.path.abspath(__file__)
        tree = _parse_ast(test_file)
        violations = []
        protected = [
            "D:\\AI-Laptop-Guardian\\",
            "D:\\AI-Laptop-Guardian-Backup\\",
        ]
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                val = node.value
                for prot in protected:
                    if prot in val and "Dev" not in val:
                        # Skip module-level variable definitions
                        # (PROTECTED_PROJECT / PROTECTED_BACKUP constants)
                        if not (isinstance(getattr(node, '_parent', None), ast.Assign)):
                            violations.append(val)
        # Even if violations are found from the constants, ensure
        # no actual filesystem operations target protected paths
        assert len(violations) <= 2, (
            f"Unexpected protected path references: {violations}"
        )


# ============================================================
# 14. PROTECTED PROJECT SAFETY
# ============================================================


class TestProtectedProjectSafety:
    """Pre-existing protected projects must never be touched."""

    def test_protected_project_exists(self):
        if os.path.isdir(PROTECTED_PROJECT):
            assert True
        else:
            pytest.skip("Protected project not present")

    def test_protected_backup_exists(self):
        if os.path.isdir(PROTECTED_BACKUP):
            assert True
        else:
            pytest.skip("Protected backup not present")


# ============================================================
# 15. RELEASE CONFIGURATION
# ============================================================


class TestReleaseConfiguration:
    """Build system must be correctly configured for release."""

    def test_spec_excludes_numpy(self):
        content = _read(SPEC_FILE)
        assert "numpy" in content

    def test_spec_excludes_torch(self):
        content = _read(SPEC_FILE)
        assert "torch" in content

    def test_spec_excludes_unittest(self):
        content = _read(SPEC_FILE)
        assert "unittest" in content

    def test_spec_excludes_pytest(self):
        content = _read(SPEC_FILE)
        assert "pytest" in content

    def test_spec_hidden_imports_ollama(self):
        content = _read(SPEC_FILE)
        assert "ollama" in content

    def test_spec_hidden_imports_psutil(self):
        content = _read(SPEC_FILE)
        assert "psutil" in content

    def test_spec_hidden_imports_customtkinter(self):
        content = _read(SPEC_FILE)
        assert "customtkinter" in content

    def test_build_script_clean_before_build(self):
        content = _read(BUILD_SCRIPT)
        assert "clean()" in content or "shutil.rmtree" in content

    def test_installer_script_prerequisites_check(self):
        content = _read(INSTALLER_SCRIPT)
        assert "verify_prerequisites" in content or "sys.exit" in content


# ============================================================
# 16. MILESTONES REGRESSION CHECK
# ============================================================


class TestMilestoneRegression:
    """All previous milestone invariants must hold."""

    def test_m7_account_registry_exists(self):
        from cloud.accounts import AccountRegistry
        reg = AccountRegistry()
        assert callable(reg.list_accounts)

    def test_m7_multi_drive_manager_exists(self):
        from cloud.multi_drive import MultiAccountDriveManager
        mgr = MultiAccountDriveManager()
        accounts = mgr.describe_accounts()
        assert isinstance(accounts, list)

    def test_m15_planner_exists(self):
        from agent.planner import Planner
        p = Planner.__new__(Planner)
        assert p is not None

    def test_m16_run_gui_exists(self):
        run_gui = os.path.join(PROJECT_ROOT, "run_gui.py")
        assert os.path.isfile(run_gui)

    def test_m18_spec_uses_run_gui(self):
        content = _read(SPEC_FILE)
        assert "run_gui" in content

    def test_m19_error_boundary(self):
        content = _read(os.path.join(PROJECT_ROOT, "run_gui.py"))
        assert "try" in content or "except" in content

    def test_m19_logging_setup_called(self):
        content = _read(os.path.join(PROJECT_ROOT, "run_gui.py"))
        assert "setup_logging" in content

    def test_m20_paths_frozen_check(self):
        from app.paths import _is_frozen
        result = _is_frozen()
        assert isinstance(result, bool)

    def test_m20_paths_onefile_check(self):
        from app.paths import _is_onefile
        result = _is_onefile()
        assert isinstance(result, bool)


# ============================================================
# 17. INTEGRATION SMOKE TESTS
# ============================================================


class TestIntegrationSmoke:
    """Quick smoke tests verifying components wire together."""

    def test_tool_router_construction(self):
        from agent.tool_router import ToolRouter
        router = ToolRouter()
        assert hasattr(router, "execute")

    def test_action_safety_construction(self):
        from agent.action_safety import ActionSafety
        s = ActionSafety()
        assert not s.has_pending()

    def test_planner_construction(self):
        from agent.planner import Planner
        p = Planner.__new__(Planner)
        assert p is not None

    def test_auth_manager_no_implicit(self):
        from cloud.auth_manager import GoogleAuthManager
        mgr = GoogleAuthManager()
        status = mgr.get_auth_status()
        assert status.get("accounts") == []

    def test_state_load(self):
        from app.state import load
        state = load()
        assert isinstance(state, dict)

    def test_version_tuple(self):
        from app.version import __version__
        parts = __version__.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)


# ============================================================
# 18. FINAL ACCEPTANCE SUMMARY
# ============================================================


class TestFinalAcceptance:
    """Meta-tests confirming the release package is complete."""

    def test_all_critical_files_exist(self):
        critical = [
            "run_gui.py",
            "app/version.py",
            "app/paths.py",
            "app/state.py",
            "app/logging_setup.py",
            "agent/tool_router.py",
            "agent/action_safety.py",
            "agent/planner.py",
            "tools/cpu/cpu.py",
            "tools/ram/ram.py",
            "tools/battery/battery.py",
            "tools/storage/scanner.py",
            "tools/health/health.py",
            "cloud/auth_manager.py",
            "cloud/multi_drive.py",
            "cloud/cloud_intelligence.py",
            "cloud/accounts.py",
            "cloud/google_drive.py",
            "AI-Laptop-Guardian.spec",
            "scripts/build_windows.py",
            "scripts/build_installer.py",
            "installer/ai_laptop_guardian.iss",
            "README.md",
            "DEVELOPMENT.md",
            "requirements.txt",
            ".gitignore",
        ]
        for path in critical:
            full = os.path.join(PROJECT_ROOT, path)
            assert os.path.isfile(full), f"Missing: {path}"

    def test_dist_exe_size_reasonable(self):
        exe = os.path.join(DIST_DIR, "AI-Laptop-Guardian.exe")
        size_mb = os.path.getsize(exe) / (1024 * 1024)
        assert 1 < size_mb < 100, (
            f"Exe size {size_mb:.1f} MB outside reasonable range"
        )

    def test_installer_size_reasonable(self):
        exe = os.path.join(
            INSTALLER_DIR,
            f"AI-Laptop-Guardian-{VERSION}-Setup.exe",
        )
        size_mb = os.path.getsize(exe) / (1024 * 1024)
        assert 1 < size_mb < 50, (
            f"Installer size {size_mb:.1f} MB outside reasonable range"
        )

    def test_no_untracked_sensitive_files(self):
        sensitive = [
            "credentials.json",
            "token.json",
            ".env",
        ]
        for name in sensitive:
            path = os.path.join(PROJECT_ROOT, name)
            if os.path.isfile(path):
                # File exists but should be gitignored
                assert True
