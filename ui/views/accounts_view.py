import customtkinter as ctk

from ui.components import safe_text, safe_account_count, safe_connect_message


class AccountsView(ctk.CTkFrame):
    """
    Google account management via Milestone 9 APIs.

    Connect runs the existing OAuth flow in a background
    thread.  Disconnect uses agent.chat() to route through
    the existing confirmation layer.
    """

    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")

        self.ctrl = controller

        self._body = None

        self._status_label = None

        self._pending_account = None

        self._selected_account_id = None

        self._gen_id = 0

        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="Google Accounts",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(
            row=0, column=0,
            padx=20, pady=(20, 10), sticky="w",
        )

        self._body = ctk.CTkFrame(
            self, fg_color="transparent"
        )

        self._body.grid(
            row=1, column=0,
            padx=20, pady=(0, 10), sticky="nsew",
        )

        self.grid_rowconfigure(1, weight=1)

        btn_row = ctk.CTkFrame(
            self, fg_color="transparent"
        )

        btn_row.grid(
            row=2, column=0,
            padx=20, pady=(0, 20), sticky="ew",
        )

        ctk.CTkButton(
            btn_row,
            text="+ Connect Google Account",
            command=self._connect,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="Disconnect selected",
            fg_color="#c0392b",
            hover_color="#a93226",
            command=self._disconnect,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="Confirm disconnect",
            command=self._confirm_disconnect,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="Cancel",
            command=self._cancel,
        ).pack(side="left")

        self._status_label = ctk.CTkLabel(
            btn_row, text="", text_color="gray",
        )

        self._status_label.pack(
            side="right", padx=10,
        )

    def refresh(self):
        self._reload_async()

    def _reload_async(self):
        for w in self._body.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self._body,
            text="Loading accounts...",
            text_color="gray",
        ).pack(padx=20, pady=30)

        self._gen_id = self.ctrl.next_gen()

        self.ctrl.run_refresh(
            self,
            self._gen_id,
            self.ctrl.get_accounts,
            on_done=self._on_accounts,
            on_error=self._on_error,
        )

    def _on_accounts(self, result):
        if not self.winfo_exists():
            return

        for w in self._body.winfo_children():
            w.destroy()

        accounts = (
            result.get("accounts")
            if isinstance(result, dict)
            else None
        ) or []

        ctk.CTkLabel(
            self._body,
            text=safe_account_count(accounts),
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack(padx=20, pady=(10, 4), anchor="w")

        ctk.CTkLabel(
            self._body,
            text=(
                "You can connect multiple Google Drive "
                "accounts. Guardian keeps accounts isolated "
                "and never silently chooses another account "
                "for a destructive action."
            ),
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=550,
            justify="left",
        ).pack(padx=20, pady=(0, 10), anchor="w")

        if not accounts:
            ctk.CTkLabel(
                self._body,
                text=(
                    "No Google accounts connected yet.\n"
                    "Click '+ Connect Google Account' "
                    "to start."
                ),
            ).pack(padx=20, pady=20)
            return

        self._selected_account_id = None

        var = ctk.StringVar(value="")

        for idx, acc in enumerate(accounts, 1):
            if not isinstance(acc, dict):
                continue

            display_name = acc.get(
                "display_name",
                acc.get("label", ""),
            )

            email = acc.get("email", "")

            account_id = acc.get("id", "")

            status = acc.get("status", "")

            if display_name and email:
                label_text = f"{idx}. {display_name} ({email})"
            elif email:
                label_text = f"{idx}. {email}"
            else:
                label_text = f"{idx}. Account {account_id}"

            if status:
                label_text += f"  [{status}]"

            row = ctk.CTkFrame(self._body)

            row.pack(
                padx=20, pady=4, fill="x",
            )

            ctk.CTkRadioButton(
                row,
                text=label_text,
                variable=var,
                value=str(account_id),
                font=ctk.CTkFont(size=12),
                anchor="w",
            ).pack(
                padx=12, pady=8, side="left",
            )

        def _on_select(*_args):
            self._selected_account_id = (
                var.get() or None
            )

        var.trace_add("write", _on_select)

    def _connect(self):
        self._status_label.configure(
            text="Starting Google authentication...",
        )

        def work():
            return self.ctrl.connect_account()

        self.ctrl.run_refresh(
            self,
            self.ctrl.next_gen(),
            work,
            on_done=self._on_connect_result,
            on_error=self._on_error,
        )

    def _on_connect_result(self, result):
        if not self.winfo_exists():
            return

        msg = safe_connect_message(result)

        self._status_label.configure(text=msg)

        if isinstance(result, dict) and result.get("success"):
            self._reload_async()

    def _disconnect(self):
        self._status_label.configure(
            text=(
                "Select an account to disconnect, "
                "then click Confirm disconnect."
            ),
        )

    def _confirm_disconnect(self):
        if not self._selected_account_id:
            self._status_label.configure(
                text=(
                    "Select an account first by clicking "
                    "its radio button."
                ),
            )
            return

        try:
            accounts_data = (
                self.ctrl.get_accounts()
            )
        except Exception:
            self._status_label.configure(
                text="Unable to verify accounts."
            )
            return

        accounts = (
            accounts_data.get("accounts")
            if isinstance(accounts_data, dict)
            else None
        ) or []

        target = None

        for acc in accounts:
            if (
                isinstance(acc, dict)
                and acc.get("id")
                == self._selected_account_id
            ):
                target = acc
                break

        if target is None:
            self._status_label.configure(
                text="Selected account not found."
            )
            return

        email = target.get(
            "email", target.get("id")
        )

        self._status_label.configure(
            text=f"Requesting disconnect of {email}...",
        )

        def work():
            return self.ctrl.request_disconnect(
                email
            )

        self.ctrl.run_refresh(
            self,
            self.ctrl.next_gen(),
            work,
            on_done=self._on_proposal,
            on_error=self._on_error,
        )

    def _on_proposal(self, message):
        if not self.winfo_exists():
            return

        text = safe_text(message)

        if "confirm disconnect" in text.lower():
            self._pending_account = True

            self._status_label.configure(
                text=(
                    "Disconnect proposed.  Click "
                    "'Confirm disconnect' again to "
                    "execute, or 'Cancel'."
                ),
            )
            return

        self._pending_account = None

        self._status_label.configure(text=text)

    def _cancel(self):
        if self._pending_account:
            result = self.ctrl.cancel_disconnect()

            self._pending_account = None

            self._status_label.configure(
                text=safe_text(result, "Cancelled."),
            )

    def _on_error(self, _exc):
        if not self.winfo_exists():
            return

        for w in self._body.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self._body,
            text=(
                "Unable to load accounts.\n"
                "Please try again."
            ),
            text_color="#c0392b",
        ).pack(padx=20, pady=30)
