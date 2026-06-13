"""Modal character library for inserting symbols into the Text vinyl editor."""

from __future__ import annotations

from tkinter import BOTH, X, Frame, Toplevel, ttk
from typing import Any, Callable

from app_config import Theme
from text.char_libraries import (
    LIBRARY_HANGUL,
    LIBRARY_HANZI,
    LIBRARY_HIRAGANA,
    LIBRARY_KANJI,
    LIBRARY_KATAKANA,
    LIBRARY_LATIN,
)
from text.fonts import (
    SCRIPT_CHINESE,
    SCRIPT_JAPANESE,
    SCRIPT_KOREAN,
    SCRIPT_UNIVERSAL,
)
from text.ui.char_grid_picker import CharGridPicker

_JAPANESE_CHAR_LIBRARIES = (
    (LIBRARY_HIRAGANA, "text_char_library_hiragana"),
    (LIBRARY_KATAKANA, "text_char_library_katakana"),
    (LIBRARY_KANJI, "text_char_library_kanji"),
)

_CHAR_LIBRARY_TABS = (
    (SCRIPT_UNIVERSAL, "text_script_universal", [(LIBRARY_LATIN, "text_char_library_latin", True)]),
    (SCRIPT_JAPANESE, "text_script_japanese", list(_JAPANESE_CHAR_LIBRARIES)),
    (SCRIPT_KOREAN, "text_script_korean", [(LIBRARY_HANGUL, "text_char_library_hangul", True)]),
    (SCRIPT_CHINESE, "text_script_chinese", [(LIBRARY_HANZI, "text_char_library_hanzi", True)]),
)


class CharacterLibraryDialog:
    def __init__(
        self,
        app: Any,
        *,
        on_insert_char: Callable[[str], None],
        target_label: str,
    ) -> None:
        self.app = app
        self.on_insert_char = on_insert_char
        self.target_label = target_label
        self._pickers: list[Any] = []
        self._window = Toplevel(app.root)
        self._window.title(self._tr("text_char_library_title"))
        self._window.geometry("860x620")
        self._window.minsize(720, 520)
        self._window.transient(app.root)
        self._window.configure(bg=Theme.PANEL)
        self._window.protocol("WM_DELETE_WINDOW", self.close)

        header = Frame(self._window, bg=Theme.PANEL)
        header.pack(fill=X, padx=12, pady=(12, 6))
        self._target_label = app._label(header, "", anchor="w", theme_role="muted")
        self._target_label.pack(fill=X)
        self._update_target_label()

        body = Frame(self._window, bg=Theme.PANEL)
        body.pack(fill=BOTH, expand=True, padx=12, pady=(0, 12))
        notebook = ttk.Notebook(body, style="Script.TNotebook")
        notebook.pack(fill=BOTH, expand=True)

        for _script_id, tab_key, spec in _CHAR_LIBRARY_TABS:
            tab_frame = Frame(notebook, bg=Theme.PANEL)
            notebook.add(tab_frame, text=self._tr(tab_key))

            if len(spec) > 1 and spec[0][1] == "text_char_library_hiragana":
                kana_notebook = ttk.Notebook(tab_frame, style="Script.TNotebook")
                kana_notebook.pack(fill=BOTH, expand=True)
                for library_id, label_key in spec:
                    sub_frame = Frame(kana_notebook, bg=Theme.PANEL)
                    kana_notebook.add(sub_frame, text=self._tr(label_key))
                    picker = CharGridPicker(
                        sub_frame,
                        app,
                        library_id,
                        label_key=label_key,
                        on_insert=self.on_insert_char,
                        framed=False,
                    )
                    picker.frame.pack(fill=BOTH, expand=True)
                    picker.ensure_loaded()
                    self._pickers.append(picker)
                continue

            library_id, label_key, framed = spec[0]
            picker = CharGridPicker(
                tab_frame,
                app,
                library_id,
                label_key=label_key,
                on_insert=self.on_insert_char,
                framed=framed,
            )
            picker.frame.pack(fill=BOTH, expand=True)
            picker.ensure_loaded()
            self._pickers.append(picker)

        try:
            app.themes.apply_widget(self._window)
        except Exception:
            pass

    def _tr(self, key: str) -> str:
        from app import tr

        return tr(self.app.lang, key)

    def _update_target_label(self) -> None:
        self._target_label.configure(
            text=self._tr("text_char_library_target").format(target=self.target_label)
        )

    def set_target_label(self, label: str) -> None:
        self.target_label = label
        self._update_target_label()

    def on_language_changed(self) -> None:
        self._window.title(self._tr("text_char_library_title"))
        self._update_target_label()
        for picker in self._pickers:
            picker.on_language_changed()

    def on_theme_changed(self) -> None:
        try:
            self.app.themes.apply_widget(self._window)
        except Exception:
            pass
        for picker in self._pickers:
            picker.on_theme_changed()

    def refresh(self) -> None:
        for picker in self._pickers:
            picker.refresh()

    def focus(self) -> None:
        try:
            self._window.deiconify()
            self._window.lift()
            self._window.focus_force()
        except Exception:
            pass

    def close(self) -> None:
        try:
            self._window.destroy()
        except Exception:
            pass

    @property
    def alive(self) -> bool:
        try:
            return bool(self._window.winfo_exists())
        except Exception:
            return False
