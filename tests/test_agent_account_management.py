"""Milestone 9 - AIAgent chat flows for account management.

End-to-end over fake OAuth handshakes:

    - listing accounts is offline and deterministic,
    - connecting runs ONLY on an explicit request and
      registers exactly one isolated account,
    - disconnecting ALWAYS waits for a separate explicit
      confirmation and then removes exactly one account's
      local authorization,
    - pending state is single-use; ambiguous replies
      cancel and can never execute later,
    - no AI prompt, reply, or payload ever contains a
      secret, and ordinary local questions never touch
      authentication.
"""

import os
import sys
import types
def _install_cloud_stub() -> None:
    module = types.ModuleType("cloud.google_drive")

    class StubGoogleDriveProvider:
        def __init__(self, *args, **kwargs):
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


SECRET_MARKERS = [
    "SUPERSECRET-CLIENT",
    "ya29.SECRET-ACCESS",
]


class FakeAI:
    def __init__(self):
        self.prompts = []

    def ask(self, prompt):
        self.prompts.append(str(prompt))
        return "FAKE AI RESPONSE"


class FakeAuthProvider:
    """
    Stand-in for GoogleDriveProvider during the OAuth
    handshake. Records every authenticate() call so tests
    can prove authentication never happens implicitly.
    """

    authenticate_calls = 0

    def __init__(
        self,
        identity=None,
        auth_result=True,
        token_path=None,
    ):
        self.identity = identity or {
            "success": True,
            "email": "new@x.com",
            "display_name": "New User",
        }

        self.auth_result = auth_result

        self.token_path = token_path

    def authenticate(self):
        FakeAuthProvider.authenticate_calls += 1

        # Mirror reality: successful consent persists the
        # token into the provider's bound file.

        if (
            self.auth_result
            and self.token_path is not None
        ):

            with open(
                self.token_path,
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write(SECRET_MARKERS[1])

        return self.auth_result

    def get_account_identity(self):
        return dict(self.identity)


def _forbidden_session_factory(account):
    raise AssertionError(
        "provider session was built during an "
        "account-management flow"
    )


def make_agent(tmp_path, emails=()):
    """
    Agent whose drive manager is fully isolated:

        - temp token dir,
        - sessions must stay LAZY (forbidden factory),
        - auth manager points at a temp credentials file.

    Returns (agent, drive).
    """

    agent = AIAgent()

    agent.ai = FakeAI()

    token_dir = tmp_path / "tokens"

    drive = MultiAccountDriveManager(
        registry=AccountRegistry(),
        token_dir=str(token_dir),
        provider_factory=_forbidden_session_factory,
    )

    agent.router.drive_manager = drive

    # Reset the shared handshake counter for isolation.

    FakeAuthProvider.authenticate_calls = 0

    creds = tmp_path / "credentials.json"

    creds.write_text(
        SECRET_MARKERS[0],
        encoding="utf-8",
    )

    # Materialize the router's auth manager against the
    # CURRENT fake manager, then point it at test fakes.

    auth_manager = agent.router.auth_manager

    assert (
        auth_manager.drive_manager is drive
    )  # binding sanity

    auth_manager.credentials_file = str(creds)

    # The venv has no Google client libraries; every
    # connect flow here must use this fake handshake.

    def pending_factory(token_path):
        return FakeAuthProvider(
            token_path=token_path
        )

    auth_manager._pending_factory = pending_factory

    return agent, drive


def write_token(drive, account_id, content="{}"):
    path = os.path.join(
        str(drive.token_dir),
        f"{account_id}.json",
    )

    os.makedirs(
        os.path.dirname(path),
        exist_ok=True,
    )

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)

    return path


def connect_two_accounts(drive):
    first = drive.connect_account(
        provider="google_drive",
        email="a@x.com",
    )

    second = drive.connect_account(
        provider="google_drive",
        email="b@x.com",
    )

    write_token(drive, first.id)

    write_token(drive, second.id)

    return first, second


def regular_tokens(drive):

    return sorted(
        name
        for name in os.listdir(str(drive.token_dir))
        if name.endswith(".json")
        and not name.startswith(".pending-")
    )


# =========================================================
# LISTING ACCOUNTS (OFFLINE)
# =========================================================


class TestListAccountsFlow:

    def test_listing_is_deterministic_and_offline(
        self, tmp_path
    ):
        agent, drive = make_agent(tmp_path)

        connect_two_accounts(drive)

        response = agent.chat(
            "Show my connected Google accounts"
        )

        assert "a@x.com" in response
        assert "b@x.com" in response

        assert "connected" in response.lower()

        assert agent.ai.prompts == []

        assert (
            FakeAuthProvider.authenticate_calls == 0
        )

    def test_empty_listing_invites_explicit_connect(
        self, tmp_path
    ):
        agent, _ = make_agent(tmp_path)

        response = agent.chat(
            "Show my connected Google accounts"
        )

        assert "No Google accounts" in response

        assert "Connect my Google account" in response

        assert agent.ai.prompts == []


# =========================================================
# CONNECTING (EXPLICIT OAUTH)
# =========================================================


