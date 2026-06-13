"""Self-contained Text vinyl tab: UI, state, previews, and generation workers."""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any

from tkinter import (
    BOTH,
    END,
    HORIZONTAL,
    LEFT,
    RIGHT,
    X,
    Button,
    Checkbutton,
    Entry,
    Frame,
    Label,
    Listbox,
    PhotoImage,
    StringVar,
    Text,
    filedialog,
    ttk,
)

from app_paths import ROOT
from ui_preferences import load_ui_preferences, save_ui_preferences
from asset_workspace import TEXT_VINYL_WORKSPACE_ROOT, text_vinyl_workspace, write_manifest, workspace_source_file
from text.mandarin_chars import text_contains_hangul
from text.layout import WRITING_MODE_HORIZONTAL_LTR
from text.fonts import (
    SCRIPT_CHINESE,
    SCRIPT_JAPANESE,
    SCRIPT_KOREAN,
    SCRIPT_UNIVERSAL,
    TEXT_SCRIPT_IDS,
    DiscoveredFont,
    FontRecommendation,
    clear_font_discovery_cache,
    coverage_message_key,
    default_font_path_for_script,
    default_fonts_for_script,
    discover_fonts_for_script_cached,
    filter_font_labels,
    format_missing_chars,
    open_system_font_settings,
    recommend_font_for_text,
    validate_text_coverage,
)
from text.layer_masks import TextMaskOptions, summarize_payload_layers
from text.benchmark_probes import random_benchmark_text
from app_config import Theme
from text.geometry import (
    TRACE_METHOD_BARS_FULL,
    TRACE_METHOD_BARS_SKELETON,
    TRACE_METHOD_GRID,
    build_typecode_from_text_image,
    build_typecode_from_text_with_options,
    coerce_text_shape_mode_for_ui,
    estimate_layer_count,
    estimate_typed_text_layers,
    normalize_text_shape_mode,
    normalize_text_trace_method,
    normalize_trace_cell_size,
    TEXT_SHAPE_MODE_UI_CHOICES,
    TEXT_TRACE_METHOD_UI_CHOICES,
    trace_method_uses_grid,
    write_text_design_json,
)
from text.presets import (
    CJK_DEFAULT_PRESET_ID,
    DEFAULT_MAX_DRAWABLE_LAYERS,
    UI_PRESET_ORDER,
    get_preset,
    normalize_preset_id,
)
from text.ui.character_library_dialog import CharacterLibraryDialog
from text.ui.color_values_editor import ColorValuesEditor
from text.ui.help_hint import create_help_button, guard_combobox_against_mousewheel, pack_label_with_help, themed_entry, themed_text

FONT_COMBO_DISPLAY_FONT = ("Consolas", 10)


