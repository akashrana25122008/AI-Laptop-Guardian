import customtkinter as ctk

from ui.components import format_bytes_short


class CleanupView(ctk.CTkFrame):
    """
    Cleanup preview + confirmation.

    Milestone 6 safety rules are preserved: the UI never
    performs deletion.  It shows safe candidates, proposes
    deletion through ActionSafety, and waits for an
    explicit confirmation.
    """

    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")

        self.ctrl = controller

        self._body = None

        self._current_safe_items = []

        self._status_label = None

        self._gen_id = 0

        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="Cleanup",
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
            text="Scan temporary files",
            command=self._scan,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="Confirm deletion",
            command=self._confirm,
            fg_color="#c0392b",
            hover_color="#a93226",
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
        pass

    def _scan(self):
        for w in self._body.winfo_children():
            w.destroy()

        self._current_safe_items = []

        ctk.CTkLabel(
            self._body,
            text="Scanning temporary files...",
            text_color="gray",
        ).pack(padx=20, pady=30)

        self._gen_id = self.ctrl.next_gen()

        self.ctrl.run_refresh(
            self,
            self._gen_id,
            self.ctrl.get_cleanup_preview,
            on_done=self._on_preview,
            on_error=self._on_error,
        )

    def _on_preview(self, result):
        if not self.winfo_exists():
            return

        for w in self._body.winfo_children():
            w.destroy()

        if not (
            result.get("success")
            if isinstance(result, dict)
            else False
        ):
            ctk.CTkLabel(
                self._body,
                text="Unable to scan temporary files.",
                text_color="#c0392b",
            ).pack(padx=20, pady=30)
            return

        self._current_safe_items = (
            self.ctrl.get_safe_cleanup_items(result)
        )

        data = result.get("data") or {}

        ctk.CTkLabel(
            self._body,
            text=(
                f"Safe candidates: "
                f"{len(self._current_safe_items)}"
                f"  |  Total scan: "
                f"{data.get('total_files', '?')} "
                f"files  —  "
                f"{data.get('total_size_mb', '?')} MB"
            ),
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(padx=20, pady=(10, 10), anchor="w")

        if not self._current_safe_items:
            ctk.CTkLabel(
                self._body,
                text="No safe deletable files found.",
            ).pack(padx=30, pady=10)
            return

        for item in self._current_safe_items:
            name = item.get("name", "?")

            size = format_bytes_short(
                item.get("size_bytes")
            )

            ctk.CTkLabel(
                self._body,
                text=f"  {name}  —  {size}",
                font=ctk.CTkFont(size=11),
                anchor="w",
            ).pack(padx=30, pady=1, anchor="w")

        total = sum(
            item.get("size_bytes", 0)
            for item in self._current_safe_items
        )

        self._status_label.configure(
            text=(
                f"Ready to request deletion of "
                f"{len(self._current_safe_items)} "
                f"file(s) "
                f"({format_bytes_short(total)})"
            ),
        )

    def _confirm(self):
        if not self._current_safe_items:
            return

        self._status_label.configure(
            text="Confirming deletion...",
        )

        def work():
            self.ctrl.propose_cleanup(
                self._current_safe_items
            )

            return (
                self.ctrl.confirm_cleanup_deletion()
            )

        self.ctrl.run_refresh(
            self,
            self.ctrl.next_gen(),
            work,
            on_done=self._on_result,
            on_error=self._on_error,
        )

    def _cancel(self):
        try:
            if not self.ctrl.agent.safety.has_pending():
                return
        except Exception:
            return

        try:
            result = self.ctrl.cancel_cleanup()
        except Exception:
            result = "Unable to cancel."

        if self.winfo_exists():
            self._status_label.configure(
                text=str(result),
            )

    def _on_result(self, message):
        if not self.winfo_exists():
            return

        self._current_safe_items = []

        self._status_label.configure(
            text=str(message),
        )

    def _on_error(self, _exc):
        if not self.winfo_exists():
            return

        for w in self._body.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self._body,
            text="Unable to complete cleanup.\nPlease try again.",
            text_color="#c0392b",
        ).pack(padx=20, pady=30)
