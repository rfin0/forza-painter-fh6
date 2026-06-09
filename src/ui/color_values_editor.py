"""Editable/read-only color value panel (hex, RGB, optional alpha, Forza H/S/B)."""

from __future__ import annotations

from typing import Any, Callable

from tkinter import LEFT, X, Button, Entry, Frame, Label, StringVar, ttk

from forza_colors import describe_color, hex_to_rgb

try:
    from ui.saved_color_swatches import apply_themed_palette_surface, render_saved_color_swatches
except ImportError:  # upstream 1.8.x without color picker tools

    def apply_themed_palette_surface(parent, app):  # type: ignore[no-redef]
        return None

    def render_saved_color_swatches(parent, app, colors, on_select):  # type: ignore[no-redef]
        return None


class ColorValuesEditor:
    """Compact color fields matching Tools → Color Picker, with optional alpha."""

    def __init__(
        self,
        parent,
        app: Any,
        *,
        include_alpha: bool = True,
        editable: bool = True,
        show_actions: bool = True,
        show_saved_palette: bool = True,
    ) -> None:
        self.app = app
        self.include_alpha = bool(include_alpha)
        self.editable = bool(editable)
        self.show_actions = bool(show_actions)
        self.show_saved_palette = bool(show_saved_palette)
        self._syncing = False
        self._palette_row: Frame | None = None
        self._palette_listener = self._on_shared_palette_changed

        self.hex_var = StringVar(value="#ffffff")
        self.rgb_r_var = StringVar(value="255")
        self.rgb_g_var = StringVar(value="128")
        self.rgb_b_var = StringVar(value="128")
        self.alpha_var = StringVar(value="255")
        self.hsl_h_var = StringVar()
        self.hsl_s_var = StringVar()
        self.hsl_l_var = StringVar()
        self.hsb_h_var = StringVar()
        self.hsb_s_var = StringVar()
        self.hsb_b_var = StringVar()
        self.forza_h_var = StringVar()
        self.forza_s_var = StringVar()
        self.forza_b_var = StringVar()

        self.frame = Frame(parent)
        self._swatch: Label | None = None
        self._build()

    def _tr(self, key: str) -> str:
        from app import tr

        return tr(self.app.lang, key)

    def _color(self, name: str) -> str:
        import app as app_module

        return getattr(app_module, name)

    def _entry_state(self) -> str:
        return "normal" if self.editable else "readonly"

    def _build(self) -> None:
        app = self.app
        top = Frame(self.frame)
        top.pack(fill=X)

        self._swatch = Label(top, text="", width=6, height=2, bg="#ffffff", relief="solid", bd=1)
        self._swatch.pack(side=LEFT, padx=(0, 10))

        if self.show_actions:
            actions = Frame(top)
            actions.pack(side=LEFT, fill=X, expand=True)
            app._button(actions, "colors_copy_hex", lambda: app._copy_to_clipboard(self.hex_var.get())).pack(
                fill=X, pady=1
            )
            app._button(actions, "colors_copy_forza", self._copy_forza).pack(fill=X, pady=1)
            app._button(actions, "colors_open_bang", self._open_bang).pack(fill=X, pady=1)

        values = ttk.LabelFrame(self.frame, text=self._tr("colors_values"))
        app.translated.append((values, "colors_values", "text"))
        values.pack(fill=X, pady=(8, 0))
        grid = Frame(values)
        grid.pack(fill=X, padx=10, pady=8)

        row = 0
        self._value_row(grid, row, "colors_hex", self.hex_var, width=14, commit=self._commit_hex)
        row += 1
        self._value_row(
            grid,
            row,
            "colors_rgb",
            self.rgb_r_var,
            extra=(self.rgb_g_var, self.rgb_b_var),
            width=6,
            commit=self._commit_rgb,
        )
        row += 1
        if self.include_alpha:
            self._value_row(grid, row, "colors_alpha", self.alpha_var, width=6, commit=self._commit_alpha)
            row += 1
        self._value_row(
            grid, row, "colors_hsl", self.hsl_h_var, extra=(self.hsl_s_var, self.hsl_l_var), readonly=True
        )
        row += 1
        self._value_row(
            grid, row, "colors_hsb", self.hsb_h_var, extra=(self.hsb_s_var, self.hsb_b_var), readonly=True
        )
        row += 1
        self._value_row(
            grid,
            row,
            "colors_forza",
            self.forza_h_var,
            extra=(self.forza_s_var, self.forza_b_var),
            readonly=True,
        )

        if self.show_saved_palette:
            palette_box = Frame(self.frame)
            palette_box.pack(fill=X, pady=(8, 0))
            apply_themed_palette_surface(palette_box, app)
            self.app._label(palette_box, "colors_saved_history", anchor="w", theme_role="muted").pack(fill=X)
            self._palette_row = Frame(palette_box)
            self._palette_row.pack(fill=X, pady=(4, 0))
            apply_themed_palette_surface(self._palette_row, app)

        last = self._initial_rgba()
        self.set_rgba(*last, record=False)
        self._bind_shared_palette()

    def _initial_rgba(self) -> tuple[int, int, int, int]:
        palette = getattr(self.app, "shared_colors", None)
        if palette is not None:
            colors = palette.saved_colors()
            if colors:
                return colors[0]
        try:
            from shared_color_palette import get_last_color

            last = get_last_color()
            if last is not None:
                return last
        except ImportError:
            pass
        return 255, 255, 255, 255

    def _bind_shared_palette(self) -> None:
        palette = getattr(self.app, "shared_colors", None)
        if palette is None:
            return
        palette.subscribe(self._palette_listener)
        self._render_saved_palette()

    def _on_shared_palette_changed(self, rgba: tuple[int, int, int, int], source: str) -> None:
        self._render_saved_palette()
        self.set_rgba(*rgba, record=False)

    def _render_saved_palette(self) -> None:
        if self._palette_row is None:
            return
        apply_themed_palette_surface(self._palette_row, self.app)
        for child in self._palette_row.winfo_children():
            child.destroy()
        palette = getattr(self.app, "shared_colors", None)
        if palette is None:
            return
        render_saved_color_swatches(
            self._palette_row,
            self.app,
            palette.saved_colors(),
            on_select=self._recall_saved_color,
        )

    def _recall_saved_color(self, rgba: tuple[int, int, int, int]) -> None:
        palette = getattr(self.app, "shared_colors", None)
        if palette is not None:
            palette.recall(rgba)
        else:
            self.set_rgba(*rgba, record=False)

    def _record_color(self) -> None:
        palette = getattr(self.app, "shared_colors", None)
        if palette is None:
            return
        r, g, b, a = self.get_rgba()
        palette.push(r, g, b, a, source="push")

    def _value_row(
        self,
        parent,
        row: int,
        label_key: str,
        primary_var: StringVar,
        *,
        extra: tuple[StringVar, ...] = (),
        width: int = 8,
        readonly: bool = False,
        commit: Callable[[], None] | None = None,
    ) -> None:
        self.app._label(parent, label_key, anchor="w").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
        state = "readonly" if readonly or not self.editable else "normal"
        primary = Entry(parent, textvariable=primary_var, width=width, state=state)
        primary.grid(row=row, column=1, sticky="w", pady=3)
        if commit is not None and self.editable:
            primary.bind("<Return>", lambda _e: commit())
            primary.bind("<FocusOut>", lambda _e: commit())
        column = 2
        for var in extra:
            entry = Entry(parent, textvariable=var, width=width, state=state)
            entry.grid(row=row, column=column, sticky="w", padx=(6, 0), pady=3)
            if commit is not None and self.editable and not readonly:
                entry.bind("<Return>", lambda _e: commit())
                entry.bind("<FocusOut>", lambda _e: commit())
            column += 1

    def _copy_forza(self) -> None:
        text = f"{self.forza_h_var.get()}, {self.forza_s_var.get()}, {self.forza_b_var.get()}"
        self.app._copy_to_clipboard(text)

    def _open_bang(self) -> None:
        import webbrowser

        webbrowser.open("https://dxbang.github.io/forza-colors/")

    def _commit_hex(self) -> None:
        if self._syncing:
            return
        rgb = hex_to_rgb(self.hex_var.get())
        if rgb is None:
            return
        alpha = self._read_alpha(default=255)
        self._apply_rgb(rgb.r, rgb.g, rgb.b, alpha, update_hex=False)
        self._record_color()

    def _commit_rgb(self) -> None:
        if self._syncing:
            return
        try:
            r = self._clamp_channel(self.rgb_r_var.get())
            g = self._clamp_channel(self.rgb_g_var.get())
            b = self._clamp_channel(self.rgb_b_var.get())
        except ValueError:
            return
        alpha = self._read_alpha(default=255)
        self._apply_rgb(r, g, b, alpha, update_hex=True)
        self._record_color()

    def _commit_alpha(self) -> None:
        if self._syncing:
            return
        try:
            alpha = self._clamp_channel(self.alpha_var.get())
        except ValueError:
            return
        self._syncing = True
        try:
            self.alpha_var.set(str(alpha))
        finally:
            self._syncing = False

    @staticmethod
    def _clamp_channel(value: str) -> int:
        return max(0, min(255, int(str(value).strip())))

    def _read_alpha(self, *, default: int) -> int:
        if not self.include_alpha:
            return default
        try:
            return self._clamp_channel(self.alpha_var.get())
        except ValueError:
            return default

    def _apply_rgb(self, r: int, g: int, b: int, a: int, *, update_hex: bool) -> None:
        self._syncing = True
        try:
            formats = describe_color(r, g, b)
            if update_hex:
                self.hex_var.set(formats.hex)
            self.rgb_r_var.set(str(formats.rgb.r))
            self.rgb_g_var.set(str(formats.rgb.g))
            self.rgb_b_var.set(str(formats.rgb.b))
            if self.include_alpha:
                self.alpha_var.set(str(self._clamp_channel(str(a))))
            self.hsl_h_var.set(f"{formats.hsl_h:.2f}")
            self.hsl_s_var.set(f"{formats.hsl_s:.2f}")
            self.hsl_l_var.set(f"{formats.hsl_l:.2f}")
            self.hsb_h_var.set(f"{formats.hsb_h:.2f}")
            self.hsb_s_var.set(f"{formats.hsb_s:.2f}")
            self.hsb_b_var.set(f"{formats.hsb_b:.2f}")
            self.forza_h_var.set(f"{formats.forza_h:.2f}")
            self.forza_s_var.set(f"{formats.forza_s:.2f}")
            self.forza_b_var.set(f"{formats.forza_b:.2f}")
            if self._swatch is not None:
                try:
                    self._swatch.config(bg=formats.hex)
                except Exception:
                    pass
        finally:
            self._syncing = False

    def set_rgba(self, r: int, g: int, b: int, a: int = 255, *, record: bool = True) -> None:
        self._apply_rgb(
            self._clamp_channel(str(r)),
            self._clamp_channel(str(g)),
            self._clamp_channel(str(b)),
            self._clamp_channel(str(a)),
            update_hex=True,
        )
        if record:
            self._record_color()

    def get_rgba(self) -> tuple[int, int, int, int]:
        r = self._clamp_channel(self.rgb_r_var.get())
        g = self._clamp_channel(self.rgb_g_var.get())
        b = self._clamp_channel(self.rgb_b_var.get())
        a = self._read_alpha(default=255)
        return r, g, b, a

    def set_from_legacy_text(self, text: str) -> None:
        raw = (text or "").strip()
        if not raw:
            return
        if raw.startswith("#"):
            rgb = hex_to_rgb(raw)
            if rgb is not None:
                self.set_rgba(rgb.r, rgb.g, rgb.b, 255)
            return
        parts = [part.strip() for part in raw.split(",")]
        try:
            values = [int(part) for part in parts]
        except ValueError:
            return
        if len(values) == 3:
            values.append(255)
        if len(values) != 4:
            return
        self.set_rgba(*values[:4])

    def legacy_text(self) -> str:
        r, g, b, a = self.get_rgba()
        return f"{r},{g},{b},{a}"
