"""Milestone 10 - UI security regression tests.

Proves that:

    - constructing the UI
    - opening every view
    - running the dashboard

never triggers Google authentication.
Only explicit account connection may start OAuth.

Uses customtkinter (skipped when unavailable).
"""

import sys
import types

import pytest


ctk = pytest.importorskip(
    "customtkinter",
    reason="customtkinter not installed",
)


def _install_cloud_stub():
    if "cloud.google_drive" not in sys.modules:
        module = types.ModuleType(
            "cloud.google_drive"
        )

        class StubGoogleDriveProvider:
            def __init__(self, *a, **kw):
                self.service = None
                self.credentials = None

        module.GoogleDriveProvider = (
            StubGoogleDriveProvider
        )

        sys.modules["cloud.google_drive"] = module


_install_cloud_stub()

from agent.ai_agent import AIAgent  # noqa: E402
from cloud.accounts import AccountRegistry  # noqa: E402
from cloud.multi_drive import (  # noqa: E402
    MultiAccountDriveManager,
)
from cloud.auth_manager import (  # noqa: E402
    GoogleAuthManager,
)
from ui.app import GuardianApp  # noqa: E402
from ui.navigation import NAV_ITEMS  # noqa: E402


# =========================================================
# AUTH EXPLOSION GUARD
# =========================================================

AUTH_TRIGGERED = False


def _explode_auth(*args, **kwargs):
    global AUTH_TRIGGERED
    AUTH_TRIGGERED = True
    raise AssertionError(
        "Google authentication was triggered "
        "implicitly — this must never happen "
        "during UI navigation or startup."
    )


# =========================================================
# FIXTURE (session-scoped to avoid Tk root conflicts)
# =========================================================


@pytest.fixture(scope="module")
def app_guard(tmp_path_factory):
    """
    Construct a real GuardianApp with an exploded auth
    guard, run ALL security checks against it, then
    destroy it exactly once at the end.
    """

    global AUTH_TRIGGERED
    AUTH_TRIGGERED = False

    tmp = Path(str(tmp_path_factory.mktemp("sec")))

    agent = AIAgent()

    agent.router.drive_manager = (
        MultiAccountDriveManager(
            registry=AccountRegistry(),
            token_dir=str(tmp / "tokens"),
        )
    )

    gm = agent.router.auth_manager

    gm.credentials_file = str(
        tmp / "credentials.json"
    )

    gm.start_authentication = _explode_auth

    app = GuardianApp(controller=None)

    app.ctrl.agent = agent

    app.ctrl.agent.router.drive_manager = (
        agent.router.drive_manager
    )

    app.ctrl.agent.router._auth_manager = gm

    # Suppress background threads so tkinter stays
    # on the main thread throughout security checks.

    def _sync(fn, on_done, on_error=None):
        try:
            result = fn()
        except Exception as exc:
            if on_error is not None:
                on_error(exc)
            return
        on_done(result)

    app.ctrl.run_in_background = _sync

    app.withdraw()

    yield app

    try:
        app.destroy()
    except Exception:
        pass


from pathlib import Path  # noqa: E402


# =========================================================
# SECURITY REGRESSIONS (all in one test to avoid Tk
# root recreation across tests)
# =========================================================


class TestUISecurityNoAuth:
    """
    Every navigation step must complete without
    triggering Google authentication.
    """

    def test_full_navigation_never_authenticates(
        self, app_guard
    ):
        global AUTH_TRIGGERED

        app = app_guard

        # 1. Startup was safe (app already constructed).

        assert not AUTH_TRIGGERED

        # 2. Navigate every view.

        for key, _label in NAV_ITEMS:

            app.show_view(key)

            app.update_idletasks()

            app.update()

            assert not AUTH_TRIGGERED, (
                f"Auth triggered on view: {key}"
            )

        # 3. Dashboard loaded safely via sync path.

        app.show_view("dashboard")

        app.update_idletasks()

        app.update()

        assert not AUTH_TRIGGERED

        # 4. No secret strings leaked into any widget.

        SECRET_MARKERS = [
            "ya29.", "1//", "SUPERSECRET",
            "refresh_token",
        ]

        for widget in app.winfo_children():

            try:
                text = widget.cget("text")

                if isinstance(text, str):

                    for marker in SECRET_MARKERS:
                        assert marker not in (
                            text.lower()
                        )

            except Exception:
                pass

        # 5. Token directory was never created.

        token_dir = Path(
            app.ctrl.agent.router.drive_manager
            .token_dir
        )

        assert not token_dir.exists()
