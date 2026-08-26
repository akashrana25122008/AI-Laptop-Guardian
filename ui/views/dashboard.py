import customtkinter as ctk

from ui.components import safe_text


class DashboardView(ctk.CTkFrame):
    """Summary cards + assistant chat."""

    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")

        self.ctrl = controller

        self._cards_frame = None

        self._assistant_entry = None

        self._assistant_output = None

        self._gen_id = 0

        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="Dashboard",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(
            row=0, column=0,
            padx=20, pady=(20, 10), sticky="w",
        )

        self._cards_frame = ctk.CTkFrame(
            self, fg_color="transparent"
        )

        self._cards_frame.grid(
            row=1, column=0,
            padx=20, pady=(0, 10), sticky="nsew",
        )

        self.grid_rowconfigure(1, weight=1)

        self._build_assistant()

    def _build_assistant(self):
        panel = ctk.CTkFrame(self)

        panel.grid(
            row=2, column=0,
            padx=20, pady=(0, 20), sticky="nsew",
        )

        ctk.CTkLabel(
            panel,
            text="AI Assistant",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=12, pady=(10, 4), anchor="w")

        ctk.CTkLabel(
            panel,
            text="Ask about your laptop in plain English",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(padx=12, anchor="w")

        self._assistant_output = ctk.CTkTextbox(
            panel, height=80, state="disabled",
            wrap="word",
        )

        self._assistant_output.pack(
            padx=12, pady=(4, 8), fill="x",
        )

        row = ctk.CTkFrame(
            panel, fg_color="transparent"
        )

        row.pack(padx=12, pady=(0, 12), fill="x")

        self._assistant_entry = ctk.CTkEntry(
            row,
            placeholder_text="Ask AI Laptop Guardian...",
        )

        self._assistant_entry.pack(
            side="left", fill="x", expand=True,
            padx=(0, 8),
        )

        ctk.CTkButton(
            row, text="Send", width=80,
            command=self._on_send,
        ).pack(side="right")

        quick = ctk.CTkFrame(
            panel, fg_color="transparent"
        )

        quick.pack(padx=12, pady=(0, 12), fill="x")

        ctk.CTkButton(
            quick,
            text="Check my laptop health",
            width=200,
            command=self._quick_health,
        ).pack(side="left")

        ctk.CTkButton(
            quick,
            text="Check storage",
            width=160,
            command=self._quick_storage,
        ).pack(side="left", padx=(8, 0))

    def refresh(self):
        self._set_cards_loading()

        self._gen_id = self.ctrl.next_gen()

        self.ctrl.run_refresh(
            self,
            self._gen_id,
            self.ctrl.get_dashboard,
            on_done=self._on_loaded,
            on_error=self._on_error,
        )

    def _set_cards_loading(self):
        for w in self._cards_frame.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self._cards_frame,
            text="Loading dashboard...",
            text_color="gray",
        ).pack(padx=20, pady=30)

    def _on_loaded(self, data):
        if not self.winfo_exists():
            return

        for w in self._cards_frame.winfo_children():
            w.destroy()

        cards = data.get("cards") if isinstance(data, dict) else None

        if not cards:
            ctk.CTkLabel(
                self._cards_frame,
                text="Dashboard data is temporarily unavailable.",
                text_color="gray",
            ).pack(padx=20, pady=30)
            return

        for idx, card in enumerate(cards):
            if not isinstance(card, dict):
                continue

            r, c = divmod(idx, 3)

            self._cards_frame.grid_columnconfigure(
                c, weight=1,
            )

            f = ctk.CTkFrame(self._cards_frame)

            f.grid(
                row=r, column=c,
                padx=6, pady=6, sticky="nsew",
            )

            ok = card.get("ok")

            color = "#2fa572" if ok else "#c0392b"

            status_indicator = "OK" if ok else "!"

            ctk.CTkLabel(
                f, text=card.get("label", "?"),
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="gray",
            ).pack(padx=12, pady=(10, 0), anchor="w")

            ctk.CTkLabel(
                f, text=card.get("value", "?"),
                font=ctk.CTkFont(size=22),
                text_color=color,
            ).pack(padx=12, pady=(2, 0), anchor="w")

            detail = card.get("detail", "")

            if detail:
                ctk.CTkLabel(
                    f, text=detail,
                    font=ctk.CTkFont(size=11),
                    text_color="gray",
                    wraplength=200,
                ).pack(
                    padx=12, pady=(0, 6), anchor="w",
                )

            ctk.CTkLabel(
                f,
                text=f"[{status_indicator}]",
                font=ctk.CTkFont(size=10),
                text_color=color,
            ).pack(padx=12, pady=(0, 10), anchor="w")

        status = data.get("status", "") if isinstance(data, dict) else ""

        if status:
            self.event_generate(
                "<<StatusUpdate>>", data=status,
            )

    def _on_error(self, _exc):
        if not self.winfo_exists():
            return

        for w in self._cards_frame.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self._cards_frame,
            text=(
                "Unable to load dashboard data.\n"
                "Please try again."
            ),
            text_color="#c0392b",
        ).pack(padx=20, pady=30)

    def _set_assistant(self, text):
        if not self.winfo_exists():
            return

        self._assistant_output.configure(state="normal")
        self._assistant_output.delete("1.0", "end")
        self._assistant_output.insert("1.0", text)
        self._assistant_output.configure(state="disabled")

    def _on_send(self):
        msg = self._assistant_entry.get().strip()

        if not msg:
            return

        self._assistant_entry.delete(0, "end")
        self._set_assistant("Thinking...")

        self.ctrl.run_refresh(
            self,
            self.ctrl.next_gen(),
            lambda: self.ctrl.ask(msg),
            on_done=lambda r: self._set_assistant(
                safe_text(str(r), "No response received.")
            ),
            on_error=lambda _: self._set_assistant(
                "Unable to get a response. "
                "Please check that Ollama is running."
            ),
        )

    def _quick_health(self):
        self._set_assistant("Checking laptop health...")

        self.ctrl.run_refresh(
            self,
            self.ctrl.next_gen(),
            lambda: self.ctrl.ask(
                "Generate a laptop health report"
            ),
            on_done=lambda r: self._set_assistant(
                safe_text(str(r), "No health data available.")
            ),
            on_error=lambda _: self._set_assistant(
                "Unable to check health. "
                "Please try again later."
            ),
        )

    def _quick_storage(self):
        self._set_assistant("Checking storage...")

        self.ctrl.run_refresh(
            self,
            self.ctrl.next_gen(),
            lambda: self.ctrl.ask(
                "Show me my local storage usage"
            ),
            on_done=lambda r: self._set_assistant(
                safe_text(str(r), "No storage data available.")
            ),
            on_error=lambda _: self._set_assistant(
                "Unable to check storage. "
                "Please try again later."
            ),
        )
