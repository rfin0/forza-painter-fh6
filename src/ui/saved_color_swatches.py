"""Render clickable saved-color swatches shared by Bang color panels."""

from __future__ import annotations

from typing import Any, Callable

from tkinter import LEFT, Frame, Label

from forza_colors import describe_color


def render_saved_color_swatches(
    parent: Frame,
    app: Any,
    colors: list[tuple[int, int, int, int]],
    *,
    on_select: Callable[[tuple[int, int, int, int]], None],
) -> Frame | None:
    surface = _surface_bg(app, parent)
    border = _border_color(app)
    row = Frame(parent, bg=surface, highlightthickness=0, bd=0)
    for rgba in colors:
        r, g, b, _a = rgba
        hex_value = describe_color(r, g, b).hex
        try:
            swatch = Label(
                row,
                text="",
                width=3,
                height=1,
                bg=hex_value,
                relief="solid",
                bd=1,
                highlightthickness=1,
                highlightbackground=border,
                highlightcolor=border,
                cursor="hand2",
            )
            swatch.pack(side=LEFT, padx=(0, 4))
            swatch.bind("<Button-1>", lambda _event, value=rgba: on_select(value))
        except Exception:
            continue
    if not row.winfo_children():
        row.destroy()
        return None
    row.pack(anchor="w")
    return row


def apply_themed_palette_surface(frame: Frame, app: Any) -> None:
    """Match unthemed host frames to the active palette."""
    surface = _surface_bg(app, frame)
    try:
        frame.configure(bg=surface, highlightthickness=0, bd=0)
    except Exception:
        pass


def _surface_bg(app: Any, parent: Frame) -> str:
    tokens = getattr(getattr(app, "themes", None), "tokens", None)
    fallback = getattr(tokens, "panel", "#2b2b2b") if tokens is not None else "#2b2b2b"
    try:
        if hasattr(app, "_parent_bg"):
            bg = app._parent_bg(parent)
            if bg:
                return bg
    except Exception:
        pass
    return fallback


def _border_color(app: Any) -> str:
    tokens = getattr(getattr(app, "themes", None), "tokens", None)
    if tokens is not None:
        return tokens.border
    import app as app_module

    return getattr(app_module, "COLOR_BORDER", "#666666")