class TextVinylWorkspace:
    """Text vinyl tool module hosted by App (shared queue, theme, import bridge)."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.json_files: list[Path] = []
        self._reference_preview_path: Path | None = None
        self._json_preview_path: Path | None = None
        self._reference_preview_job = None
        self._json_preview_job = None
        self._coverage_job = None
        self._coverage_generation = 0
        self._last_font_recommendation: FontRecommendation | None = None
        self._layer_estimate_signature: tuple | None = None
        self._fonts_deep_scanned: set[str] = set()
        self.text_panels = {
            script: {
                "input_widget": None,
                "font_choice": StringVar(),
                "font_path": StringVar(),
                "font_search": StringVar(),
                "discovered": (),
                "font_by_label": {},
                "widgets": {},
            }
            for script in TEXT_SCRIPT_IDS
        }
        self._char_library_dialog: CharacterLibraryDialog | None = None
        self._font_preview_job = None
        self._font_preview_image: PhotoImage | None = None
        self.text_font_size = StringVar(value="120")
        self.text_cell_size = StringVar(value="1")
        self.text_shape_mode = StringVar(value="rectangles")
        self.text_trace_method = StringVar(value=TRACE_METHOD_GRID)
        self.text_preset_id = StringVar(value="custom")
        self.text_show_advanced = StringVar(value="0")
        self.text_show_color = StringVar(value="0")
        self.text_fit_layer_budget = StringVar(value="0")
        self.text_extra_shapes = StringVar(value="0")
        self.text_include_boundary_masks = StringVar(value="0")
        self.text_include_polish_masks = StringVar(value="0")
        self.text_max_drawable_layers = StringVar(value=str(DEFAULT_MAX_DRAWABLE_LAYERS))
        self.text_layer_estimate = StringVar(value="")
        self._layer_estimate_job = None
        self._font_refresh_buttons: list[Button] = []
        self._fonts_scanning = False
        self._applying_preset = False
        self.text_image_path = StringVar()
        self._color_editor: ColorValuesEditor | None = None
        self.text_invert = StringVar(value="0")
        self.text_script_notebook: ttk.Notebook | None = None
        self.text_json_list: Listbox | None = None
        self.text_reference_preview_label: Label | None = None
        self.text_json_preview_label: Label | None = None
        self.text_shape_combo: ttk.Combobox | None = None
        self.text_trace_method_combo: ttk.Combobox | None = None
        self.text_template_hint_label: Label | None = None
        self._import_shape_notice_frame: Frame | None = None
        self._import_shape_notice_body: Frame | None = None
        self._import_shape_notice_label: Label | None = None
        self._import_shape_notice_restore: Button | None = None
        self.text_layer_stack_label: Label | None = None
        self.text_coverage_label: Label | None = None
        self._coverage_apply_button: Button | None = None
        self._trace_method_label_to_mode: dict[str, str] = {}
        self._trace_method_mode_to_label: dict[str, str] = {}
        self._shape_mode_label_to_mode: dict[str, str] = {}
        self._shape_mode_mode_to_label: dict[str, str] = {}
        self._preset_label_to_id: dict[str, str] = {}
        self._preset_id_to_label: dict[str, str] = {}

    @property
    def lang(self) -> str:
        return self.app.lang

    @property
    def root(self):
        return self.app.root

    @property
    def closed(self) -> bool:
        return self.app.closed

    @property
    def queue(self):
        return self.app.queue

    def _tr(self, key: str) -> str:
        from app import tr

        return tr(self.lang, key)

    def _color(self, name: str) -> str:
        from app_config import Theme

        mapping = {
            "COLOR_INFO": Theme.ACCENT,
        }
        return mapping.get(name, Theme.TEXT)

    def _preview_renderers(self):
        from app import render_geometry_json, render_source_image

        return render_source_image, render_geometry_json

    def build(self, tab: Frame) -> None:
        app = self.app
        paned = app._create_paned(tab, orient=HORIZONTAL, layout_key="text_horizontal", padx=10, pady=10)
        left_outer = Frame(paned)
        right = Frame(paned)
        paned.add(left_outer, weight=3)
        paned.add(right, weight=2)

        left, action_host = app._prepare_sticky_column(left_outer)
        header_row = Frame(left, bg=app._parent_bg(left))
        header_row.pack(fill="x", pady=(0, 8))
        tab_hint = app._label(header_row, "text_tab_hint", anchor="w", justify="left", theme_role="hint")
        tab_hint.pack(side=LEFT, fill="x", expand=True, anchor="w")
        self._build_import_shape_notice(header_row)
        app._bind_wraplength(tab_hint, header_row, padding=8)

        self.text_script_notebook = ttk.Notebook(left, style="Script.TNotebook")
        self.text_script_notebook.pack(fill=BOTH, expand=True, pady=(0, 8))
        self.text_script_notebook.bind("<<NotebookTabChanged>>", lambda _event: self._on_script_tab_changed())

        for script in TEXT_SCRIPT_IDS:
            panel_frame = Frame(self.text_script_notebook, bg=Theme.PANEL)
            self.text_script_notebook.add(panel_frame, text=self._tr(self._script_tab_key(script)))
            self._build_script_panel(panel_frame, script)

        self._build_options_panel(left)

        outputs_box = ttk.LabelFrame(left, text=self._tr("text_outputs"))
        app.translated.append((outputs_box, "text_outputs", "text"))
        outputs_box.pack(fill="x", pady=(0, 8))
        outputs_hint = app._label(outputs_box, "text_outputs_hint", anchor="w", justify="left", theme_role="hint")
        outputs_hint.pack(fill="x", padx=10, pady=(8, 4))
        app._bind_wraplength(outputs_hint, outputs_box)
        outputs_row = Frame(outputs_box)
        outputs_row.pack(fill="x", padx=10, pady=(0, 4))
        app._button(outputs_row, "text_add_json", self.add_json).pack(side=LEFT)
        app._button(outputs_row, "text_remove_json", self.remove_selected_json).pack(side=LEFT, padx=8)
        app._button(outputs_row, "text_send_to_import", self.send_to_import).pack(side=RIGHT)
        list_body = Frame(outputs_box)
        list_body.pack(fill="x", padx=10, pady=(0, 10))
        self.text_json_list = Listbox(list_body, height=5)
        self.text_json_list.pack(fill="x", expand=True)
        self.text_json_list.bind("<<ListboxSelect>>", self._preview_selected_json)
        self.text_layer_stack_label = app._label(
            outputs_box, "text_layer_stack_no_masks", anchor="w", theme_role="muted", justify="left"
        )
        self.text_layer_stack_label.pack(fill="x", padx=10, pady=(0, 8))
        app._bind_wraplength(self.text_layer_stack_label, outputs_box, padding=20)
        self.text_layer_stack_label.pack_forget()

        action_box = ttk.LabelFrame(action_host, text=self._tr("text_generate_action"))
        app.translated.append((action_box, "text_generate_action", "text"))
        action_box.pack(fill="x")
        action_row = Frame(action_box)
        action_row.pack(fill="x", padx=10, pady=(0, 12))
        app._button(
            action_row,
            "text_generate_typed",
            self.start_generate_typed,
            font=("Segoe UI", 12, "bold"),
            height=2,
        ).pack(side=LEFT, fill="x", expand=True)
        app._button(action_row, "text_open_vinyl_folder", self.open_output_folder).pack(side=LEFT, padx=(8, 0))

        ref_box = ttk.LabelFrame(right, text=self._tr("text_reference_image"))
        app.translated.append((ref_box, "text_reference_image", "text"))
        ref_box.pack(fill=BOTH, expand=True, pady=(0, 8))
        ref_row = Frame(ref_box)
        ref_row.pack(fill="x", padx=10, pady=8)
        Entry(ref_row, textvariable=self.text_image_path).pack(side=LEFT, fill="x", expand=True)
        app._button(ref_row, "text_browse_image", self.browse_reference_image).pack(side=LEFT, padx=8)
        ref_actions = Frame(ref_box)
        ref_actions.pack(fill="x", padx=10, pady=(0, 6))
        invert_toggle = Checkbutton(
            ref_actions,
            text=self._tr("text_invert"),
            variable=self.text_invert,
            onvalue="1",
            offvalue="0",
        )
        invert_toggle.pack(side=LEFT)
        app.translated.append((invert_toggle, "text_invert", "text"))
        app._button(ref_actions, "text_trace_image", self.start_trace).pack(side=LEFT)
        app._label(ref_box, "text_reference_preview", anchor="w", font=("Segoe UI", 10, "bold")).pack(fill="x", padx=10)
        preview_t = app.themes.tokens
        self.text_reference_preview_label = Label(
            ref_box,
            text=self._tr("preview_hint"),
            bg=preview_t.preview_bg,
            fg=preview_t.preview_fg,
        )
        self.text_reference_preview_label.pack(fill=BOTH, expand=True, padx=10, pady=(4, 10))
        self.text_reference_preview_label.bind("<Configure>", lambda _e: self._schedule_reference_preview_refresh())

        json_box = ttk.LabelFrame(right, text=self._tr("text_json_preview"))
        app.translated.append((json_box, "text_json_preview", "text"))
        json_box.pack(fill=BOTH, expand=True)
        self.text_json_preview_label = Label(
            json_box,
            text=self._tr("preview_hint"),
            bg=preview_t.preview_bg,
            fg=preview_t.preview_fg,
        )
        self.text_json_preview_label.pack(fill=BOTH, expand=True, padx=10, pady=10)
        self.text_json_preview_label.bind("<Configure>", lambda _e: self._schedule_json_preview_refresh())

        self.text_image_path.trace_add("write", lambda *_args: self._schedule_reference_preview_refresh())
        self._on_script_tab_changed()

    def _build_options_panel(self, parent: Frame) -> None:
        app = self.app
        shared = ttk.LabelFrame(parent, text=self._tr("text_options"))
        app.translated.append((shared, "text_options", "text"))
        shared.pack(fill="x", pady=(0, 8))
        opts = Frame(shared, bg=Theme.PANEL)
        opts.pack(fill="x", padx=10, pady=8)

        pack_label_with_help(
            opts,
            app,
            "text_preset",
            "text_help_preset",
            grid_row=0,
            grid_column=0,
            sticky="w",
        )
        self._preset_label_to_id: dict[str, str] = {}
        self._preset_id_to_label: dict[str, str] = {}
        self.text_preset_combo = ttk.Combobox(opts, state="readonly", width=28)
        self._refresh_preset_combo()
        self.text_preset_combo.grid(row=0, column=1, columnspan=3, sticky="ew", pady=(0, 0))
        self.text_preset_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_preset_selected())
        guard_combobox_against_mousewheel(self.text_preset_combo)

        advanced_toggle_row = Frame(opts, bg=Theme.PANEL)
        advanced_toggle_row.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self._advanced_toggle = Checkbutton(
            advanced_toggle_row,
            text=self._tr("text_show_advanced"),
            variable=self.text_show_advanced,
            onvalue="1",
            offvalue="0",
            command=self._on_show_advanced_toggle,
            bg=Theme.PANEL,
            fg=Theme.TEXT,
            selectcolor=Theme.INPUT,
            activebackground=Theme.PANEL,
            activeforeground=Theme.TEXT,
        )
        self._advanced_toggle.pack(side=LEFT)
        app.translated.append((self._advanced_toggle, "text_show_advanced", "text"))

        self._advanced_frame = Frame(opts, bg=Theme.PANEL)
        self._advanced_frame.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(6, 0))

        pack_label_with_help(
            self._advanced_frame,
            app,
            "text_font_size",
            "text_help_font_size",
            grid_row=0,
            grid_column=0,
            sticky="w",
        )
        themed_entry(self._advanced_frame, app, textvariable=self.text_font_size, width=8).grid(
            row=0, column=1, sticky="w"
        )
        pack_label_with_help(
            self._advanced_frame,
            app,
            "text_cell_size",
            "text_help_cell_size",
            grid_row=0,
            grid_column=2,
            sticky="w",
            padx=(16, 8),
        )
        self._trace_cell_entry = themed_entry(self._advanced_frame, app, textvariable=self.text_cell_size, width=8)
        self._trace_cell_entry.grid(row=0, column=3, sticky="w")

        cell_hint = app._label(self._advanced_frame, "text_cell_hint", anchor="w", theme_role="muted")
        cell_hint.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        app._bind_wraplength(cell_hint, self._advanced_frame, padding=8)
        self._cell_hint_label = cell_hint

        pack_label_with_help(
            self._advanced_frame,
            app,
            "text_trace_method",
            "text_help_trace_method",
            grid_row=2,
            grid_column=0,
            sticky="w",
            pady=(6, 0),
        )
        self.text_trace_method_combo = ttk.Combobox(
            self._advanced_frame,
            textvariable=self.text_trace_method,
            width=28,
            state="readonly",
        )
        self._trace_method_label_to_mode: dict[str, str] = {}
        self._trace_method_mode_to_label: dict[str, str] = {}
        self._refresh_trace_method_combo()
        self.text_trace_method_combo.grid(row=2, column=1, columnspan=3, sticky="w", pady=(6, 0))
        self.text_trace_method_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_trace_method_changed())
        guard_combobox_against_mousewheel(self.text_trace_method_combo)

        self._trace_method_hint_label = app._label(
            self._advanced_frame, "text_trace_method_hint_grid", anchor="w", theme_role="muted"
        )
        self._trace_method_hint_label.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        app._bind_wraplength(self._trace_method_hint_label, self._advanced_frame, padding=8)

        pack_label_with_help(
            self._advanced_frame,
            app,
            "text_shape_primitive",
            "text_help_shape_primitive",
            grid_row=4,
            grid_column=0,
            sticky="w",
            pady=(6, 0),
        )
        self.text_shape_combo = ttk.Combobox(
            self._advanced_frame,
            textvariable=self.text_shape_mode,
            width=18,
            state="readonly",
        )
        self._shape_mode_label_to_mode: dict[str, str] = {}
        self._shape_mode_mode_to_label: dict[str, str] = {}
        self._refresh_shape_mode_combo()
        self.text_shape_combo.grid(row=4, column=1, columnspan=3, sticky="w", pady=(6, 0))
        self.text_shape_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_generation_option_changed())
        guard_combobox_against_mousewheel(self.text_shape_combo)

        self._trace_active_summary_label = app._label(
            self._advanced_frame, "text_trace_active_summary_grid", anchor="w", theme_role="muted"
        )
        self._trace_active_summary_label.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        app._bind_wraplength(self._trace_active_summary_label, self._advanced_frame, padding=8)

        budget_row = Frame(self._advanced_frame, bg=Theme.PANEL)
        budget_row.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        self._fit_budget_toggle = Checkbutton(
            budget_row,
            text=self._tr("text_fit_layer_budget"),
            variable=self.text_fit_layer_budget,
            onvalue="1",
            offvalue="0",
            command=self._on_generation_option_changed,
            bg=Theme.PANEL,
            fg=Theme.TEXT,
            selectcolor=Theme.INPUT,
            activebackground=Theme.PANEL,
            activeforeground=Theme.TEXT,
        )
        self._fit_budget_toggle.pack(side=LEFT)
        app.translated.append((self._fit_budget_toggle, "text_fit_layer_budget", "text"))
        create_help_button(budget_row, app, "text_help_fit_budget", padx=(4, 0))
        app._label(budget_row, "text_max_drawable_layers").pack(side=LEFT, padx=(12, 4))
        themed_entry(budget_row, app, textvariable=self.text_max_drawable_layers, width=8).pack(side=LEFT)

        extra_row = Frame(self._advanced_frame, bg=Theme.PANEL)
        extra_row.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        self._extra_shapes_toggle = Checkbutton(
            extra_row,
            text=self._tr("text_extra_shapes"),
            variable=self.text_extra_shapes,
            onvalue="1",
            offvalue="0",
            command=self._on_extra_shapes_toggle,
            bg=Theme.PANEL,
            fg=Theme.TEXT,
            selectcolor=Theme.INPUT,
            activebackground=Theme.PANEL,
            activeforeground=Theme.TEXT,
        )
        self._extra_shapes_toggle.pack(side=LEFT)
        app.translated.append((self._extra_shapes_toggle, "text_extra_shapes", "text"))
        create_help_button(extra_row, app, "text_help_extra_shapes", padx=(6, 0))

        mask_row = Frame(self._advanced_frame, bg=Theme.PANEL)
        mask_row.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        self._boundary_masks_toggle = Checkbutton(
            mask_row,
            text=self._tr("text_boundary_masks"),
            variable=self.text_include_boundary_masks,
            onvalue="1",
            offvalue="0",
            command=self._on_generation_option_changed,
            bg=Theme.PANEL,
            fg=Theme.TEXT,
            selectcolor=Theme.INPUT,
            activebackground=Theme.PANEL,
            activeforeground=Theme.TEXT,
        )
        self._boundary_masks_toggle.pack(side=LEFT)
        app.translated.append((self._boundary_masks_toggle, "text_boundary_masks", "text"))
        create_help_button(mask_row, app, "text_help_boundary_masks", padx=(4, 12))
        self._polish_masks_toggle = Checkbutton(
            mask_row,
            text=self._tr("text_polish_masks"),
            variable=self.text_include_polish_masks,
            onvalue="1",
            offvalue="0",
            command=self._on_generation_option_changed,
            bg=Theme.PANEL,
            fg=Theme.TEXT,
            selectcolor=Theme.INPUT,
            activebackground=Theme.PANEL,
            activeforeground=Theme.TEXT,
        )
        self._polish_masks_toggle.pack(side=LEFT)
        app.translated.append((self._polish_masks_toggle, "text_polish_masks", "text"))
        create_help_button(mask_row, app, "text_help_polish_masks", padx=(4, 0))

        self._custom_preset_note = app._label(
            opts, "text_custom_preset_note", anchor="w", theme_role="muted"
        )
        self._custom_preset_note.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        app._bind_wraplength(self._custom_preset_note, opts, padding=8)

        self.text_layer_estimate_label = app._label(
            opts, "text_layer_estimate_idle", anchor="w", theme_role="info", justify="left"
        )
        self.text_layer_estimate_label.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        app._bind_wraplength(self.text_layer_estimate_label, opts, padding=8)

        self.text_template_hint_label = Label(
            opts,
            text="",
            anchor="w",
            bg=app._parent_bg(opts),
            fg=app.themes.fg("info"),
        )
        self.text_template_hint_label.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        app._bind_wraplength(self.text_template_hint_label, opts, padding=8)
        self.update_shape_hint()

        color_section = Frame(opts, bg=Theme.PANEL)
        color_section.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        color_header = Frame(color_section, bg=Theme.PANEL)
        color_header.pack(fill="x")
        pack_label_with_help(color_header, app, "text_color", "text_help_color")
        self._color_toggle = Checkbutton(
            color_header,
            text=self._tr("text_show_color"),
            variable=self.text_show_color,
            onvalue="1",
            offvalue="0",
            command=self._on_show_color_toggle,
            bg=Theme.PANEL,
            fg=Theme.TEXT,
            selectcolor=Theme.INPUT,
            activebackground=Theme.PANEL,
            activeforeground=Theme.TEXT,
        )
        self._color_toggle.pack(side=RIGHT)
        app.translated.append((self._color_toggle, "text_show_color", "text"))
        self._color_editor_host = Frame(color_section, bg=Theme.PANEL)
        self._color_editor = ColorValuesEditor(
            self._color_editor_host, app, include_alpha=True, editable=True, show_saved_palette=False
        )
        text_color_hint = app._label(color_section, "text_color_hint", anchor="w", theme_role="muted")
        app._bind_wraplength(text_color_hint, color_section, padding=8)
        self._color_hint_label = text_color_hint

        coverage_row = Frame(opts, bg=Theme.PANEL)
        coverage_row.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        coverage_row.columnconfigure(0, weight=1)
        self.text_coverage_label = app._label(
            coverage_row, "text_coverage_ok", anchor="w", theme_role="text", justify="left"
        )
        self.text_coverage_label.grid(row=0, column=0, sticky="ew")
        self._coverage_apply_button = app._button(
            coverage_row,
            "text_apply_recommended_font",
            self.apply_recommended_font,
        )
        self._coverage_apply_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        opts.columnconfigure(1, weight=1)
        app._bind_wraplength(self.text_coverage_label, opts, padding=8)
        self._sync_advanced_visibility()
        self._sync_color_visibility()
        self._sync_custom_preset_note()
        self._sync_trace_controls()
        self._wire_generation_option_traces()
        self._schedule_layer_estimate()

    def _on_show_advanced_toggle(self) -> None:
        self._sync_advanced_visibility()

    def _on_show_color_toggle(self) -> None:
        self._sync_color_visibility()

    def _sync_advanced_visibility(self) -> None:
        if not hasattr(self, "_advanced_frame"):
            return
        if self.text_show_advanced.get() == "1":
            self._advanced_frame.grid()
        else:
            self._advanced_frame.grid_remove()

    def _sync_color_visibility(self) -> None:
        if self._color_editor is None:
            return
        if self.text_show_color.get() == "1":
            self._color_editor_host.pack(fill=X, pady=(4, 0))
            self._color_editor.frame.pack(fill=X)
            self._color_hint_label.pack(fill=X, pady=(4, 0))
        else:
            self._color_editor.frame.pack_forget()
            self._color_editor_host.pack_forget()
            self._color_hint_label.pack_forget()

    def _sync_custom_preset_note(self) -> None:
        if not hasattr(self, "_custom_preset_note"):
            return
        if self.text_preset_id.get() == "custom" and self.text_show_advanced.get() != "1":
            self._custom_preset_note.grid()
        else:
            self._custom_preset_note.grid_remove()

    def _wire_generation_option_traces(self) -> None:
        for var in (
            self.text_font_size,
            self.text_cell_size,
            self.text_trace_method,
            self.text_shape_mode,
            self.text_fit_layer_budget,
            self.text_extra_shapes,
            self.text_max_drawable_layers,
        ):
            var.trace_add("write", lambda *_args: self._on_generation_option_changed())

    def _refresh_preset_combo(self) -> None:
        self._preset_label_to_id.clear()
        self._preset_id_to_label.clear()
        labels: list[str] = []
        for preset_id in UI_PRESET_ORDER:
            label = self._tr(get_preset(preset_id).label_key)
            labels.append(label)
            self._preset_label_to_id[label] = preset_id
            self._preset_id_to_label[preset_id] = label
        if self.text_preset_combo is not None:
            self.text_preset_combo.configure(values=labels)
            current = normalize_preset_id(self.text_preset_id.get())
            self.text_preset_id.set(current)
            self.text_preset_combo.set(self._preset_id_to_label.get(current, labels[0]))

    def _apply_preset(self, preset_id: str, *, update_combo: bool = True) -> None:
        preset_id = normalize_preset_id(preset_id)
        preset = get_preset(preset_id)
        self._applying_preset = True
        try:
            self.text_preset_id.set(preset_id)
            if update_combo and self.text_preset_combo is not None:
                label = self._preset_id_to_label.get(preset_id)
                if label:
                    self.text_preset_combo.set(label)
            if preset.id != "custom":
                self.text_trace_method.set(TRACE_METHOD_GRID)
                self._refresh_trace_method_combo()
                self.text_shape_mode.set(preset.shape_mode)
                self._refresh_shape_mode_combo()
                self.text_cell_size.set(str(preset.cell_size))
                self.text_fit_layer_budget.set("1" if preset.fit_layer_budget else "0")
                self.text_extra_shapes.set("1" if preset.extra_shapes else "0")
                if preset.max_drawable_layers is not None:
                    self.text_max_drawable_layers.set(str(preset.max_drawable_layers))
            if preset_id == "custom":
                self.text_show_advanced.set("1")
            self._sync_advanced_visibility()
            self._sync_custom_preset_note()
            self._sync_trace_controls()
            self.update_shape_hint()
            self._schedule_layer_estimate()
        finally:
            self._applying_preset = False

    def _on_preset_selected(self) -> None:
        if self.text_preset_combo is None:
            return
        label = self.text_preset_combo.get().strip()
        preset_id = self._preset_label_to_id.get(label, "custom")
        self._apply_preset(preset_id, update_combo=False)

    def _on_extra_shapes_toggle(self) -> None:
        if self.text_extra_shapes.get() == "1":
            self.text_trace_method.set(TRACE_METHOD_GRID)
            self._refresh_trace_method_combo()
            if self.text_preset_id.get() == "custom" and self.text_preset_combo is not None:
                label = self._preset_id_to_label.get("smooth_cjk_extra")
                if label:
                    self.text_preset_combo.set(label)
                    self.text_preset_id.set("smooth_cjk_extra")
        self._sync_trace_controls()
        self._on_generation_option_changed()

    def _on_trace_method_changed(self) -> None:
        method = self._resolve_trace_method()
        if method in (TRACE_METHOD_BARS_FULL, TRACE_METHOD_BARS_SKELETON) and self.text_extra_shapes.get() == "1":
            self.text_extra_shapes.set("0")
        self._sync_trace_controls()
        self._on_generation_option_changed()

    def _sync_trace_controls(self) -> None:
        extra_on = self.text_extra_shapes.get() == "1"
        method = self._resolve_trace_method()
        uses_grid = trace_method_uses_grid(method) and not extra_on
        uses_bars = method in (TRACE_METHOD_BARS_FULL, TRACE_METHOD_BARS_SKELETON) and not extra_on

        if hasattr(self, "text_trace_method_combo") and self.text_trace_method_combo is not None:
            self.text_trace_method_combo.configure(state="disabled" if extra_on else "readonly")
        if hasattr(self, "text_shape_combo") and self.text_shape_combo is not None:
            self.text_shape_combo.configure(state="readonly" if uses_grid else "disabled")
        if hasattr(self, "_trace_cell_entry") and self._trace_cell_entry is not None:
            self._trace_cell_entry.configure(state="normal" if uses_grid else "disabled")
        if hasattr(self, "_extra_shapes_toggle") and self.app._widget_alive(self._extra_shapes_toggle):
            self._extra_shapes_toggle.configure(state="disabled" if uses_bars else "normal")

        if hasattr(self, "_cell_hint_label") and self._cell_hint_label is not None:
            hint_key = "text_cell_hint" if uses_grid else "text_cell_size_unused_bar_trace"
            self._cell_hint_label.config(text=self._tr(hint_key))

        if hasattr(self, "_trace_method_hint_label") and self._trace_method_hint_label is not None:
            if extra_on:
                hint_key = "text_trace_method_hint_grid"
            elif method == TRACE_METHOD_BARS_FULL:
                hint_key = "text_trace_method_hint_bars_full"
            elif method == TRACE_METHOD_BARS_SKELETON:
                hint_key = "text_trace_method_hint_bars_skeleton"
            else:
                hint_key = "text_trace_method_hint_grid"
            self._trace_method_hint_label.config(text=self._tr(hint_key))

        self._update_trace_active_summary()

    def _update_trace_active_summary(self) -> None:
        if not hasattr(self, "_trace_active_summary_label") or self._trace_active_summary_label is None:
            return
        extra_on = self.text_extra_shapes.get() == "1"
        method = self._resolve_trace_method()
        cell = self.text_cell_size.get().strip() or "1"
        primitive = self.text_shape_mode.get().strip() or self._tr("text_shape_rectangles")
        if extra_on:
            text = self._tr("text_trace_active_summary_extra").format(cell=cell)
        elif method == TRACE_METHOD_BARS_FULL:
            text = self._tr("text_trace_active_summary_bars_full")
        elif method == TRACE_METHOD_BARS_SKELETON:
            text = self._tr("text_trace_active_summary_bars_skeleton")
        else:
            text = self._tr("text_trace_active_summary_grid").format(primitive=primitive, cell=cell)
        self._trace_active_summary_label.config(text=text)

    def _on_generation_option_changed(self) -> None:
        if not self._applying_preset and self.text_preset_id.get() != "custom":
            if self.text_preset_combo is not None:
                self.text_preset_combo.set(self._preset_id_to_label.get("custom", ""))
            self.text_preset_id.set("custom")
        self._sync_custom_preset_note()
        self._sync_trace_controls()
        self.update_shape_hint()
        self._schedule_layer_estimate()

    def _set_font_refresh_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in self._font_refresh_buttons:
            if self.app._widget_alive(button):
                button.configure(state=state)

    def _default_font_label(self, script: str, font_by_label: dict[str, Path]) -> str | None:
        preferred = default_font_path_for_script(script)
        if preferred is None:
            return None
        preferred = preferred.resolve()
        for label, path in font_by_label.items():
            try:
                if path.resolve() == preferred:
                    return label
            except OSError:
                continue
        return None

    def _mask_options(self) -> TextMaskOptions:
        try:
            max_layers = int(self.text_max_drawable_layers.get().strip() or str(DEFAULT_MAX_DRAWABLE_LAYERS))
        except ValueError:
            max_layers = DEFAULT_MAX_DRAWABLE_LAYERS
        max_layers = max(1, min(max_layers, 2996))
        return TextMaskOptions(
            include_boundary_masks=self.text_include_boundary_masks.get() == "1",
            include_polish_masks=self.text_include_polish_masks.get() == "1",
            max_drawable_layers=max_layers,
        )

    def _generation_options(self, script: str | None = None) -> dict:
        try:
            max_layers = int(self.text_max_drawable_layers.get().strip() or str(DEFAULT_MAX_DRAWABLE_LAYERS))
        except ValueError:
            max_layers = DEFAULT_MAX_DRAWABLE_LAYERS
        max_layers = max(1, min(max_layers, 2996))
        extra_shapes = self.text_extra_shapes.get() == "1"
        trace_method = self._resolve_trace_method()
        return {
            "font_size": int(self.text_font_size.get().strip() or "120"),
            "cell_size": normalize_trace_cell_size(self.text_cell_size.get().strip() or "1"),
            "shape_mode": self._resolve_shape_mode(),
            "trace_method": trace_method,
            "use_forza_font": False,
            "forza_font_index": 1,
            "fit_layer_budget": self.text_fit_layer_budget.get() == "1",
            "max_drawable_layers": max_layers,
            "extra_shapes": extra_shapes,
            "mask_options": self._mask_options(),
            "writing_mode": WRITING_MODE_HORIZONTAL_LTR,
        }

    def _schedule_layer_estimate(self) -> None:
        if self.closed:
            return
        if self._layer_estimate_job is not None:
            try:
                self.root.after_cancel(self._layer_estimate_job)
            except Exception:
                pass
        self.text_layer_estimate.set(self._tr("text_layer_estimate_working"))
        self._layer_estimate_job = self.root.after(550, self._start_layer_estimate)

    def _start_layer_estimate(self) -> None:
        self._layer_estimate_job = None
        script = self.active_script()
        panel = self._panel(script)
        text = self._get_panel_text(script).strip()
        if not text:
            self._layer_estimate_signature = None
            self._set_layer_estimate_message("text_layer_estimate_idle")
            return
        try:
            font_path = self._resolve_font_path(script)
        except Exception:
            font_path = None
        options = self._generation_options()
        signature = (
            script,
            text,
            str(font_path) if font_path else "",
            options["font_size"],
            options["cell_size"],
            options["shape_mode"],
            options["trace_method"],
            options["fit_layer_budget"],
            options["max_drawable_layers"],
            options["extra_shapes"],
            options["writing_mode"],
            options["mask_options"].include_boundary_masks,
            options["mask_options"].include_polish_masks,
        )
        if signature == self._layer_estimate_signature:
            return
        self._layer_estimate_signature = signature
        threading.Thread(
            target=self._layer_estimate_worker,
            args=(text, font_path, options),
            daemon=True,
        ).start()

    def _layer_estimate_worker(self, text: str, font_path: Path | None, options: dict) -> None:
        try:
            layers, cell_used, summary = estimate_typed_text_layers(
                text,
                font_path=font_path,
                font_size=options["font_size"],
                cell_size=options["cell_size"],
                shape_mode=options["shape_mode"],
                use_forza_font=False,
                forza_font_index=1,
                fit_layer_budget=options["fit_layer_budget"],
                max_drawable_layers=options["max_drawable_layers"],
                extra_shapes=options["extra_shapes"],
                trace_method=options["trace_method"],
                mask_options=options["mask_options"],
                writing_mode=options["writing_mode"],
            )
            self.queue.put(("text_layer_estimate", ("ok", layers, cell_used, summary)))
        except Exception as exc:
            self.queue.put(("text_layer_estimate", ("error", str(exc), 0)))

    def _set_layer_estimate_message(self, key: str, **kwargs) -> None:
        if self.text_layer_estimate_label is not None:
            self.text_layer_estimate_label.configure(text=self._tr(key).format(**kwargs))

    def handle_layer_estimate(self, result: tuple) -> None:
        kind = result[0]
        if kind == "ok":
            layers = int(result[1])
            cell_used = int(result[2])
            summary = result[3] if len(result) >= 4 and isinstance(result[3], dict) else {}
            drawable = int(summary.get("drawable_count", layers))
            polish = int(summary.get("polish_mask_count", 0))
            boundary = int(summary.get("boundary_mask_count", 0))
            mask_layers = polish + boundary
            template_need = layers
            cell_note = ""
            if self.text_fit_layer_budget.get() == "1":
                cell_note = self._tr("text_layer_estimate_cell").format(cell=cell_used)
            mode_note = ""
            if self.text_extra_shapes.get() == "1":
                mode_note = " " + self._tr("text_layer_estimate_extra_shapes")
            else:
                trace_method = self._resolve_trace_method()
                if trace_method == TRACE_METHOD_BARS_FULL:
                    mode_note = " " + self._tr("text_layer_estimate_bars_full")
                elif trace_method == TRACE_METHOD_BARS_SKELETON:
                    mode_note = " " + self._tr("text_layer_estimate_bars_skeleton")
                elif trace_method_uses_grid(trace_method):
                    mode_note = " " + self._tr("text_layer_estimate_grid")
            mask_detail = ""
            if mask_layers:
                mask_detail = self._tr("text_layer_estimate_masks_detail").format(
                    polish=polish,
                    boundary=boundary,
                )
            self._set_layer_estimate_message(
                "text_layer_estimate_ok",
                drawable=drawable,
                mask_layers=mask_layers,
                template=template_need,
                cell_note=cell_note + mask_detail,
                mode_note=mode_note,
            )
            return
        if kind == "error":
            self._set_layer_estimate_message("text_layer_estimate_error", error=result[1])
            return
        self._set_layer_estimate_message("text_layer_estimate_idle")

    def _get_panel_text(self, script: str | None = None) -> str:
        widget = self._panel(script).get("input_widget")
        if widget is None:
            return ""
        return widget.get("1.0", "end-1c")

    def _set_panel_text(self, script: str, text: str) -> None:
        widget = self._panel(script).get("input_widget")
        if widget is None:
            return
        widget.delete("1.0", END)
        if text:
            widget.insert("1.0", text)

    def _insert_text_at_cursor(self, script: str, text: str) -> None:
        widget = self._panel(script).get("input_widget")
        if widget is None or not text:
            return
        widget.insert("insert", text)
        widget.edit_modified(True)
        self._on_input_changed(script)

    def _clear_panel_text(self, script: str) -> None:
        self._set_panel_text(script, "")
        self._on_input_changed(script)

    def _bind_text_widget(self, script: str, widget: Text) -> None:
        panel = self._panel(script)
        panel["input_widget"] = widget

        def _on_change(_event=None) -> None:
            if widget.edit_modified():
                widget.edit_modified(False)
                self._on_input_changed(script)

        widget.bind("<<Modified>>", _on_change)
        widget.bind("<KeyRelease>", _on_change)

    def _build_script_panel(self, parent: Frame, script: str) -> None:
        parent.configure(bg=Theme.PANEL)
        self._build_text_entry_section(parent, script)
        self._build_font_section(parent, script)

    def _build_text_entry_section(self, parent: Frame, script: str) -> None:
        app = self.app
        widgets = self._panel(script)["widgets"]

        hint = app._label(parent, self._script_hint_key(script), anchor="w", justify="left", theme_role="muted")
        hint.pack(fill="x", padx=10, pady=(10, 6))
        app._bind_wraplength(hint, parent, padding=20)
        widgets["hint"] = hint

        text_frame = ttk.LabelFrame(parent, text=self._tr("text_section"))
        app.translated.append((text_frame, "text_section", "text"))
        text_frame.pack(fill=BOTH, expand=True, padx=10, pady=(0, 8))
        editor_host = Frame(text_frame, bg=Theme.PANEL)
        editor_host.pack(fill=BOTH, expand=True, padx=10, pady=8)
        _shell, text_widget = themed_text(editor_host, app, height=8)
        _shell.pack(fill=BOTH, expand=True)
        self._bind_text_widget(script, text_widget)

        actions = Frame(text_frame, bg=Theme.PANEL)
        actions.pack(fill="x", padx=10, pady=(0, 10))
        left_actions = Frame(actions, bg=Theme.PANEL)
        left_actions.pack(side=LEFT)
        app._button(left_actions, "text_char_library_open", self._open_character_library).pack(side=LEFT)
        app._button(left_actions, "text_clear", lambda s=script: self._clear_panel_text(s)).pack(side=LEFT, padx=(8, 0))
        benchmark_row = Frame(actions, bg=Theme.PANEL)
        benchmark_row.pack(side=RIGHT)
        app._button(
            benchmark_row,
            "text_insert_benchmark",
            lambda s=script: self.insert_benchmark_text(s),
        ).pack(side=LEFT)
        create_help_button(benchmark_row, app, "text_help_benchmark", padx=(4, 0))

    def _build_font_section(self, parent: Frame, script: str) -> None:
        app = self.app
        panel = self._panel(script)
        widgets = panel["widgets"]

        font_frame = ttk.LabelFrame(parent, text=self._tr("text_font_section"))
        app.translated.append((font_frame, "text_font_section", "text"))
        font_frame.pack(fill="x", padx=10, pady=(0, 10))

        font_box = Frame(font_frame, bg=Theme.PANEL)
        font_box.pack(fill="x", padx=10, pady=(8, 6))
        font_box.columnconfigure(1, weight=1)
        app._label(font_box, "text_font_search").grid(row=0, column=0, sticky="w")
        font_search = themed_entry(font_box, app, textvariable=panel["font_search"], width=28)
        font_search.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        font_search.bind("<KeyRelease>", lambda _event, s=script: self._on_font_search_changed(s))

        app._label(font_box, "text_font").grid(row=1, column=0, sticky="w", pady=(6, 0))
        font_combo = ttk.Combobox(
            font_box,
            textvariable=panel["font_choice"],
            state="readonly",
            font=FONT_COMBO_DISPLAY_FONT,
        )
        font_combo.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(6, 0))
        font_combo.bind("<<ComboboxSelected>>", lambda _event, s=script: self._on_font_selected(s))
        guard_combobox_against_mousewheel(font_combo)
        widgets["font_combo"] = font_combo

        preview_host = Frame(font_frame, bg=Theme.PANEL)
        preview_host.pack(fill="x", padx=10, pady=(0, 6))
        app._label(preview_host, "text_font_preview", anchor="w").pack(fill="x")
        preview_t = app.themes.tokens
        preview_label = Label(
            preview_host,
            text=self._tr("text_font_preview_empty"),
            bg=preview_t.preview_bg,
            fg=preview_t.preview_fg,
            anchor="w",
            justify="left",
            height=3,
        )
        preview_label.pack(fill="x", pady=(4, 0))
        widgets["font_preview_label"] = preview_label

        font_actions = Frame(font_frame, bg=Theme.PANEL)
        font_actions.pack(fill="x", padx=10, pady=(0, 4))
        app._button(font_actions, "text_font_browse", lambda s=script: self.browse_font(s)).pack(side=LEFT)
        app._button(font_actions, "text_font_browse_machine", self.browse_fonts_folder).pack(side=LEFT, padx=(8, 0))
        refresh_btn = app._button(
            font_actions,
            "text_font_refresh",
            lambda: self.refresh_fonts(full_rescan=True),
        )
        refresh_btn.pack(side=LEFT, padx=(8, 0))
        self._font_refresh_buttons.append(refresh_btn)
        load_hint = app._label(font_actions, "text_font_refresh_hint", anchor="w", theme_role="muted")
        load_hint.pack(side=LEFT, padx=(12, 0))
        app._bind_wraplength(load_hint, font_actions, padding=8)
        app.translated.append((load_hint, "text_font_refresh_hint", "text"))

    def _schedule_font_preview(self) -> None:
        if self._font_preview_job is not None:
            try:
                self.root.after_cancel(self._font_preview_job)
            except Exception:
                pass
        self._font_preview_job = self.root.after(300, self._update_font_preview)

    def _update_font_preview(self) -> None:
        self._font_preview_job = None
        script = self.active_script()
        widgets = self._panel(script)["widgets"]
        preview_label = widgets.get("font_preview_label")
        if preview_label is None or not self.app._widget_alive(preview_label):
            return
        sample = self._get_panel_text(script).strip()
        if not sample:
            preview_label.configure(image="", text=self._tr("text_font_preview_empty"))
            preview_label.image = None
            return
        sample = sample.replace("\n", " ")[:48]
        try:
            font_path = self._resolve_font_path(script)
        except Exception:
            preview_label.configure(image="", text=sample)
            preview_label.image = None
            return
        try:
            from text.geometry import render_text_mask
            from text.layout import layout_options_from_writing_mode

            mask = render_text_mask(
                sample,
                font_path=font_path,
                font_size=48,
                padding=12,
                layout=layout_options_from_writing_mode(WRITING_MODE_HORIZONTAL_LTR),
            )
            preview = mask.convert("RGB")
            max_w = max(120, preview_label.winfo_width() - 8)
            if preview.width > max_w:
                ratio = max_w / preview.width
                preview = preview.resize((max_w, max(1, int(preview.height * ratio))))
            photo = PhotoImage(preview)
            preview_label.configure(image=photo, text="")
            preview_label.image = photo
        except Exception:
            preview_label.configure(image="", text=sample)
            preview_label.image = None

    def _open_character_library(self) -> None:
        script = self.active_script()
        target = self._tr(self._script_tab_key(script))
        if self._char_library_dialog is not None and self._char_library_dialog.alive:
            self._char_library_dialog.set_target_label(target)
            self._char_library_dialog.focus()
            return
        self._char_library_dialog = CharacterLibraryDialog(
            self.app,
            on_insert_char=lambda char: self._insert_char(self.active_script(), char),
            target_label=target,
        )

    def _insert_char(self, script: str, char: str) -> None:
        self._insert_text_at_cursor(script, char)
        self._schedule_coverage_check()

    def refresh_char_pickers(self) -> None:
        if self._char_library_dialog is not None and self._char_library_dialog.alive:
            self._char_library_dialog.refresh()

    def on_tab_activated(self) -> None:
        self._schedule_reference_preview_refresh()
        self._schedule_json_preview_refresh()

    def _build_import_shape_notice(self, parent: Frame) -> None:
        app = self.app
        bg = Theme.PANEL_ALT
        frame = Frame(parent, bg=bg, highlightthickness=1, highlightbackground=Theme.BORDER)
        frame.pack(side=RIGHT, padx=(8, 0), anchor="ne")
        self._import_shape_notice_frame = frame

        body = Frame(frame, bg=bg)
        self._import_shape_notice_body = body

        self._import_shape_notice_label = Label(
            body,
            text=self._tr("text_import_shape_notice"),
            bg=bg,
            fg=Theme.ACCENT,
            anchor="w",
            justify="left",
            font=("Segoe UI", 9),
            wraplength=280,
        )
        self._import_shape_notice_label.pack(side=LEFT, padx=(8, 2), pady=6)

        Button(
            body,
            text="×",
            command=self._dismiss_import_shape_notice,
            bg=bg,
            fg=Theme.MUTED,
            activebackground=Theme.PANEL,
            activeforeground=Theme.TEXT,
            relief="flat",
            bd=0,
            padx=6,
            pady=0,
            font=("Segoe UI", 11, "bold"),
            cursor="hand2",
        ).pack(side=RIGHT, anchor="n", pady=2)

        self._import_shape_notice_restore = app._button(
            frame,
            "text_import_shape_notice_show",
            self._restore_import_shape_notice,
            bg=bg,
            fg=Theme.ACCENT,
            activebackground=Theme.PANEL,
            activeforeground=Theme.TEXT,
            highlightthickness=0,
            relief="flat",
            bd=0,
            padx=8,
            pady=6,
            font=("Segoe UI", 9),
            cursor="hand2",
        )

        if load_ui_preferences().get("text_import_shape_notice_dismissed"):
            self._set_import_shape_notice_collapsed()
        else:
            self._set_import_shape_notice_expanded()

    def _set_import_shape_notice_expanded(self) -> None:
        if self._import_shape_notice_body is None or self._import_shape_notice_restore is None:
            return
        self._import_shape_notice_restore.pack_forget()
        self._import_shape_notice_body.pack(side=LEFT, fill="both", expand=True)

    def _set_import_shape_notice_collapsed(self) -> None:
        if self._import_shape_notice_body is None or self._import_shape_notice_restore is None:
            return
        self._import_shape_notice_body.pack_forget()
        self._import_shape_notice_restore.pack(side=LEFT, padx=0, pady=0)

    def _dismiss_import_shape_notice(self) -> None:
        self._set_import_shape_notice_collapsed()
        prefs = load_ui_preferences()
        prefs["text_import_shape_notice_dismissed"] = True
        save_ui_preferences(prefs)

    def _restore_import_shape_notice(self) -> None:
        self._set_import_shape_notice_expanded()
        prefs = load_ui_preferences()
        prefs["text_import_shape_notice_dismissed"] = False
        save_ui_preferences(prefs)

    def on_language_changed(self) -> None:
        if self.text_script_notebook is not None:
            for index, script in enumerate(TEXT_SCRIPT_IDS):
                self.text_script_notebook.tab(index, text=self._tr(self._script_tab_key(script)))
            for script in TEXT_SCRIPT_IDS:
                hint = self._panel(script)["widgets"].get("hint")
                if hint is not None:
                    hint.config(text=self._tr(self._script_hint_key(script)))
        self.update_shape_hint()
        self._schedule_coverage_check()
        self._refresh_trace_method_combo()
        self._refresh_shape_mode_combo()
        self._sync_trace_controls()
        self._refresh_preset_combo()
        if self._import_shape_notice_label is not None:
            self._import_shape_notice_label.config(text=self._tr("text_import_shape_notice"))
        if self._char_library_dialog is not None and self._char_library_dialog.alive:
            self._char_library_dialog.on_language_changed()

    def update_theme_hints(self) -> None:
        self.update_shape_hint()
        self._schedule_coverage_check()

    def _preview_colors(self) -> tuple[str, str]:
        t = self.app.themes.tokens
        return t.preview_bg, t.preview_fg

    def on_theme_changed(self) -> None:
        self.update_theme_hints()
        self.refresh_char_pickers()
        if self._char_library_dialog is not None and self._char_library_dialog.alive:
            self._char_library_dialog.on_theme_changed()
        if self._reference_preview_path is not None:
            self.set_reference_preview(self._reference_preview_path)
        if getattr(self, "_json_preview_path", None) is not None:
            self.set_json_preview(self._json_preview_path)

    @staticmethod
    def _script_tab_key(script: str) -> str:
        return f"text_script_{script}"

    @staticmethod
    def _script_hint_key(script: str) -> str:
        return f"text_script_hint_{script}"

    def active_script(self) -> str:
        if self.text_script_notebook is None:
            return SCRIPT_CHINESE
        index = self.text_script_notebook.index(self.text_script_notebook.select())
        return TEXT_SCRIPT_IDS[index]

    def _panel(self, script: str | None = None) -> dict:
        return self.text_panels[script or self.active_script()]

    def _resolve_font_path(self, script: str | None = None) -> Path:
        script = script or self.active_script()
        panel = self._panel(script)
        browse = panel["font_path"].get().strip()
        if browse:
            path = Path(browse)
            if path.exists():
                return path.resolve()
            raise FileNotFoundError(f"Font not found: {path}")

        selection = panel["font_choice"].get().strip()
        if selection in panel["font_by_label"]:
            return panel["font_by_label"][selection]

        if selection:
            path = Path(selection)
            if path.exists():
                return path.resolve()

        discovered = panel["discovered"]
        if discovered:
            return discovered[0].path

        from text.fonts import find_font_for_text

        return find_font_for_text(self._get_panel_text(script), script=script)

    @staticmethod
    def _merge_discovered_fonts(
        existing: tuple[DiscoveredFont, ...],
        incoming: tuple[DiscoveredFont, ...],
    ) -> tuple[DiscoveredFont, ...]:
        by_path: dict[Path, DiscoveredFont] = {font.path: font for font in existing}
        for font in incoming:
            if not font.path.exists():
                continue
            prev = by_path.get(font.path)
            if prev is None or font.score > prev.score:
                by_path[font.path] = font
        return tuple(sorted(by_path.values(), key=lambda item: (-item.score, item.display_name.lower())))

    def refresh_fonts(self, *, full_rescan: bool = False) -> None:
        if full_rescan:
            clear_font_discovery_cache()
            self._fonts_deep_scanned.clear()
            self._fonts_scanning = True
            self._set_font_refresh_enabled(False)
        tier1 = {
            script: tuple(font for font in default_fonts_for_script(script) if font.path.exists())
            for script in TEXT_SCRIPT_IDS
        }
        self.apply_fonts_by_script(tier1, merge=not full_rescan, log=False)
        if full_rescan:
            self.app.log_line(self._tr("text_log_scanning_fonts"))
            threading.Thread(
                target=self._refresh_fonts_worker,
                args=(self.active_script(), full_rescan),
                daemon=True,
            ).start()
        else:
            self.app.log_line(
                self._tr("text_log_fonts_tier1").format(
                    latin=len(tier1.get(SCRIPT_UNIVERSAL, ())),
                    japanese=len(tier1.get(SCRIPT_JAPANESE, ())),
                    korean=len(tier1.get(SCRIPT_KOREAN, ())),
                    chinese=len(tier1.get(SCRIPT_CHINESE, ())),
                )
            )

    def _refresh_fonts_worker(self, priority_script: str, full_rescan: bool) -> None:
        try:
            order = [priority_script] + [s for s in TEXT_SCRIPT_IDS if s != priority_script]
            fonts_by_script: dict[str, tuple[DiscoveredFont, ...]] = {}
            for script in order:
                fonts = tuple(
                    font
                    for font in discover_fonts_for_script_cached(script, deep_scan=True)
                    if font.path.exists()
                )
                fonts_by_script[script] = fonts
                self._fonts_deep_scanned.add(script)
                self.queue.put(("text_fonts_ready", ({script: fonts}, True, False)))
                self.queue.put(
                    (
                        "log",
                        self._tr("text_log_fonts_scanned_script").format(
                            script=self._tr(self._script_tab_key(script)),
                            count=len(fonts),
                        ),
                    )
                )
            if fonts_by_script:
                self.queue.put(("text_fonts_ready", (fonts_by_script, True, True)))
        except Exception as exc:
            self.queue.put(("log", self._tr("text_log_font_scan_failed").format(error=exc)))
            self.queue.put(("text_fonts_scan_done", None))

    def insert_benchmark_text(self, script: str | None = None) -> None:
        script = script or self.active_script()
        text = random_benchmark_text(script)
        if not text:
            return
        self._set_panel_text(script, text)
        self._on_input_changed(script)

    def _refresh_script_font_combo(self, script: str) -> None:
        panel = self._panel(script)
        widgets = panel["widgets"]
        combo = widgets.get("font_combo")
        if combo is None:
            return

        filtered = filter_font_labels(panel["discovered"], panel["font_search"].get())
        filtered = tuple(sorted(filtered, key=lambda font: font.display_name.lower()))
        labels = [font.label for font in filtered]
        font_by_label: dict[str, Path] = {}
        for font, label in zip(filtered, labels):
            font_by_label[label] = font.path
        panel["font_by_label"] = font_by_label
        combo["values"] = labels

        current = panel["font_choice"].get().strip()
        if labels and current not in labels:
            default_label = self._default_font_label(script, font_by_label)
            panel["font_choice"].set(default_label or labels[0])
        elif not labels:
            panel["font_choice"].set("")

    def apply_fonts_by_script(self, fonts_by_script: dict, *, merge: bool = True, log: bool = True) -> None:
        total = 0
        for script in TEXT_SCRIPT_IDS:
            fonts = tuple(fonts_by_script.get(script, ()))
            if not fonts:
                continue
            panel = self._panel(script)
            if merge and panel["discovered"]:
                panel["discovered"] = self._merge_discovered_fonts(panel["discovered"], fonts)
            else:
                panel["discovered"] = fonts
            self._refresh_script_font_combo(script)
            total += len(fonts)
        if log:
            if total:
                self.app.log_line(
                    self._tr("text_log_fonts_loaded").format(
                        latin=len(fonts_by_script.get("universal", ())),
                        japanese=len(fonts_by_script.get("japanese", ())),
                        korean=len(fonts_by_script.get("korean", ())),
                        chinese=len(fonts_by_script.get("chinese", ())),
                    )
                )
            else:
                self.app.log_line(self._tr("text_log_no_fonts"))
        if log:
            if self._fonts_scanning:
                self._fonts_scanning = False
                self._set_font_refresh_enabled(True)
        self._schedule_coverage_check()

    def browse_font(self, script: str | None = None) -> None:
        script = script or self.active_script()
        panel = self._panel(script)
        path = filedialog.askopenfilename(
            title=self._tr("text_dialog_select_font"),
            filetypes=[("Fonts", "*.ttf;*.ttc;*.otf"), ("All files", "*.*")],
        )
        if not path:
            return
        panel["font_path"].set(path)
        panel["font_choice"].set(Path(path).name)
        self._schedule_coverage_check()

    def browse_fonts_folder(self) -> None:
        try:
            open_system_font_settings()
        except OSError as exc:
            self.app.log_line(str(exc))

    def _on_font_selected(self, script: str | None = None) -> None:
        panel = self._panel(script)
        panel["font_path"].set("")
        self._schedule_coverage_check()
        if (script or self.active_script()) == self.active_script():
            self._schedule_font_preview()

    def _on_font_search_changed(self, script: str) -> None:
        self._refresh_script_font_combo(script)

    def _maybe_auto_cjk_preset(self, script: str) -> None:
        if script not in (SCRIPT_CHINESE, SCRIPT_JAPANESE, SCRIPT_KOREAN):
            return
        if self.text_preset_id.get() != "custom":
            return
        if not self._get_panel_text(script).strip():
            return
        self._apply_preset(CJK_DEFAULT_PRESET_ID)

    def _on_input_changed(self, script: str) -> None:
        self._maybe_auto_cjk_preset(script)
        self._schedule_coverage_check()
        if script == self.active_script():
            self._schedule_layer_estimate()
            self._schedule_font_preview()

    def _on_script_tab_changed(self) -> None:
        script = self.active_script()
        self._maybe_auto_cjk_preset(script)
        self._refresh_script_font_combo(script)
        self._schedule_coverage_check()
        self._schedule_layer_estimate()
        self._schedule_font_preview()
        if self._char_library_dialog is not None and self._char_library_dialog.alive:
            self._char_library_dialog.set_target_label(self._tr(self._script_tab_key(script)))

    def _resolve_trace_method(self) -> str:
        value = self.text_trace_method.get().strip()
        if value in self._trace_method_label_to_mode:
            return self._trace_method_label_to_mode[value]
        return normalize_text_trace_method(value)

    def _refresh_trace_method_combo(self) -> None:
        current_method = normalize_text_trace_method(self._resolve_trace_method())
        labels: list[str] = []
        self._trace_method_label_to_mode.clear()
        self._trace_method_mode_to_label.clear()
        for method in TEXT_TRACE_METHOD_UI_CHOICES:
            label = self._tr(f"text_trace_method_{method}")
            labels.append(label)
            self._trace_method_label_to_mode[label] = method
            self._trace_method_mode_to_label[method] = label
        if self.text_trace_method_combo is not None:
            self.text_trace_method_combo["values"] = labels
        display = self._trace_method_mode_to_label.get(current_method, labels[0] if labels else "")
        self.text_trace_method.set(display)

    def _resolve_shape_mode(self) -> str:
        value = self.text_shape_mode.get().strip()
        if value in self._shape_mode_label_to_mode:
            return self._shape_mode_label_to_mode[value]
        return normalize_text_shape_mode(value)

    def _refresh_shape_mode_combo(self) -> None:
        current_mode = coerce_text_shape_mode_for_ui(self.text_shape_mode.get())
        labels: list[str] = []
        self._shape_mode_label_to_mode.clear()
        self._shape_mode_mode_to_label.clear()
        for mode in TEXT_SHAPE_MODE_UI_CHOICES:
            label = self._tr(f"text_shape_{mode}")
            labels.append(label)
            self._shape_mode_label_to_mode[label] = mode
            self._shape_mode_mode_to_label[mode] = label
        if self.text_shape_combo is not None:
            self.text_shape_combo["values"] = labels
        display = self._shape_mode_mode_to_label.get(current_mode, labels[0] if labels else "")
        self.text_shape_mode.set(display)

    def update_shape_hint(self) -> None:
        if self.text_template_hint_label is None:
            return
        self.text_template_hint_label.config(
            text=self._tr("text_template_hint"),
            fg=self._color("COLOR_INFO"),
        )
        if self._import_shape_notice_label is not None:
            self._import_shape_notice_label.config(text=self._tr("text_import_shape_notice"))

    def _schedule_coverage_check(self) -> None:
        if self._coverage_job is not None:
            try:
                self.root.after_cancel(self._coverage_job)
            except Exception:
                pass
        self._coverage_job = self.root.after(350, self._start_coverage_check)

    def _start_coverage_check(self) -> None:
        self._coverage_job = None
        if not self.app._widget_alive(self.text_coverage_label):
            return
        script = self.active_script()
        panel = self._panel(script)
        text = self._get_panel_text(script).strip()
        self._last_font_recommendation = None
        if self._coverage_apply_button is not None:
            self._coverage_apply_button.config(state="disabled")
        if not text:
            self.text_coverage_label.config(text="", fg=self.app.themes.fg("muted"))
            return
        try:
            font_path = self._resolve_font_path(script)
        except Exception as exc:
            self.text_coverage_label.config(text=str(exc), fg=self.app.themes.fg("error"))
            return

        self._coverage_generation += 1
        generation = self._coverage_generation
        discovered = tuple(panel["discovered"])
        selected = panel["font_choice"].get().strip()
        threading.Thread(
            target=self._coverage_check_worker,
            args=(generation, script, text, font_path, discovered, selected),
            daemon=True,
        ).start()

    def _coverage_check_worker(
        self,
        generation: int,
        script: str,
        text: str,
        font_path: Path,
        discovered: tuple[DiscoveredFont, ...],
        selected: str,
    ) -> None:
        try:
            ok, missing = validate_text_coverage(text, font_path)
            recommendation = None
            if not ok:
                recommendation = recommend_font_for_text(text, script=script, fonts=discovered)
            elif text_contains_hangul(text) and "[KR]" not in selected.upper():
                recommendation = recommend_font_for_text(text, script=script, fonts=discovered)
            self.queue.put(
                (
                    "text_coverage_ready",
                    {
                        "generation": generation,
                        "script": script,
                        "text": text,
                        "ok": ok,
                        "missing": missing,
                        "recommendation": recommendation,
                    },
                )
            )
        except Exception as exc:
            self.queue.put(
                (
                    "text_coverage_ready",
                    {
                        "generation": generation,
                        "script": script,
                        "text": text,
                        "error": str(exc),
                    },
                )
            )

    def handle_coverage_ready(self, payload: dict) -> None:
        if payload.get("generation") != self._coverage_generation:
            return
        if not self.app._widget_alive(self.text_coverage_label):
            return
        if payload.get("error"):
            self.text_coverage_label.config(text=payload["error"], fg=self.app.themes.fg("error"))
            return

        script = payload.get("script") or self.active_script()
        panel = self._panel(script)
        if self._get_panel_text(script).strip() != payload.get("text", ""):
            return

        text = payload["text"]
        missing = payload.get("missing") or []
        ok = bool(payload.get("ok"))
        recommendation = payload.get("recommendation")
        self._last_font_recommendation = recommendation
        selected = panel["font_choice"].get().strip()

        if ok:
            message = self._tr(coverage_message_key(text, True, missing))
            if (
                recommendation is not None
                and recommendation.label
                and text_contains_hangul(text)
                and "[KR]" not in selected.upper()
            ):
                message = self._tr("text_coverage_suggest_kr").format(font=recommendation.label)
                fg = self.app.themes.fg("hint")
            else:
                fg = self.app.themes.fg("success")
            self.text_coverage_label.config(text=message, fg=fg)
            return

        key = coverage_message_key(text, False, missing)
        message = self._tr(key).format(
            count=len(missing),
            chars=format_missing_chars(missing),
        )
        if recommendation is not None and recommendation.label:
            if recommendation.complete:
                message = f"{message} {self._tr('text_coverage_suggest_font').format(font=recommendation.label)}"
            else:
                message = self._tr("text_coverage_partial").format(
                    covered=recommendation.covered,
                    total=recommendation.total,
                    font=recommendation.label,
                    chars=format_missing_chars(missing),
                )
        if (
            recommendation is not None
            and recommendation.font is not None
            and recommendation.label
            and recommendation.label != selected
            and self._coverage_apply_button is not None
        ):
            self._coverage_apply_button.config(state="normal")
        self.text_coverage_label.config(text=message, fg=self.app.themes.fg("error"))

    def update_coverage_status(self) -> None:
        self._schedule_coverage_check()

    def apply_recommended_font(
        self,
        recommendation: FontRecommendation | None = None,
        script: str | None = None,
    ) -> None:
        script = script or self.active_script()
        rec = recommendation or self._last_font_recommendation
        if rec is None or rec.font is None or not rec.label:
            return
        panel = self._panel(script)
        panel["font_path"].set("")
        if rec.label in panel["font_by_label"]:
            panel["font_choice"].set(rec.label)
        else:
            discovered = tuple(panel["discovered"])
            if rec.font not in discovered:
                panel["discovered"] = discovered + (rec.font,)
                self._refresh_script_font_combo(script)
            panel["font_choice"].set(rec.label)
        self.update_coverage_status()

    def _parse_color(self) -> tuple[int, int, int, int]:
        if self._color_editor is None:
            return 255, 255, 255, 255
        try:
            return self._color_editor.get_rgba()
        except ValueError as exc:
            raise ValueError(self._tr("text_color_invalid")) from exc

    def browse_reference_image(self) -> None:
        path = filedialog.askopenfilename(
            title=self._tr("text_dialog_select_reference_image"),
            filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.webp"), ("All files", "*.*")],
        )
        if path:
            self.text_image_path.set(path)
            self._schedule_reference_preview_refresh()

    def start_generate_typed(self) -> None:
        script = self.active_script()
        panel = self._panel(script)
        text = self._get_panel_text(script).strip()
        if not text:
            self.app.log_line(self._tr("text_log_enter_text"))
            return
        try:
            font_path = self._resolve_font_path(script)
        except Exception as exc:
            self.app.log_line(f"{self._tr('text_failed')}: {exc}")
            return
        self.app.status.set(self._tr("running"))
        threading.Thread(target=self._typed_worker, args=(text, font_path), daemon=True).start()

    def start_trace(self) -> None:
        path = self.text_image_path.get().strip()
        if not path:
            self.app.log_line(self._tr("text_log_choose_trace_image"))
            return
        self.app.status.set(self._tr("running"))
        threading.Thread(target=self._trace_worker, args=(path,), daemon=True).start()

    @staticmethod
    def output_path(stem: str, *, mode: str = "typed", identity: str | None = None) -> Path:
        safe = re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff-]+", "_", stem, flags=re.UNICODE).strip("_")
        if not safe:
            safe = "text_vinyl"
        identity = identity or stem or safe
        paths = text_vinyl_workspace(mode, identity).ensure()
        return paths.json_finals / f"{safe[:48]}.json"

    def finish_json(
        self,
        payload,
        output: Path,
        shape_mode: str | None = None,
        extra_shapes: bool = False,
    ) -> None:
        write_text_design_json(output, payload)
        summary = summarize_payload_layers(payload)
        layers = summary["total_layers"]
        mask_note = ""
        if summary.get("polish_mask_count") or summary.get("boundary_mask_count"):
            mask_note = self._tr("text_done_masks").format(
                polish=summary.get("polish_mask_count", 0),
                boundary=summary.get("boundary_mask_count", 0),
            )
        try:
            import json
            from datetime import datetime, timezone

            root = output.parent.parent
            if root.parent == TEXT_VINYL_WORKSPACE_ROOT:
                manifest_path = root / "manifest.json"
                body: dict = {}
                if manifest_path.is_file():
                    body = json.loads(manifest_path.read_text(encoding="utf-8"))
                body.setdefault("workspace_id", root.name)
                body.setdefault("kind", "text_vinyl")
                body.update(
                    {
                        "label": output.name,
                        "layers": layers,
                        "shape_mode": shape_mode or "",
                        "output": str(output),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                manifest_path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass
        if output not in self.json_files:
            self.json_files.append(output)
        self.render_json_list()
        self.set_json_preview(output)
        self._update_layer_stack_summary(output)
        self.app.log_line(
            self._tr("text_done").format(layers=layers, mask_note=mask_note, path=output)
        )
        self.app.log_line(self._tr("text_template_hint"))
        self.app.status.set(self._tr("done"))

    def render_json_list(self) -> None:
        if self.text_json_list is None:
            return
        self.text_json_list.delete(0, END)
        for path in self.json_files:
            self.text_json_list.insert(END, self.app._json_list_display(path))

    def add_json(self) -> None:
        files = filedialog.askopenfilenames(
            title=self._tr("text_dialog_add_json"),
            filetypes=[("Geometry JSON", "*.json"), ("All files", "*.*")],
        )
        if not files:
            return
        added = 0
        for raw in files:
            path = Path(raw)
            if path.suffix.lower() != ".json" or not path.exists():
                continue
            if path not in self.json_files:
                self.json_files.append(path)
                added += 1
        if added:
            self.render_json_list()
            self.set_json_preview(self.json_files[-1])
            self.text_json_list.selection_clear(0, END)
            self.text_json_list.selection_set(len(self.json_files) - 1)

    def remove_selected_json(self) -> None:
        if self.text_json_list is None:
            return
        selection = list(self.text_json_list.curselection())
        if not selection:
            return
        for index in reversed(selection):
            del self.json_files[index]
        self.render_json_list()
        if self.json_files:
            self.text_json_list.selection_set(0)
            self.set_json_preview(self.json_files[0])
        else:
            self._json_preview_path = None
            self.set_json_preview(None)
            self._update_layer_stack_summary(None)

    def send_to_import(self) -> None:
        if self.text_json_list is None:
            return
        selection = list(self.text_json_list.curselection())
        paths = [self.json_files[index] for index in selection] if selection else list(self.json_files)
        if not paths:
            self.app.log_line(self._tr("text_log_no_json_to_send"))
            return
        added = self.app.add_text_import_paths(paths, navigate=True)
        if added:
            self.app.log_line(self._tr("text_log_added_json_import").format(count=added))
        else:
            self.app.log_line(self._tr("text_log_json_already_import"))

    def open_output_folder(self) -> None:
        from asset_workspace import TEXT_VINYL_WORKSPACE_ROOT

        TEXT_VINYL_WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
        os.startfile(TEXT_VINYL_WORKSPACE_ROOT)  # type: ignore[attr-defined]

    def _preview_selected_json(self, _event=None) -> None:
        if self.text_json_list is None:
            return
        selection = list(self.text_json_list.curselection())
        if not selection:
            return
        self.set_json_preview(self.json_files[selection[0]])

    def _schedule_reference_preview_refresh(self) -> None:
        if self.text_reference_preview_label is None or self.closed:
            return
        if self._reference_preview_job is not None:
            try:
                self.root.after_cancel(self._reference_preview_job)
            except Exception:
                pass
        self._reference_preview_job = self.root.after(180, self._refresh_reference_preview)

    def _refresh_reference_preview(self) -> None:
        self._reference_preview_job = None
        raw = self.text_image_path.get().strip()
        path = Path(raw) if raw else None
        self.set_reference_preview(path)

    def set_reference_preview(self, path: Path | None) -> None:
        if self.text_reference_preview_label is None:
            return
        self._reference_preview_path = Path(path) if path else None
        label = self.text_reference_preview_label
        preview_bg, preview_fg = self._preview_colors()
        if path is None or not path.exists():
            label.config(image="", text=self._tr("preview_hint"), bg=preview_bg, fg=preview_fg)
            label.image = None
            return
        render_source_image, _render_geometry_json = self._preview_renderers()
        data = render_source_image(path, self.app._preview_bounds(label))
        if not data:
            label.config(image="", text=self._tr("preview_unavailable"), bg=preview_bg, fg=preview_fg)
            label.image = None
            return
        image = PhotoImage(data=data)
        label.config(image=image, text="", bg=preview_bg)
        label.image = image

    def _schedule_json_preview_refresh(self) -> None:
        if self.text_json_preview_label is None or self.closed:
            return
        if self._json_preview_job is not None:
            try:
                self.root.after_cancel(self._json_preview_job)
            except Exception:
                pass
        self._json_preview_job = self.root.after(180, self._refresh_json_preview)

    def _refresh_json_preview(self) -> None:
        self._json_preview_job = None
        path = self._json_preview_path
        if path is not None:
            self.set_json_preview(path)

    def set_json_preview(self, path: Path | None) -> None:
        if self.text_json_preview_label is None:
            return
        label = self.text_json_preview_label
        preview_bg, preview_fg = self._preview_colors()
        if path is None:
            self._json_preview_path = None
            label.config(image="", text=self._tr("preview_hint"), bg=preview_bg, fg=preview_fg)
            label.image = None
            self._update_layer_stack_summary(None)
            return
        path = Path(path)
        self._json_preview_path = path
        if not path.exists():
            label.config(image="", text=self._tr("preview_unavailable"), bg=preview_bg, fg=preview_fg)
            label.image = None
            return
        bounds = self.app._preview_bounds(label)
        slot = self.app._geometry_preview_slot_for_label(label)

        def on_ready(png_bytes) -> None:
            if not self.app._widget_alive(label):
                return
            if not png_bytes:
                label.config(
                    image="",
                    text=self._tr("preview_unavailable"),
                    bg=preview_bg,
                    fg=preview_fg,
                )
                label.image = None
                return
            image = PhotoImage(data=png_bytes)
            label.config(image=image, text="", bg=preview_bg)
            label.image = image

        self.app.schedule_geometry_json_preview(slot, path, bounds, on_ready)
        self._update_layer_stack_summary(path)

    def _update_layer_stack_summary(self, path: Path | None) -> None:
        if self.text_layer_stack_label is None:
            return
        if path is None or not Path(path).is_file():
            self.text_layer_stack_label.pack_forget()
            return
        try:
            import json

            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            summary = summarize_payload_layers(payload)
        except Exception:
            self.text_layer_stack_label.pack_forget()
            return
        drawable = summary.get("drawable_count", 0)
        polish = summary.get("polish_mask_count", 0)
        boundary = summary.get("boundary_mask_count", 0)
        total = summary.get("total_layers", 0)
        if polish or boundary:
            text = self._tr("text_layer_stack_summary").format(
                drawable=drawable,
                polish=polish,
                boundary=boundary,
                total=total,
            )
        else:
            text = self._tr("text_layer_stack_no_masks").format(drawable=drawable, total=total)
        self.text_layer_stack_label.configure(text=text)
        self.text_layer_stack_label.pack(fill="x", padx=10, pady=(0, 8))

    def _typed_worker(self, text: str, font_path: Path | None) -> None:
        try:
            self.queue.put(("log", self._tr("text_generating")))
            color = self._parse_color()
            options = self._generation_options()
            payload, cell_used = build_typecode_from_text_with_options(
                text,
                color=color,
                font_path=font_path,
                font_size=options["font_size"],
                cell_size=options["cell_size"],
                shape_mode=options["shape_mode"],
                use_forza_font=options["use_forza_font"],
                forza_font_index=options["forza_font_index"],
                fit_layer_budget=options["fit_layer_budget"],
                max_drawable_layers=options["max_drawable_layers"],
                extra_shapes=options["extra_shapes"],
                trace_method=options["trace_method"],
                mask_options=options["mask_options"],
                writing_mode=options["writing_mode"],
            )
            if cell_used != options["cell_size"]:
                self.queue.put(("text_cell_size_applied", str(cell_used)))
            shape_mode = options["shape_mode"]
            paths = text_vinyl_workspace("typed", text).ensure()
            write_manifest(
                paths,
                {
                    "label": text[:48],
                    "mode": "typed",
                    "source_original": text[:120],
                },
            )
            output = self.output_path(text[:12], mode="typed", identity=text)
            self.queue.put(
                ("text_json_done", (payload, output, shape_mode, options["extra_shapes"]))
            )
        except Exception as exc:
            self.queue.put(("log", f"{self._tr('text_failed')}: {exc}"))
            self.queue.put(("status", self._tr("failed")))

    def _trace_worker(self, path: str) -> None:
        try:
            self.queue.put(("log", self._tr("text_generating")))
            color = self._parse_color()
            options = self._generation_options()
            cell_size = options["cell_size"]
            shape_mode = options["shape_mode"]
            extra_shapes = options["extra_shapes"]
            source = Path(path)
            identity = str(source.resolve()) if source.exists() else path
            paths = text_vinyl_workspace("trace", identity).ensure()
            trace_input = source
            try:
                from file_management_settings import load_file_management_settings

                if source.exists() and load_file_management_settings().effective_copy_trace_references():
                    import shutil

                    destination = workspace_source_file(paths, source.suffix or ".png")
                    try:
                        if not destination.exists() or source.stat().st_mtime > destination.stat().st_mtime:
                            shutil.copy2(source, destination)
                        trace_input = destination
                    except OSError:
                        trace_input = source
            except ImportError:
                pass
            payload = build_typecode_from_text_image(
                trace_input,
                color=color,
                cell_size=cell_size,
                invert=self.text_invert.get() == "1",
                shape_mode=shape_mode,
                extra_shapes=extra_shapes,
                trace_method=options["trace_method"],
                mask_options=options["mask_options"],
            )
            output = self.output_path(source.stem, mode="trace", identity=identity)
            write_manifest(
                paths,
                {
                    "label": source.name,
                    "mode": "trace",
                    "source_original": identity,
                    "shape_mode": shape_mode,
                },
            )
            self.queue.put(("text_json_done", (payload, output, shape_mode, extra_shapes)))
        except Exception as exc:
            self.queue.put(("log", f"{self._tr('text_failed')}: {exc}"))
            self.queue.put(("status", self._tr("failed")))
