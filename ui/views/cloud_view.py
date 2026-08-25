import customtkinter as ctk

from ui.components import format_bytes_short, safe_text


class CloudView(ctk.CTkFrame):
    """Milestone 8 read-only cloud intelligence display."""

    def __init__(self, parent, controller):
        super().__init__(parent, fg_color="transparent")

        self.ctrl = controller

        self._body = None

        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="Cloud Storage Intelligence",
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
            padx=20, pady=(0, 20), sticky="nsew",
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
            btn_row, text="Load storage summary",
            command=self._load_summary,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="Load large files",
            command=self._load_large,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="Load duplicates",
            command=self._load_dup,
        ).pack(side="left")

    def refresh(self):
        self._load_summary_async()

    def _load_summary_async(self):
        self._clear_body("Loading cloud data...")

        self.ctrl.run_in_background(
            self.ctrl.get_cloud_storage,
            on_done=self._on_summary,
            on_error=self._on_error,
        )

    def _load_summary(self):
        self._clear_body("Loading cloud data...")

        self.ctrl.run_in_background(
            self.ctrl.get_cloud_storage,
            on_done=self._on_summary,
            on_error=self._on_error,
        )

    def _load_large(self):
        self._clear_body("Loading large files...")

        self.ctrl.run_in_background(
            self.ctrl.get_cloud_large_files,
            on_done=self._on_large,
            on_error=self._on_error,
        )

    def _load_dup(self):
        self._clear_body("Loading duplicates...")

        self.ctrl.run_in_background(
            self.ctrl.get_cloud_duplicates,
            on_done=self._on_dup,
            on_error=self._on_error,
        )

    def _clear_body(self, loading_msg):
        for w in self._body.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self._body,
            text=loading_msg,
            text_color="gray",
        ).pack(padx=20, pady=30)

    def _on_summary(self, result):
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
                text="Cloud data unavailable.",
                text_color="#c0392b",
            ).pack(padx=20, pady=30)
            return

        entries = result.get("accounts") or []

        totals = result.get("totals") or {}

        if not entries:
            ctk.CTkLabel(
                self._body,
                text="No cloud accounts connected.",
            ).pack(padx=20, pady=30)
            return

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            email = entry.get(
                "email", entry.get("account", "?")
            )

            storage = entry.get("storage") or {}

            used = storage.get("used_bytes")
            free = storage.get("free_bytes")
            total = storage.get("total_bytes")

            used_str = (
                format_bytes_short(used)
                if used is not None
                else "Unavailable"
            )

            free_str = (
                format_bytes_short(free)
                if free is not None
                else "Unavailable"
            )

            total_str = (
                format_bytes_short(total)
                if total is not None
                else "Unavailable"
            )

            ctk.CTkLabel(
                self._body,
                text=(
                    f"{email}:  "
                    f"{used_str} used  |  "
                    f"{free_str} free  |  "
                    f"{total_str} total"
                ),
                font=ctk.CTkFont(size=12),
                anchor="w",
            ).pack(padx=30, pady=3, anchor="w")

            errors = entry.get("errors") or []

            for err in errors:
                ctk.CTkLabel(
                    self._body,
                    text=f"   ⚠ {safe_text(err)}",
                    text_color="#c0392b",
                    font=ctk.CTkFont(size=11),
                    anchor="w",
                ).pack(padx=40, pady=1, anchor="w")

        if totals:
            t_used = totals.get("known_used_bytes")
            t_free = totals.get("known_free_bytes")
            included = totals.get(
                "included_account_ids"
            ) or []

            ctk.CTkLabel(
                self._body,
                text=(
                    f"Total ({len(included)} account"
                    f"{'s' if len(included) != 1 else ''}):  "
                    f"{format_bytes_short(t_used) if t_used is not None else '?'} used  |  "
                    f"{format_bytes_short(t_free) if t_free is not None else '?'} free"
                ),
                font=ctk.CTkFont(
                    size=12, weight="bold"
                ),
                anchor="w",
            ).pack(
                padx=30, pady=(16, 4), anchor="w",
            )

    def _on_large(self, result):
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
                text="Cloud large-file data unavailable.",
                text_color="#c0392b",
            ).pack(padx=20, pady=30)
            return

        files = (
            result.get("files") or []
        )[:15]

        if not files:
            ctk.CTkLabel(
                self._body,
                text="No large cloud files found.",
            ).pack(padx=20, pady=30)
            return

        ctk.CTkLabel(
            self._body,
            text=f"Large cloud files ({len(files)} shown)",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(padx=20, pady=(10, 6), anchor="w")

        for f in files:
            if not isinstance(f, dict):
                continue

            ctk.CTkLabel(
                self._body,
                text=(
                    f"  {f.get('name', '?')}  —  "
                    f"{format_bytes_short(f.get('size_bytes'))}"
                ),
                font=ctk.CTkFont(size=11),
                anchor="w",
            ).pack(padx=30, pady=1, anchor="w")

    def _on_dup(self, result):
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
                text="Cloud duplicate data unavailable.",
                text_color="#c0392b",
            ).pack(padx=20, pady=30)
            return

        groups = (
            result.get("groups") or []
        )[:15]

        if not groups:
            ctk.CTkLabel(
                self._body,
                text="No cloud duplicate candidates.",
            ).pack(padx=20, pady=30)
            return

        ctk.CTkLabel(
            self._body,
            text="Cloud duplicate candidates",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(padx=20, pady=(10, 6), anchor="w")

        for g in groups:
            if not isinstance(g, dict):
                continue

            ctk.CTkLabel(
                self._body,
                text=(
                    f"  {g.get('copies', '?')} copies"
                    f"  —  "
                    f"{format_bytes_short(g.get('size_bytes'))}"
                ),
                font=ctk.CTkFont(size=11),
                anchor="w",
            ).pack(padx=30, pady=1, anchor="w")

    def _on_error(self, _exc):
        if not self.winfo_exists():
            return

        for w in self._body.winfo_children():
            w.destroy()

        ctk.CTkLabel(
            self._body,
            text="Unable to load cloud data.\nPlease try again.",
            text_color="#c0392b",
        ).pack(padx=20, pady=30)
