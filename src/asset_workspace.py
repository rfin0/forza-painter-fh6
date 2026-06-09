"""Structured workspace roots, tier paths, and safe cache cleanup."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal

from app_paths import ROOT

IMAGE_SOURCE_BASENAME = "original"

WorkspaceKind = Literal["image", "text_vinyl", "pixel_art"]

IMAGE_WORKSPACE_ROOT = ROOT / "runtime" / "workspace"
TEXT_VINYL_WORKSPACE_ROOT = ROOT / "runtime" / "text-vinyl"
PIXEL_ART_WORKSPACE_ROOT = ROOT / "runtime" / "pixel-art"

LEGACY_GENERATOR_PREVIEW_DIR = ROOT / "runtime" / "previews"
LEGACY_FILTER_PREVIEW_DIR = ROOT / "imgs" / "filter-previews"

_SAFE_STEM_RE = re.compile(r"[^A-Za-z0-9_.-]+")

WORKSPACE_SIGNATURE_NAME = "SIGNATURE.txt"
_LEGACY_WORKSPACE_SIGNATURE_NAME = "SIGNATURE"


def workspace_root(kind: WorkspaceKind) -> Path:
    if kind == "image":
        return IMAGE_WORKSPACE_ROOT
    if kind == "pixel_art":
        return PIXEL_ART_WORKSPACE_ROOT
    return TEXT_VINYL_WORKSPACE_ROOT


def _hash8(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:8]


def safe_stem(name: str, *, limit: int = 48) -> str:
    cleaned = _SAFE_STEM_RE.sub("_", name).strip("._")
    if not cleaned:
        cleaned = "workspace"
    return cleaned[:limit]


def image_workspace_id(source: Path) -> str:
    source = Path(source)
    try:
        key = str(source.resolve()).lower()
    except OSError:
        key = str(source).lower()
    return f"{safe_stem(source.stem)}__{_hash8(key)}"


def text_vinyl_workspace_id(*, mode: str, identity: str) -> str:
    payload = f"{mode}:{identity}".lower()
    prefix = safe_stem(identity[:24] or mode, limit=24)
    return f"{prefix}__{_hash8(payload)}"


@dataclass(frozen=True)
class WorkspacePaths:
    kind: WorkspaceKind
    workspace_id: str
    root: Path
    manifest: Path
    source: Path
    variants: Path
    json_root: Path
    json_finals: Path
    json_checkpoints: Path
    preview: Path
    preview_filters: Path
    preview_generation: Path
    cache: Path
    logs: Path

    def ensure(self) -> WorkspacePaths:
        for path in (
            self.root,
            self.source,
            self.variants,
            self.json_root,
            self.json_finals,
            self.json_checkpoints,
            self.preview,
            self.preview_filters,
            self.cache,
            self.logs,
        ):
            path.mkdir(parents=True, exist_ok=True)
        write_workspace_signature(self)
        return self


def _image_workspace_paths(workspace_id: str, root: Path) -> WorkspacePaths:
    preview = root / "preview"
    return WorkspacePaths(
        kind="image",
        workspace_id=workspace_id,
        root=root,
        manifest=root / "manifest.json",
        source=root / "source",
        variants=root / "variants",
        json_root=root / "json",
        json_finals=root / "json" / "finals",
        json_checkpoints=root / "json" / "checkpoints",
        preview=preview,
        preview_filters=preview / "filters",
        preview_generation=preview / "generation.preview.png",
        cache=root / "cache",
        logs=root / "logs",
    )


def image_workspace(source: str | Path) -> WorkspacePaths:
    source = Path(source)
    try:
        resolved = source.resolve()
        ws_root = IMAGE_WORKSPACE_ROOT.resolve()
        if ws_root in resolved.parents:
            workspace_id = resolved.relative_to(ws_root).parts[0]
            root = ws_root / workspace_id
            if root.is_dir():
                return _image_workspace_paths(workspace_id, root)
    except (OSError, ValueError):
        pass
    workspace_id = image_workspace_id(source)
    return _image_workspace_paths(workspace_id, IMAGE_WORKSPACE_ROOT / workspace_id)


def is_path_in_workspace(path: str | Path, paths: WorkspacePaths | None = None) -> bool:
    path = Path(path)
    try:
        resolved = path.resolve()
        root = (paths.root if paths is not None else image_workspace(path).root).resolve()
        return resolved == root or root in resolved.parents
    except OSError:
        return False


def workspace_source_file(paths: WorkspacePaths, suffix: str = ".png") -> Path:
    ext = suffix if suffix.startswith(".") else f".{suffix}"
    return paths.source / f"{IMAGE_SOURCE_BASENAME}{ext.lower()}"


def _path_points_into_workspace(path_str: str, paths: WorkspacePaths) -> bool:
    if not path_str:
        return False
    try:
        resolved = Path(path_str).resolve()
        root = paths.root.resolve()
        return resolved == root or root in resolved.parents
    except OSError:
        return False


def _stem_is_internal_copy_name(stem: str) -> bool:
    return safe_stem(stem).lower() == IMAGE_SOURCE_BASENAME


def workspace_id_display_stem(paths: WorkspacePaths) -> str:
    """Human stem from workspace folder id (e.g. kiara_bluefield_nobg__ca0663de -> kiara_bluefield_nobg)."""
    workspace_id = paths.workspace_id
    if "__" in workspace_id:
        prefix = workspace_id.rsplit("__", 1)[0]
    else:
        prefix = workspace_id
    prefix = safe_stem(prefix)
    if prefix and not _stem_is_internal_copy_name(prefix):
        return prefix
    return ""


def _import_stem_from_manifest(paths: WorkspacePaths, manifest: dict) -> str:
    source_original = str(manifest.get("source_original", "")).strip()
    if source_original and not _path_points_into_workspace(source_original, paths):
        stem = safe_stem(Path(source_original).stem)
        if not _stem_is_internal_copy_name(stem):
            return stem

    label = str(manifest.get("label", "")).strip()
    if label and not _stem_is_internal_copy_name(Path(label).stem):
        return safe_stem(Path(label).stem)

    return workspace_id_display_stem(paths)


def _display_filename_for_stem(stem: str, source: Path, paths: WorkspacePaths) -> str:
    if source.suffix:
        return f"{stem}{source.suffix.lower()}"
    for candidate in sorted(paths.source.glob(f"{IMAGE_SOURCE_BASENAME}.*")):
        if candidate.is_file():
            return f"{stem}{candidate.suffix.lower()}"
    return f"{stem}.png"


def generated_run_folder_label(folder: str | Path) -> str:
    """Label for Import past-generations list (workspace name, not bare 'json')."""
    folder = Path(folder)
    try:
        resolved = folder.resolve()
        ws_root = IMAGE_WORKSPACE_ROOT.resolve()
        if ws_root in resolved.parents:
            workspace_id = resolved.relative_to(ws_root).parts[0]
            stem = workspace_id.rsplit("__", 1)[0] if "__" in workspace_id else workspace_id
            stem = safe_stem(stem)
            if stem and not _stem_is_internal_copy_name(stem):
                return stem
    except (OSError, ValueError):
        pass
    return folder.name


def ensure_image_workspace_source(source: str | Path, *, copy_external: bool) -> Path:
    """Return the path used to read image bytes; optionally copy externals into workspace."""
    source = Path(source)
    paths = image_workspace(source).ensure()
    try:
        original = str(source.resolve())
    except OSError:
        original = str(source)
    manifest = read_manifest(paths)
    inside_workspace = is_path_in_workspace(source, paths)

    if manifest is None:
        if not inside_workspace:
            write_manifest(
                paths,
                {
                    "label": source.name,
                    "source_original": original,
                },
            )
    elif not inside_workspace:
        if manifest.get("source_original") != original or manifest.get("label") != source.name:
            body = dict(manifest)
            body["source_original"] = original
            body["label"] = source.name
            write_manifest(paths, body)
    elif _path_points_into_workspace(str(manifest.get("source_original", "")), paths):
        body = dict(manifest)
        stem = workspace_id_display_stem(paths)
        if stem:
            body["label"] = _display_filename_for_stem(stem, source, paths)
            write_manifest(paths, body)

    if inside_workspace:
        for candidate in sorted(paths.source.glob(f"{IMAGE_SOURCE_BASENAME}.*")):
            if candidate.is_file():
                return candidate
        return source

    destination = workspace_source_file(paths, source.suffix or ".png")
    if not copy_external:
        return source
    try:
        if not destination.exists() or source.stat().st_mtime > destination.stat().st_mtime:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        return destination
    except OSError:
        return source


def variant_image_path(source: str | Path, mode: str, *, suffix: str | None = None) -> Path:
    """Canonical preprocessed variant path: ``variants/{stem}.{mode}{ext}``."""
    source = Path(source)
    ext = suffix or source.suffix or ".png"
    paths = image_workspace(source).ensure()
    mode_name = normalize_filter_mode(mode)
    if mode_name in ("", "none"):
        mode_name = "plain"
    base_stem = workspace_source_stem(source)
    return paths.variants / f"{base_stem}.{mode_name}{ext.lower()}"


def legacy_variant_image_path(source: str | Path, mode: str, *, suffix: str | None = None) -> Path:
    """Previous layout: ``variants/{mode}{ext}`` (still read for migration)."""
    source = Path(source)
    ext = suffix or source.suffix or ".png"
    paths = image_workspace(source).ensure()
    mode_name = normalize_filter_mode(mode)
    return paths.variants / f"{mode_name}{ext.lower()}"


def filter_preview_path(source: str | Path, mode: str) -> Path:
    source = Path(source)
    paths = image_workspace(source).ensure()
    return paths.preview_filters / f"{normalize_filter_mode(mode)}.png"


def normalize_filter_mode(mode: str) -> str:
    return str(mode or "none").strip().lower()


def generator_json_output_base(source: str | Path, preprocess_mode: str | None = None) -> Path:
    from preprocess.filters import filter_json_slug, normalize_preprocess_mode

    source = Path(source)
    paths = image_workspace(source).ensure()
    stem = workspace_json_stem(source)
    slug = filter_json_slug(normalize_preprocess_mode(preprocess_mode))
    return paths.json_root / f"{stem}_{slug}"


def canonicalize_generator_json_outputs(
    json_dir: str | Path,
    stem: str,
    slug: str,
) -> list[Path]:
    """Rename {stem}_{slug}.{N}.json and {stem}_{slug}.json to {stem}_{slug}_{N}.json."""
    from geometry_json import drawable_shape_count

    json_dir = Path(json_dir)
    if not json_dir.is_dir():
        return []

    prefix = f"{stem}_{slug}"
    renamed: list[Path] = []
    checkpoint_re = re.compile(rf"^{re.escape(prefix)}\.(\d+)\.json$", re.IGNORECASE)

    for path in sorted(json_dir.glob(f"{prefix}.*.json")):
        match = checkpoint_re.match(path.name)
        if not match:
            continue
        dest = json_dir / f"{prefix}_{match.group(1)}.json"
        if path.resolve() == dest.resolve():
            continue
        if dest.exists():
            dest.unlink()
        path.rename(dest)
        renamed.append(dest)

    final_src = json_dir / f"{prefix}.json"
    if not final_src.is_file():
        return renamed

    layer_count = drawable_shape_count(final_src)
    if layer_count <= 0:
        highest = 0
        for path in json_dir.glob(f"{prefix}_*.json"):
            match = re.match(rf"^{re.escape(prefix)}_(\d+)\.json$", path.name, re.IGNORECASE)
            if match:
                highest = max(highest, int(match.group(1)))
        layer_count = highest

    if layer_count <= 0:
        return renamed

    dest = json_dir / f"{prefix}_{layer_count}.json"
    if final_src.resolve() == dest.resolve():
        return renamed
    if dest.exists():
        dest.unlink()
    final_src.rename(dest)
    renamed.append(dest)
    return renamed


def generator_live_preview_path(source: str | Path) -> Path:
    return image_workspace(source).ensure().preview_generation


def legacy_preprocessed_path(source: str | Path, mode: str) -> Path:
    source = Path(source)
    mode_name = normalize_filter_mode(mode)
    if mode_name in ("", "none"):
        return source
    return source.with_name(f"{source.stem}.{mode_name}{source.suffix}")


def legacy_filter_preview_path(source: str | Path, mode: str) -> Path:
    source = Path(source)
    safe_stem = source.stem.replace(" ", "_")[:80] or "image"
    return LEGACY_FILTER_PREVIEW_DIR / f"{safe_stem}.{normalize_filter_mode(mode)}.png"


def text_vinyl_workspace(mode: str, identity: str) -> WorkspacePaths:
    workspace_id = text_vinyl_workspace_id(mode=mode, identity=identity)
    root = TEXT_VINYL_WORKSPACE_ROOT / workspace_id
    preview = root / "preview"
    return WorkspacePaths(
        kind="text_vinyl",
        workspace_id=workspace_id,
        root=root,
        manifest=root / "manifest.json",
        source=root / "source",
        variants=root / "variants",
        json_root=root / "json",
        json_finals=root / "json",
        json_checkpoints=root / "json" / "checkpoints",
        preview=preview,
        preview_filters=preview / "filters",
        preview_generation=preview / "json.render.png",
        cache=root / "cache",
        logs=root / "logs",
    )


def workspace_signature_path(paths: WorkspacePaths) -> Path:
    return paths.root / WORKSPACE_SIGNATURE_NAME


def _remove_workspace_signature_files(paths: WorkspacePaths) -> None:
    for name in (WORKSPACE_SIGNATURE_NAME, _LEGACY_WORKSPACE_SIGNATURE_NAME):
        candidate = paths.root / name
        if candidate.is_file():
            try:
                candidate.unlink()
            except OSError:
                pass


def write_workspace_signature(paths: WorkspacePaths) -> Path | None:
    """Write human-readable provenance at the workspace root (not inside JSON).

    Optional: only active when the fork UI preference module is present.
    Upstream 1.8.x builds omit that module and skip signatures silently.
    """
    try:
        from ui.workspace_signature_option import should_write_workspace_signature
    except ImportError:
        return None

    if not should_write_workspace_signature():
        _remove_workspace_signature_files(paths)
        return None

    try:
        from version import (
            APP_LINE_VERSION,
            GENERATOR_AUTHOR,
            REPOSITORY_URL,
        )
    except ImportError:
        return None

    paths.root.mkdir(parents=True, exist_ok=True)
    _remove_legacy_workspace_signature(paths)
    written_at = datetime.now(timezone.utc).isoformat()
    lines = [
        f"Generator Author: {GENERATOR_AUTHOR}",
        f"Repo Link: {REPOSITORY_URL}",
        f"Program Version: {APP_LINE_VERSION}",
        f"Workspace ID: {paths.workspace_id}",
        f"Workspace Kind: {paths.kind}",
        f"Written: {written_at}",
    ]
    destination = workspace_signature_path(paths)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination


def _remove_legacy_workspace_signature(paths: WorkspacePaths) -> None:
    legacy = paths.root / _LEGACY_WORKSPACE_SIGNATURE_NAME
    if legacy.is_file():
        try:
            legacy.unlink()
        except OSError:
            pass


def write_manifest(paths: WorkspacePaths, payload: dict) -> None:
    paths.ensure()
    body = dict(payload)
    body.setdefault("workspace_id", paths.workspace_id)
    body.setdefault("kind", paths.kind)
    body["updated_at"] = datetime.now(timezone.utc).isoformat()
    paths.manifest.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")


def read_manifest(paths: WorkspacePaths) -> dict | None:
    try:
        if not paths.manifest.is_file():
            return None
        payload = json.loads(paths.manifest.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def workspace_display_name(source: str | Path) -> str:
    """Human-readable filename for queue labels (prefer import name, not workspace copy)."""
    source = Path(source)
    paths = image_workspace(source)
    manifest = read_manifest(paths)
    if manifest:
        stem = _import_stem_from_manifest(paths, manifest)
        if stem:
            return _display_filename_for_stem(stem, source, paths)
    stem = workspace_id_display_stem(paths)
    if stem:
        return _display_filename_for_stem(stem, source, paths)
    return source.name


def workspace_source_stem(source: str | Path) -> str:
    """Filename stem used for variant files (manifest import name, else workspace id)."""
    source = Path(source)
    paths = image_workspace(source)
    manifest = read_manifest(paths)
    if manifest:
        stem = _import_stem_from_manifest(paths, manifest)
        if stem:
            return stem
    stem = workspace_id_display_stem(paths)
    if stem:
        return stem
    return safe_stem(source.stem)


def workspace_json_stem(source: str | Path) -> str:
    """Stem for generated JSON names (prefer import filename, not workspace copy)."""
    source = Path(source)
    paths = image_workspace(source)
    manifest = read_manifest(paths)
    if manifest:
        stem = _import_stem_from_manifest(paths, manifest)
        if stem:
            return stem
    stem = workspace_id_display_stem(paths)
    if stem:
        return stem
    return safe_stem(source.stem) or "image"


def iter_workspaces(kind: WorkspaceKind | None = None) -> list[WorkspacePaths]:
    kinds: Iterable[WorkspaceKind]
    if kind is None:
        kinds = ("image", "text_vinyl")
    else:
        kinds = (kind,)
    found: list[WorkspacePaths] = []
    for item_kind in kinds:
        root = workspace_root(item_kind)
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if item_kind == "image":
                paths = image_workspace(child / "source" / "placeholder.png")
                paths = WorkspacePaths(
                    kind="image",
                    workspace_id=child.name,
                    root=child,
                    manifest=child / "manifest.json",
                    source=child / "source",
                    variants=child / "variants",
                    json_root=child / "json",
                    json_finals=child / "json" / "finals",
                    json_checkpoints=child / "json" / "checkpoints",
                    preview=child / "preview",
                    preview_filters=child / "preview" / "filters",
                    preview_generation=child / "preview" / "generation.preview.png",
                    cache=child / "cache",
                    logs=child / "logs",
                )
            else:
                paths = WorkspacePaths(
                    kind="text_vinyl",
                    workspace_id=child.name,
                    root=child,
                    manifest=child / "manifest.json",
                    source=child / "source",
                    variants=child / "variants",
                    json_root=child / "json",
                    json_finals=child / "json",
                    json_checkpoints=child / "json" / "checkpoints",
                    preview=child / "preview",
                    preview_filters=child / "preview" / "filters",
                    preview_generation=child / "preview" / "json.render.png",
                    cache=child / "cache",
                    logs=child / "logs",
                )
            found.append(paths)
    return found


def folder_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except OSError:
                    continue
    except OSError:
        return total
    return total


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.2f} GB"


def _clear_directory(path: Path) -> int:
    removed = 0
    if not path.exists():
        return 0
    if path.is_file():
        try:
            path.unlink()
            return 1
        except OSError:
            return 0
    try:
        for child in list(path.iterdir()):
            if child.is_dir():
                removed += _clear_tree(child)
            else:
                try:
                    child.unlink()
                    removed += 1
                except OSError:
                    pass
    except OSError:
        pass
    return removed


def _clear_tree(path: Path) -> int:
    removed = 0
    if not path.exists():
        return 0
    if path.is_file():
        try:
            path.unlink()
            return 1
        except OSError:
            return 0
    try:
        for child in path.iterdir():
            removed += _clear_tree(child)
        path.rmdir()
        removed += 1
    except OSError:
        pass
    return removed


def clear_workspace_tier1(paths: WorkspacePaths) -> int:
    removed = 0
    removed += _clear_directory(paths.cache)
    removed += _clear_directory(paths.preview_filters)
    if paths.preview_generation.is_file():
        try:
            paths.preview_generation.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def clear_workspace_tier2(paths: WorkspacePaths) -> int:
    removed = 0
    removed += _clear_directory(paths.variants)
    removed += _clear_directory(paths.json_checkpoints)
    removed += _clear_directory(paths.logs)
    if paths.kind == "text_vinyl":
        for name in ("reference.png", "json.render.png"):
            candidate = paths.preview / name
            if candidate.is_file():
                try:
                    candidate.unlink()
                    removed += 1
                except OSError:
                    pass
    return removed


def clear_legacy_ephemeral() -> int:
    removed = 0
    removed += _clear_directory(LEGACY_GENERATOR_PREVIEW_DIR)
    return removed


def clear_legacy_session_cache() -> int:
    removed = _clear_directory(LEGACY_FILTER_PREVIEW_DIR)
    return removed


def clear_all_filter_previews(*, include_legacy: bool = True) -> int:
    removed = 0
    for paths in iter_workspaces(kind="image"):
        removed += _clear_directory(paths.preview_filters)
    if include_legacy:
        removed += clear_legacy_session_cache()
    return removed


def clear_all_tier1(*, include_legacy: bool = True) -> int:
    removed = 0
    for paths in iter_workspaces():
        removed += clear_workspace_tier1(paths)
    if include_legacy:
        removed += clear_legacy_ephemeral()
    return removed


def clear_all_tier2(*, include_legacy: bool = False) -> int:
    removed = 0
    for paths in iter_workspaces():
        removed += clear_workspace_tier2(paths)
    if include_legacy:
        removed += clear_legacy_session_cache()
    return removed


def remove_workspace(paths: WorkspacePaths) -> bool:
    if not paths.root.exists():
        return False
    try:
        shutil.rmtree(paths.root)
        return True
    except OSError:
        return False


def run_exit_cleanup(
    *,
    clear_ephemeral: bool,
    clear_session_cache: bool,
    clear_filter_previews: bool = True,
) -> tuple[int, int, int]:
    tier1 = clear_all_tier1(include_legacy=clear_ephemeral) if clear_ephemeral else 0
    tier2 = clear_all_tier2(include_legacy=False) if clear_session_cache else 0
    filters = clear_all_filter_previews(include_legacy=True) if clear_filter_previews else 0
    return tier1, tier2, filters


def json_search_roots(source: str | Path) -> list[Path]:
    source = Path(source)
    paths = image_workspace(source)
    roots = [
        paths.json_root,
        paths.json_finals,
        paths.json_checkpoints,
        generator_json_output_base(source),
        source.parent / source.stem,
        source.parent,
    ]
    seen: set[str] = set()
    ordered: list[Path] = []
    for root in roots:
        try:
            key = str(root.resolve()).lower()
        except OSError:
            key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(root)
    return ordered
