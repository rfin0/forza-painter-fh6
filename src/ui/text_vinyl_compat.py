"""Minimal theme adapter so Text vinyl UI works on upstream 1.8.x without the full theme system."""

from __future__ import annotations

from app_config import Theme


class _PreviewTokens:
    preview_bg = "#202020"
    preview_fg = "#dddddd"
    panel = Theme.PANEL
    panel_alt = Theme.PANEL_ALT
    border = Theme.BORDER
    text = Theme.TEXT
    button_active = Theme.BUTTON_ACTIVE
    button_active_fg = Theme.TEXT


class TextVinylThemeAdapter:
    tokens = _PreviewTokens()

    @staticmethod
    def fg(role: str) -> str:
        mapping = {
            "hint": Theme.MUTED,
            "muted": Theme.MUTED,
            "info": Theme.ACCENT,
            "text": Theme.TEXT,
            "success": "#3fb950",
            "error": Theme.WARN,
        }
        return mapping.get(str(role or "").lower(), Theme.TEXT)

    @staticmethod
    def apply_widget(widget) -> None:
        surface = getattr(widget, "_theme_surface", "panel")
        bg = Theme.PANEL_ALT if surface == "panel_alt" else Theme.PANEL
        try:
            widget.configure(bg=bg)
        except Exception:
            pass
        for child in widget.winfo_children():
            try:
                TextVinylThemeAdapter.apply_widget(child)
            except Exception:
                pass
