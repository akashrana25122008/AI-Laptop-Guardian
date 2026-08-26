"""
Headless application controller.

This module is the ONLY place where the UI talks to the
existing backend.  Every public method returns plain dicts,
strings, or simple lists that the thin widget layer can
render without interpretation.

This module is fully testable without a display server.
"""

import os
import threading
import itertools

from agent.result_contract import (
    ensure_result,
    is_successful_result,
)

from app.version import __version__
from ui.navigation import NAV_ITEMS


class GuardianController:
    """
    Coordinates the desktop UI with the existing
    application layer.

    All heavy operations (AI chat, cloud analytics,
    storage scans) are designed to be called from
    background threads.  The widget layer is responsible
    for marshalling results back to the main thread.
    """

    def __init__(self, agent=None):

        from agent.ai_agent import AIAgent

        self.agent = agent or AIAgent()

        self._current_view = "dashboard"

        self._last_health = None

        self._root = None

        self._shutting_down = False

        self._gen_counter = itertools.count()

    # =====================================================
    # ONBOARDING STATUS
    # =====================================================

    def get_onboarding_status(self):
        """Return safe status info for the onboarding display.

        No OAuth, no network calls, no secrets exposed.
        """
        from app.version import __version__

        ollama_status = "Not available"
        ollama_available = False

        try:
            from ollama import list as ollama_list
            models = ollama_list()
            names = [
                m.get("name", "")
                for m in models.get("models", [])
            ]
            if names:
                ollama_status = f"Available ({len(names)} model{'s' if len(names) != 1 else ''})"
                ollama_available = True
            else:
                ollama_status = "Running (no models installed)"
                ollama_available = True
        except Exception:
            ollama_status = "Not available"

        google_status = "Not connected"
        try:
            accounts_data = ensure_result(
                self.agent.router.execute("cloud_accounts"),
                "cloud_accounts",
            )
            acc_list = (
                accounts_data.get("accounts")
                if isinstance(accounts_data, dict)
                else None
            ) or []
            if acc_list:
                google_status = (
                    f"Connected ({len(acc_list)} account"
                    f"{'s' if len(acc_list) != 1 else ''})"
                )
        except Exception:
            pass

        return {
            "version": __version__,
            "ollama_status": ollama_status,
            "ollama_available": ollama_available,
            "google_status": google_status,
            "local_storage": "Available",
        }

    # =====================================================
    # NAVIGATION
    # =====================================================

    @property
    def current_view(self):
        return self._current_view

    def open_view(self, view_key):
        valid = {
            key for key, _ in NAV_ITEMS
        }

        if view_key not in valid:
            raise ValueError(
                f"Unknown view: {view_key}"
            )

        self._current_view = view_key

        return view_key

    # =====================================================
    # DASHBOARD (CHEAP SYNC FOR IMMEDIATE DISPLAY)
    # =====================================================

    def get_dashboard(self):
        """
        Collect a lightweight snapshot of every dashboard
        card from the actual backend tools.

        Each card is a plain dict:

            {"label": str, "value": str, "detail": str, "ok": bool}

        Long-running work (large-file scan, cloud
        analytics) is NOT included here; the Dashboard
        view fetches those lazily after initial render.
        """

        cards = []

        # --- Health score ---

        health = ensure_result(
            self.agent.router.execute("health"),
            "health",
        )

        if is_successful_result(health):

            overall = (
                (health.get("data") or {})
                .get("overall") or {}
            )

            score = overall.get("score")
            status_text = overall.get(
                "status", "Unknown"
            )

            cards.append({
                "label": "Health",
                "value": (
                    f"{status_text} ({score})"
                    if score is not None
                    else status_text
                ),
                "detail": "",
                "ok": (
                    overall.get("score", 0) >= 70
                ),
            })

        else:

            cards.append({
                "label": "Health",
                "value": "Unavailable",
                "detail": health.get(
                    "error", "Unknown"
                ),
                "ok": False,
            })

        # --- CPU ---

        cpu = ensure_result(
            self.agent.router.execute("cpu"),
            "cpu",
        )

        if is_successful_result(cpu):
            d = cpu.get("data") or {}
            cards.append({
                "label": "CPU",
                "value": (
                    f"{d.get('usage_percent', '?')}%"
                ),
                "detail": d.get("status", ""),
                "ok": d.get("usage_percent", 100) < 90,
            })
        else:
            cards.append({
                "label": "CPU",
                "value": "Unavailable",
                "detail": "",
                "ok": False,
            })

        # --- RAM ---

        ram = ensure_result(
            self.agent.router.execute("ram"),
            "ram",
        )

        if is_successful_result(ram):
            d = ram.get("data") or {}
            cards.append({
                "label": "RAM",
                "value": (
                    f"{d.get('usage_percent', '?')}%"
                ),
                "detail": d.get("status", ""),
                "ok": d.get("usage_percent", 100) < 90,
            })
        else:
            cards.append({
                "label": "RAM",
                "value": "Unavailable",
                "detail": "",
                "ok": False,
            })

        # --- Battery ---

        bat = ensure_result(
            self.agent.router.execute("battery"),
            "battery",
        )

        if is_successful_result(bat):
            d = bat.get("data") or {}
            pct = d.get("percent")
            charging = d.get("charging")
            detail_parts = []
            if charging is not None:
                detail_parts.append(
                    "Charging"
                    if charging
                    else "On battery"
                )
            tr = d.get("time_remaining")
            if tr:
                detail_parts.append(tr)
            cards.append({
                "label": "Battery",
                "value": (
                    f"{pct}%" if pct is not None
                    else "Unknown"
                ),
                "detail": " ".join(detail_parts),
                "ok": (
                    pct is None
                    or pct > 20
                ),
            })
        else:
            cards.append({
                "label": "Battery",
                "value": "Unavailable",
                "detail": "",
                "ok": False,
            })

        # --- Primary local drive (C:) ---

        storage = ensure_result(
            self.agent.router.execute("storage"),
            "storage",
        )

        if is_successful_result(storage):
            drives = (
                (storage.get("data") or {})
                .get("drives") or []
            )

            primary = next(
                (
                    dr for dr in drives
                    if isinstance(dr, dict)
                    and "C" in str(
                        dr.get("drive", "")
                    ).upper()
                ),
                drives[0] if drives else None,
            )

            if (
                primary
                and isinstance(primary, dict)
            ):
                pct = primary.get(
                    "percent_used", "?"
                )
                free = primary.get("free_gb", "?")
                total = primary.get("total_gb", "?")
                st = primary.get("status", "")
                cards.append({
                    "label": (
                        primary.get("drive", "C:")
                    ),
                    "value": f"{pct}% used",
                    "detail": (
                        f"{free} GB free of "
                        f"{total} GB | {st}"
                    ),
                    "ok": (
                        primary.get(
                            "percent_used", 0
                        )
                        < 90
                    ),
                })
            else:
                cards.append({
                    "label": "Drive",
                    "value": "No drives found",
                    "detail": "",
                    "ok": False,
                })
        else:
            cards.append({
                "label": "Drive",
                "value": "Unavailable",
                "detail": "",
                "ok": False,
            })

        # --- Cloud accounts count ---

        accounts = ensure_result(
            self.agent.router.execute(
                "cloud_accounts"
            ),
            "cloud_accounts",
        )

        if is_successful_result(accounts):
            acc_list = accounts.get("accounts") or []
            cards.append({
                "label": "Google Accounts",
                "value": str(len(acc_list)),
                "detail": (
                    "Connected"
                    if acc_list
                    else "None connected"
                ),
                "ok": True,
            })
        else:
            cards.append({
                "label": "Google Accounts",
                "value": "0",
                "detail": "",
                "ok": True,
            })

        # --- Status bar text (derived deterministically) ---

        status_text = "Protected"

        for card in cards:

            if not card["ok"]:

                status_text = "Attention Needed"

                break

        self._last_health = health

        return {
            "cards": cards,
            "status": status_text,
        }

    # =====================================================
    # HEALTH (FULL REPORT)
    # =====================================================

    def get_health_report(self):
        return ensure_result(
            self.agent.router.execute("health"),
            "health",
        )

    def get_health_recommendations(self, result):
        """
        Extract deterministic priority recommendations
        from the existing health result.

        Recommendations never originate in this module.
        """

        if not is_successful_result(result):
            return []

        data = result.get("data") or {}

        components = (
            data.get("component_scores") or {}
        )

        recs = []

        # These thresholds match the existing health
        # tool's own warning semantics.

        storage_score = components.get(
            "storage", 100
        )

        if storage_score < 70:
            recs.append(
                "Local storage is under pressure. "
                "Consider running Cleanup."
            )

        ram_pct = (
            (data.get("ram") or {})
            .get("data") or {}
        ).get("usage_percent", 0)

        if ram_pct > 85:
            recs.append(
                "RAM usage is high.  Close heavy "
                "applications to free memory."
            )

        bat_pct = (
            (data.get("battery") or {})
            .get("data") or {}
        ).get("percent")

        if bat_pct is not None and bat_pct < 25:
            recs.append(
                "Battery is low.  Connect your "
                "charger."
            )

        return recs

    # =====================================================
    # STORAGE
    # =====================================================

    def get_local_drives(self):
        return ensure_result(
            self.agent.router.execute("storage"),
            "storage",
        )

    def get_large_files(self):
        return ensure_result(
            self.agent.router.execute("large_files"),
            "large_files",
        )

    def get_local_duplicates(self):
        return ensure_result(
            self.agent.router.execute("duplicates"),
            "duplicates",
        )

    # =====================================================
    # CLEANUP (MILESTONE 6 SAFETY MODEL)
    #
    # The UI NEVER performs deletion.  It asks the
    # controller to snapshot candidates, then the
    # existing safety layer holds the exact items.
    # Confirmation goes through agent.chat() which uses
    # ActionSafety — the same path as chat.py.
    # =====================================================

    def get_cleanup_preview(self):
        return ensure_result(
            self.agent.router.execute(
                "cleanup_preview"
            ),
            "cleanup_preview",
        )

    def get_safe_cleanup_items(self, preview_result):
        """
        Extract ONLY deletable candidates from the
        preview result.

        Protected, locked, and review items are never
        included.
        """

        if not is_successful_result(preview_result):
            return []

        candidates = (
            (preview_result.get("data") or {})
            .get("candidates") or []
        )

        return [
            item
            for item in candidates
            if isinstance(item, dict)
            and item.get("classification") == "safe"
        ]

    def propose_cleanup(self, safe_items):
        """
        Hold the exact snapshot in ActionSafety.

        Returns the human-readable proposal, or raises
        ValueError if items are invalid.
        """

        self.agent.safety.propose_cleanup(
            safe_items
        )

        pending = self.agent.safety.get_pending()

        if pending is None:
            return "Cleanup proposed."

        return pending.describe()

    def request_cleanup_deletion(self, safe_items):
        """
        Convenience: propose + immediately surface the
        confirmation message for the UI dialog.
        """

        return self.propose_cleanup(safe_items)

    def confirm_cleanup_deletion(self):
        """
        Confirm the pending cleanup through the existing
        agent chat path.

        Returns the execution result message.
        """

        return self.agent.chat("confirm delete")

    def cancel_cleanup(self):
        """
        Cancel a pending cleanup proposal.
        """

        return self.agent.chat("cancel")

    # =====================================================
    # CLOUD (MILESTONE 8 READ-ONLY INTELLIGENCE)
    # =====================================================

    def get_cloud_storage(self):
        return self.agent.router.execute_cloud_storage()

    def get_cloud_large_files(self):
        return (
            self.agent.router
            .execute_cloud_large_files()
        )

    def get_cloud_duplicates(self):
        return (
            self.agent.router
            .execute_cloud_duplicates()
        )

    # =====================================================
    # ACCOUNTS (MILESTONE 9)
    # =====================================================

    def get_accounts(self):
        return self.agent.router.execute(
            "cloud_accounts"
        )

    def connect_account(self):
        """
        Start + complete the Google OAuth handshake.

        MUST run in a background thread: the consent
        flow blocks on a local HTTP server and on the
        user interacting with a browser window.
        """

        return self.agent.router.execute(
            "cloud_connect"
        )

    def request_disconnect(self, account_ref):
        """
        Propose disconnecting exactly one account.

        Returns the proposal message the UI must show.
        """

        message = (
            f"Disconnect {account_ref}"
        )

        return self.agent.chat(message)

    def confirm_disconnect(self):
        return self.agent.chat(
            "confirm disconnect"
        )

    def cancel_disconnect(self):
        return self.agent.chat("cancel")

    # =====================================================
    # CHAT / ASSISTANT
    # =====================================================

    def ask(self, message):
        return self.agent.chat(message)

    # =====================================================
    # SETTINGS (NON-SECRET INFO)
    # =====================================================

    def get_settings(self):

        model = getattr(
            self.agent.ai, "model", "unknown"
        )

        token_dir = str(
            self.agent.router.drive_manager.token_dir
        )

        # Probe Ollama with a short timeout so the
        # settings page never freezes.

        ollama_status = "Unavailable"

        try:

            from ollama import list as ollama_list

            models = ollama_list()

            names = [
                m.get("name", "")
                for m in models.get("models", [])
            ]

            if model in names:
                ollama_status = "Ready"
            elif names:
                ollama_status = (
                    f"Available ({len(names)} model"
                    f"{'s' if len(names) != 1 else ''})"
                )
            else:
                ollama_status = (
                    "Running (no local models found)"
                )

        except Exception:
            ollama_status = "Unavailable"

        # Cloud accounts count — safe, no secrets.

        account_count = 0
        try:
            accounts_data = ensure_result(
                self.agent.router.execute("cloud_accounts"),
                "cloud_accounts",
            )
            acc_list = (
                accounts_data.get("accounts")
                if isinstance(accounts_data, dict)
                else None
            ) or []
            account_count = len(acc_list)
        except Exception:
            pass

        # Onboarding state.

        try:
            import app.state as state_mod
            onboarding_done = state_mod.is_onboarding_completed()
        except Exception:
            onboarding_done = False

        # Theme — persisted preference.

        try:
            import app.state as state_mod
            theme = state_mod.get_theme()
        except Exception:
            theme = "System"

        return {
            "model": model,
            "ollama_status": ollama_status,
            "token_dir": token_dir,
            "version": __version__,
            "theme": theme,
            "account_count": account_count,
            "onboarding_completed": onboarding_done,
        }

    # =====================================================
    # BACKGROUND THREAD HELPER
    #
    # The thin Tk layer wraps calls in this helper so
    # long-running operations never freeze the main
    # thread.  Headless tests call the underlying
    # methods directly.
    # =====================================================

    def run_in_background(
        self, fn, on_done, on_error=None
    ):
        """
        Run *fn* in a daemon thread.

        On completion, *on_done(result)* is called
        safely on the main thread.  On exception,
        *on_error(exception)* is called if provided,
        otherwise the error is logged and discarded.

        When a Tk root window is available the callbacks
        are dispatched through ``root.after`` so they
        always execute on the main thread.  In headless
        mode (no root) the callbacks run directly.
        """

        root = self._root

        def worker():
            try:
                result = fn()
            except Exception as exc:
                if on_error is not None:
                    if root is not None:
                        root.after(
                            0,
                            lambda e=exc: on_error(e),
                        )
                    else:
                        on_error(exc)
                return

            if root is not None:
                root.after(
                    0,
                    lambda r=result: on_done(r),
                )
            else:
                on_done(result)

        thread = threading.Thread(
            target=worker, daemon=True
        )

        thread.start()

        return thread

    # =====================================================
    # STALE-RESULT PROTECTION
    #
    # Rapid tab switching or repeated button presses can
    # spawn overlapping background tasks.  ``run_refresh``
    # wraps ``run_in_background`` with a generation counter
    # so that stale callbacks are silently discarded and
    # never corrupt the UI with older data.
    # =====================================================

    def next_gen(self):
        """Return a fresh generation ID for tracking."""
        return next(self._gen_counter)

    def run_refresh(
        self, view, gen_id, fn, on_done, on_error=None
    ):
        """
        Run *fn* in a background thread with staleness
        protection tied to *gen_id*.

        The caller should bump *gen_id* (via ``next_gen``)
        before each refresh.  If the generation has moved
        on by the time the callback fires, the result is
        silently discarded.

        Parameters
        ----------
        view : object
            The calling view instance; used for
            ``winfo_exists()`` when a Tk root is set.
        gen_id : int
            The generation counter captured at refresh
            start.
        fn : callable
            Work function to run in background.
        on_done : callable
            Called with the result on the main thread.
        on_error : callable, optional
            Called with the exception on the main thread.
        """

        if self._shutting_down:
            return None

        root = self._root

        def wrapped_done(result):
            if getattr(self, "_shutting_down", False):
                return
            if not getattr(view, "winfo_exists", None) or not view.winfo_exists():
                return
            if getattr(view, "_gen_id", gen_id) != gen_id:
                return
            on_done(result)

        def wrapped_error(exc):
            if getattr(self, "_shutting_down", False):
                return
            if on_error is not None:
                if not getattr(view, "winfo_exists", None) or not view.winfo_exists():
                    return
                if getattr(view, "_gen_id", gen_id) != gen_id:
                    return
                on_error(exc)

        def worker():
            try:
                result = fn()
            except Exception as exc:
                if root is not None:
                    root.after(
                        0,
                        lambda e=exc: wrapped_error(e),
                    )
                else:
                    wrapped_error(exc)
                return

            if root is not None:
                root.after(
                    0,
                    lambda r=result: wrapped_done(r),
                )
            else:
                wrapped_done(result)

        thread = threading.Thread(
            target=worker, daemon=True
        )

        thread.start()

        return thread