class TestConnectFlow:

    def test_explicit_connect_registers_account(
        self, tmp_path
    ):
        agent, drive = make_agent(tmp_path)

        response = agent.chat(
            "Connect my Google account"
        )

        assert "new@x.com" in response

        assert "Connected" in response

        assert drive.registry.count() == 1

        entries = drive.registry.list_accounts()

        account_id = entries[0].id

        # Isolated token file exists; nothing pending.

        assert regular_tokens(drive) == [
            f"{account_id}.json"
        ]

        assert agent.ai.prompts == []

        # The reply carries safe metadata only.

        for marker in SECRET_MARKERS:
            assert marker not in response

    def test_connect_without_credentials_gives_hint(
        self, tmp_path
    ):
        agent, drive = make_agent(tmp_path)

        os.remove(
            str(
                tmp_path / "credentials.json"
            )
        )

        response = agent.chat(
            "Connect my Google account"
        )

        assert "credentials.json" in response

        assert drive.registry.count() == 0

        assert (
            FakeAuthProvider.authenticate_calls == 0
        )


# =========================================================
# DISCONNECTING (PROPOSE -> CONFIRM)
# =========================================================


class TestDisconnectFlow:

    def test_proposal_does_not_disconnect_yet(
        self, tmp_path
    ):
        agent, drive = make_agent(tmp_path)

        first, second = connect_two_accounts(drive)

        response = agent.chat(
            f"Disconnect {first.email}"
        )

        # It asks for confirmation naming the exact
        # account; NOTHING changed yet.

        assert "confirm disconnect" in response.lower()

        assert first.email in response

        assert drive.registry.count() == 2

        assert len(regular_tokens(drive)) == 2

    def test_confirmation_removes_exactly_one(
        self, tmp_path
    ):
        agent, drive = make_agent(tmp_path)

        first, second = connect_two_accounts(drive)

        agent.chat(f"Disconnect {first.email}")

        response = agent.chat("confirm disconnect")

        assert "Disconnected" in response

        assert drive.registry.count() == 1

        remaining = [
            entry.id
            for entry in drive.registry.list_accounts()
        ]

        assert remaining == [second.id]

        assert regular_tokens(drive) == [
            f"{second.id}.json"
        ]

        assert "no files were deleted" in (
            response.lower()
        )

    def test_cancel_keeps_everything(self, tmp_path):
        agent, drive = make_agent(tmp_path)

        first, _ = connect_two_accounts(drive)

        agent.chat(f"Disconnect {first.email}")

        response = agent.chat("cancel")

        assert "cancelled" in response.lower()

        assert drive.registry.count() == 2

        assert len(regular_tokens(drive)) == 2

    def test_pending_state_is_single_use(self, tmp_path):
        agent, drive = make_agent(tmp_path)

        first, _ = connect_two_accounts(drive)

        agent.chat(f"Disconnect {first.email}")

        # An ambiguous reply cancels instead of guessing.

        cancelled = agent.chat(
            "what about my files?"
        )

        assert "cancelled" in cancelled.lower()

        # A later 'yes' must NOT resurrect the request;
        # it falls through to normal handling (chat).

        agent.chat("yes")

        assert drive.registry.count() == 2

        assert len(agent.ai.prompts) >= 1

    def test_unknown_selector_fails_safely(
        self, tmp_path
    ):
        agent, drive = make_agent(tmp_path)

        connect_two_accounts(drive)

        response = agent.chat(
            "Disconnect ghost@nowhere.com"
        )

        assert drive.registry.count() == 2

        assert len(regular_tokens(drive)) == 2

        # Failure lists what IS connected.

        assert "a@x.com" in response

    def test_missing_selector_asks_which_account(
        self, tmp_path
    ):
        agent, drive = make_agent(tmp_path)

        connect_two_accounts(drive)

        # This phrase has no account noun/google/email,
        # so it may route to chat instead. Either way it
        # must NEVER disconnect without an exact target
        # plus confirmation.

        agent.chat("Disconnect one of them")

        assert drive.registry.count() == 2

        assert len(regular_tokens(drive)) == 2


# =========================================================
# IMPLICIT AUTHENTICATION IS IMPOSSIBLE
# =========================================================


class TestNoImplicitAuthentication:

    def test_local_questions_never_authenticate(
        self, tmp_path, monkeypatch
    ):
        agent, drive = make_agent(tmp_path)

        connect_two_accounts(drive)

        # Any attempt to START authentication explodes.

        def forbidden_start(*args, **kwargs):
            raise AssertionError(
                "authentication started implicitly"
            )

        monkeypatch.setattr(
            agent.router.auth_manager,
            "start_authentication",
            forbidden_start,
        )

        agent.chat("What is my CPU usage?")

        agent.chat("Show my connected Google accounts")

        assert (
            FakeAuthProvider.authenticate_calls == 0
        )

        assert drive.registry.count() == 2

    def test_replies_never_leak_planted_secrets(
        self, tmp_path
    ):
        agent, drive = make_agent(tmp_path)

        first, second = connect_two_accounts(drive)

        write_token(
            drive,
            first.id,
            SECRET_MARKERS[1],
        )

        conversations = [
            "Show my connected Google accounts",
            f"Disconnect {first.email}",
            "cancel",
        ]

        for message in conversations:

            response = agent.chat(message)

            for marker in SECRET_MARKERS:
                assert marker not in response
