"""Paginated character grid picker for Text vinyl (Google Docs–style)."""

from __future__ import annotations

from typing import Any, Callable

from tkinter import BOTH, LEFT, RIGHT, X, Button, Entry, Frame, Label, StringVar, ttk

from i18n import ui_font_name
from text.char_libraries import GRID_COLUMNS, filtered_char_count, library_total, paginate_library


class CharGridPicker:
    """Searchable, paginated grid of insertable characters."""

    def __init__(
        self,
        parent,
        app: Any,
        library_id: str,
        *,
        on_insert: Callable[[str], None],
        label_key: str,
        framed: bool = True,
    ) -> None:
        self.app = app
        self.library_id = library_id
        self.on_insert = on_insert
        self.label_key = label_key
        self._framed = bool(framed)
        self._page = 0
        self._loaded = False
        self.search_var = StringVar()
        if self._framed:
            self.frame = ttk.LabelFrame(parent, text=self._tr(label_key))
        else:
            self.frame = Frame(parent)
        self._top_frame: Frame | None = None
        self._search_entry: Entry | None = None
        self._status_label: Label | None = None
        self._grid_frame: Frame | None = None
        self._nav_frame: Frame | None = None
        self._grid_buttons: list[Button] = []
        self._build()

    def _tr(self, key: str) -> str:
        from app import tr

        return tr(self.app.lang, key)

    def _themed_frame(self, parent, *, surface: str = "panel") -> Frame:
        frame = Frame(parent)
        frame._theme_surface = surface  # type: ignore[attr-defined]
        return frame

    def _apply_theme(self) -> None:
        try:
            self.app.themes.apply_widget(self.frame)
            from ui.theme_states import refresh_ttk_widgets

            refresh_ttk_widgets(self.frame, self.app.themes)
        except Exception:
            pass

    def _build(self) -> None:
        app = self.app
        if self._framed:
            app.translated.append((self.frame, self.label_key, "text"))

        self._top_frame = self._themed_frame(self.frame, surface="panel")
        self._top_frame.pack(fill=X, padx=10, pady=(8, 4))
        app._label(self._top_frame, "text_char_search").pack(side=LEFT)
        self._search_entry = Entry(self._top_frame, textvariable=self.search_var, width=18)
        self._search_entry.pack(side=LEFT, padx=8)
        self._search_entry.bind("<KeyRelease>", lambda _e: self._on_search_changed())

        self._status_label = app._label(self._top_frame, "text_char_page_status", theme_role="muted")
        self._status_label.pack(side=RIGHT)

        self._grid_frame = self._themed_frame(self.frame, surface="panel_alt")
        self._grid_frame.pack(fill=BOTH, expand=True, padx=10, pady=(0, 4))

        self._nav_frame = self._themed_frame(self.frame, surface="panel")
        self._nav_frame.pack(fill=X, padx=10, pady=(0, 8))
        app._button(self._nav_frame, "text_char_page_prev", self._prev_page).pack(side=LEFT)
        app._button(self._nav_frame, "text_char_page_next", self._next_page).pack(side=LEFT, padx=8)
        app._button(self._nav_frame, "text_char_insert", self._insert_focused).pack(side=RIGHT)

        self.search_var.trace_add("write", lambda *_args: self._on_search_changed())
        self._apply_theme()

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        self._apply_theme()
        self.refresh()

    def _on_search_changed(self) -> None:
        if not self._loaded:
            return
        self._page = 0
        self.refresh()

    def _prev_page(self) -> None:
        if not self._loaded:
            return
        if self._page > 0:
            self._page -= 1
            self.refresh()

    def _next_page(self) -> None:
        if not self._loaded:
            return
        self._page += 1
        self.refresh()

    def _insert_focused(self) -> None:
        if not self._loaded:
            return
        for button in self._grid_buttons:
            try:
                if button.focus_get() == button:
                    self.on_insert(button.cget("text"))
                    return
            except Exception:
                pass
        query = self.search_var.get().strip()
        page_chars, _, _ = paginate_library(self.library_id, self._page, query)
        if page_chars:
            self.on_insert(page_chars[0])

    def refresh(self) -> None:
        if not self._loaded:
            return
        query = self.search_var.get().strip()
        page_chars, self._page, total_pages = paginate_library(self.library_id, self._page, query)
        self._render_grid(page_chars)
        if self._status_label is not None:
            total = library_total(self.library_id)
            shown = filtered_char_count(self.library_id, query)
            self._status_label.config(
                text=self._tr("text_char_page_status").format(
                    page=self._page + 1,
                    pages=total_pages,
                    shown=shown,
                    total=total,
                )
            )

    def _render_grid(self, chars: list[str]) -> None:
        if self._grid_frame is None:
            return
        for button in self._grid_buttons:
            button.destroy()
        self._grid_buttons.clear()

        tokens = self.app.themes.tokens
        ui_font = ui_font_name(self.app.lang)
        columns = GRID_COLUMNS
        for index, char in enumerate(chars):
            row = index // columns
            col = index % columns
            btn = Button(
                self._grid_frame,
                text=char,
                width=2,
                font=(ui_font, 11),
                relief="flat",
                bd=1,
                highlightthickness=1,
                highlightbackground=tokens.border,
                bg=tokens.panel_alt,
                fg=tokens.text,
                activebackground=tokens.button_active,
                activeforeground=tokens.button_active_fg,
                command=lambda c=char: self.on_insert(c),
            )
            btn.grid(row=row, column=col, padx=1, pady=1, sticky="nsew")
            btn.bind("<Double-Button-1>", lambda _e, c=char: self.on_insert(c))
            self._grid_buttons.append(btn)

        for col in range(columns):
            self._grid_frame.columnconfigure(col, weight=1)

    def on_language_changed(self) -> None:
        if self._framed:
            try:
                self.frame.config(text=self._tr(self.label_key))
            except Exception:
                pass
        self.refresh()

    def on_theme_changed(self) -> None:
        self._apply_theme()
        self.refresh()
