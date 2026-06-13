"""Hover help bubbles for Text vinyl option labels."""

from __future__ import annotations

from tkinter import BOTH, LEFT, RIGHT, Y, Button, Canvas, Frame, Label, Scrollbar, Text, TclError, Toplevel

from app_config import Theme

_FADE_IN_STEPS = 10
_FADE_IN_MS = 160
_FADE_OUT_STEPS = 8
_FADE_OUT_MS = 120
_MAX_ALPHA = 0.97


class _HelpBubble:
    _window: Toplevel | None = None
    _anchor = None
    _fade_job: str | None = None
    _hide_job: str | None = None
    _root = None

    @classmethod
    def _cancel_jobs(cls) -> None:
        if cls._root is None:
            cls._fade_job = None
            cls._hide_job = None
            return
        for job in (cls._fade_job, cls._hide_job):
            if job is not None:
                try:
                    cls._root.after_cancel(job)
                except Exception:
                    pass
        cls._fade_job = None
        cls._hide_job = None

    @classmethod
    def _set_alpha(cls, alpha: float) -> None:
        if cls._window is None:
            return
        try:
            cls._window.wm_attributes("-alpha", max(0.0, min(_MAX_ALPHA, alpha)))
        except (TclError, Exception):
            pass

    @classmethod
    def _destroy_window(cls) -> None:
        if cls._window is not None:
            try:
                cls._window.destroy()
            except Exception:
                pass
        cls._window = None
        cls._anchor = None

    @classmethod
    def _position(cls, widget) -> None:
        if cls._window is None:
            return
        cls._window.update_idletasks()
        x = widget.winfo_rootx() + 4
        y = widget.winfo_rooty() + widget.winfo_height() + 6
        screen_h = widget.winfo_screenheight()
        tip_h = cls._window.winfo_height()
        if y + tip_h > screen_h - 40:
            y = widget.winfo_rooty() - tip_h - 6
        cls._window.geometry(f"+{x}+{y}")

    @classmethod
    def _pointer_over(cls, widget) -> bool:
        if widget is None:
            return False
        try:
            px, py = widget.winfo_pointerxy()
            wx = widget.winfo_rootx()
            wy = widget.winfo_rooty()
            return wx <= px <= wx + widget.winfo_width() and wy <= py <= wy + widget.winfo_height()
        except Exception:
            return False

    @classmethod
    def _set_alpha_on(cls, tip: Toplevel, alpha: float) -> None:
        try:
            tip.wm_attributes("-alpha", max(0.0, min(_MAX_ALPHA, alpha)))
        except (TclError, Exception):
            pass

    @classmethod
    def show(cls, widget, app, text: str) -> None:
        cls._root = app.root
        cls._cancel_jobs()
        if not text.strip():
            return
        if cls._window is not None and cls._anchor is widget:
            return

        cls._destroy_window()
        tip = Toplevel(app.root)
        tip.wm_overrideredirect(True)
        tip.wm_attributes("-topmost", True)
        cls._set_alpha_on(tip, 0.0)

        shell = Frame(tip, bg=Theme.BORDER, padx=1, pady=1)
        shell.pack()
        body = Frame(shell, bg=Theme.PANEL_ALT)
        body.pack()
        Label(
            body,
            text=text,
            justify="left",
            wraplength=320,
            bg=Theme.PANEL_ALT,
            fg=Theme.TEXT,
            padx=10,
            pady=8,
            font=("Segoe UI", 9),
        ).pack()

        cls._window = tip
        cls._anchor = widget
        cls._position(widget)
        cls._fade_in()

        def _tip_enter(_event=None) -> None:
            cls._cancel_jobs()

        def _tip_leave(_event=None) -> None:
            cls.schedule_hide(widget, app.root)

        tip.bind("<Enter>", _tip_enter, add="+")
        tip.bind("<Leave>", _tip_leave, add="+")

    @classmethod
    def _fade_in(cls, step: int = 0) -> None:
        if cls._window is None or cls._root is None:
            return
        alpha = ((step + 1) / _FADE_IN_STEPS) * _MAX_ALPHA
        cls._set_alpha(alpha)
        if step + 1 < _FADE_IN_STEPS:
            delay = max(1, _FADE_IN_MS // _FADE_IN_STEPS)
            cls._fade_job = cls._root.after(delay, lambda: cls._fade_in(step + 1))

    @classmethod
    def _fade_out(cls, step: int = 0) -> None:
        if cls._window is None or cls._root is None:
            return
        remaining = _FADE_OUT_STEPS - step
        alpha = (remaining / _FADE_OUT_STEPS) * _MAX_ALPHA
        cls._set_alpha(alpha)
        if step + 1 < _FADE_OUT_STEPS:
            delay = max(1, _FADE_OUT_MS // _FADE_OUT_STEPS)
            cls._fade_job = cls._root.after(delay, lambda: cls._fade_out(step + 1))
            return
        cls._destroy_window()

    @classmethod
    def schedule_hide(cls, widget, root, delay_ms: int = 90) -> None:
        cls._root = root
        if cls._hide_job is not None:
            try:
                root.after_cancel(cls._hide_job)
            except Exception:
                pass
        cls._hide_job = root.after(delay_ms, lambda: cls._try_hide(widget))

    @classmethod
    def _try_hide(cls, widget) -> None:
        cls._hide_job = None
        if cls._anchor is not widget:
            return
        if cls._pointer_over(widget) or cls._pointer_over(cls._window):
            return
        cls.hide()

    @classmethod
    def hide(cls) -> None:
        if cls._window is None:
            return
        cls._cancel_jobs()
        cls._fade_out()


def bind_hover_help(widget, app, help_key: str) -> None:
    """Show translated help in a fading bubble while the pointer is over *widget*."""

    def _enter(_event=None) -> None:
        from app import tr

        _HelpBubble.show(widget, app, tr(app.lang, help_key))

    def _leave(_event=None) -> None:
        _HelpBubble.schedule_hide(widget, app.root)

    widget.bind("<Enter>", _enter, add="+")
    widget.bind("<Leave>", _leave, add="+")


def create_help_button(parent, app, help_key: str, *, padx=(6, 0)) -> Button:
    btn = Button(
        parent,
        text="?",
        width=2,
        bg=Theme.PANEL_ALT,
        fg=Theme.MUTED,
        activebackground=Theme.BUTTON,
        activeforeground=Theme.TEXT,
        relief="flat",
        font=("Segoe UI", 9, "bold"),
        cursor="question_arrow",
    )
    bind_hover_help(btn, app, help_key)
    if padx:
        btn.pack(side=LEFT, padx=padx)
    return btn


def pack_label_with_help(
    parent,
    app,
    label_key: str,
    help_key: str,
    *,
    grid_row: int | None = None,
    grid_column: int = 0,
    sticky: str = "w",
    padx=(0, 8),
    pady=0,
    columnspan: int = 1,
) -> Frame:
    """Pack or grid a translated label with a '?' hover-help button."""
    row = Frame(parent, bg=app._parent_bg(parent))
    if grid_row is not None:
        row.grid(row=grid_row, column=grid_column, columnspan=columnspan, sticky=sticky, padx=padx, pady=pady)
    else:
        row.pack(side=LEFT, fill="x", expand=True)

    label = app._label(row, label_key, anchor="w")
    label.pack(side=LEFT)
    create_help_button(row, app, help_key, padx=(6, 0))
    return row


def themed_entry(parent, app, **kwargs):
    from tkinter import Entry

    entry = Entry(
        parent,
        bg=Theme.INPUT,
        fg=Theme.TEXT,
        insertbackground=Theme.TEXT,
        relief="flat",
        highlightthickness=1,
        highlightbackground=Theme.BORDER,
        highlightcolor=Theme.ACCENT,
        **kwargs,
    )
    return entry


def themed_text(parent, app, *, height: int = 8, wrap: str = "word", undo: bool = True, **kwargs):
    """Multiline text editor with vertical scrollbar, matching app input theme."""
    shell = Frame(parent, bg=Theme.PANEL)
    scrollbar = Scrollbar(shell, orient="vertical")
    text_widget = Text(
        shell,
        height=height,
        wrap=wrap,
        undo=undo,
        bg=Theme.INPUT,
        fg=Theme.TEXT,
        insertbackground=Theme.TEXT,
        selectbackground=Theme.ACCENT_DARK,
        selectforeground=Theme.TEXT,
        relief="flat",
        highlightthickness=1,
        highlightbackground=Theme.BORDER,
        highlightcolor=Theme.ACCENT,
        padx=8,
        pady=6,
        **kwargs,
    )
    text_widget.configure(yscrollcommand=scrollbar.set)
    scrollbar.configure(command=text_widget.yview)
    text_widget.pack(side=LEFT, fill=BOTH, expand=True)
    scrollbar.pack(side=RIGHT, fill=Y)
    return shell, text_widget


_WHEEL_SEQUENCES = ("<MouseWheel>", "<Button-4>", "<Button-5>")


def _scroll_amount_from_wheel_event(event) -> int:
    if getattr(event, "num", None) == 4:
        return -1
    if getattr(event, "num", None) == 5:
        return 1
    return int(-1 * (event.delta / 120))


def _scroll_ancestor_canvas(widget, event) -> None:
    current = widget
    while current is not None:
        master = getattr(current, "master", None)
        if isinstance(master, Canvas):
            try:
                if master.cget("yscrollcommand"):
                    master.yview_scroll(_scroll_amount_from_wheel_event(event), "units")
            except TclError:
                pass
            return
        current = master


def guard_combobox_against_mousewheel(combobox) -> None:
    """Stop the scroll wheel from changing readonly combobox values; scroll the page instead."""

    def _on_wheel(event):
        _scroll_ancestor_canvas(combobox, event)
        return "break"

    def _bind_wheel_targets(widget) -> None:
        for sequence in _WHEEL_SEQUENCES:
            widget.bind(sequence, _on_wheel)

    def _bind_children(_event=None) -> None:
        _bind_wheel_targets(combobox)
        for child in combobox.winfo_children():
            _bind_wheel_targets(child)

    combobox.bind("<Map>", _bind_children, add="+")
    _bind_children()
