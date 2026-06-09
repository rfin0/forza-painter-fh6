"""Central security limits and validation for forza-painter FH6."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse


# --- Geometry JSON ---
MAX_GEOMETRY_JSON_BYTES = 64 * 1024 * 1024
MAX_GEOMETRY_SHAPES = 4000
MAX_IMAGE_DIMENSION = 8192

# --- Process memory ---
MIN_USER_ADDRESS = 0x10000
MAX_USER_ADDRESS = 0x7FFFFFFFFFFF
MIN_TEMPLATE_LAYER_COUNT = 100
MAX_TEMPLATE_LAYER_COUNT = 3000
MAX_MEMORY_READ_BYTES = 64 * 1024 * 1024
MAX_LAYER_BLOB_BYTES = 0x400

# --- Session / network ---
SESSION_SCHEMA = "fh6_session_location_v1"
ALLOWED_FETCH_HOSTS = frozenset({"api.github.com", "raw.githubusercontent.com"})
GITHUB_RELEASES_API = "https://api.github.com/repos/ShepherdHL/forza-painter-fh6/releases/latest"

_HEX_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]+$|^[0-9a-fA-F]+$")


def updates_enabled() -> bool:
    try:
        from build_profile import networking_disabled

        if networking_disabled():
            return False
    except Exception:
        pass
    value = os.environ.get("FORZA_PAINTER_CHECK_UPDATES", "").strip().lower()
    return value in ("1", "true", "yes", "on")


def trusted_locator_allowed() -> bool:
    """Addresses produced by the app's validated auto-locate session."""
    value = os.environ.get("FORZA_PAINTER_TRUSTED_LOCATOR", "").strip().lower()
    return value in ("1", "true", "yes", "on")


def manual_addresses_allowed() -> bool:
    value = os.environ.get("FORZA_PAINTER_ALLOW_MANUAL_ADDRESSES", "").strip().lower()
    return value in ("1", "true", "yes", "on")


def memory_addresses_allowed() -> bool:
    return trusted_locator_allowed() or manual_addresses_allowed()


def log_redaction_enabled() -> bool:
    value = os.environ.get("FORZA_PAINTER_REDACT_LOGS", "1").strip().lower()
    return value not in ("0", "false", "no", "off")


def is_user_address(address: int) -> bool:
    return MIN_USER_ADDRESS <= int(address) <= MAX_USER_ADDRESS


def validate_user_address(address: Any, label: str = "address") -> int:
    try:
        value = int(address, 0) if not isinstance(address, int) else int(address)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {label}: {address!r}") from exc
    if not is_user_address(value):
        raise ValueError(f"{label} 0x{value:x} is outside the allowed user-mode range")
    return value


def validate_template_layer_count(layer_count: Any) -> int:
    try:
        value = int(layer_count)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid template layer count: {layer_count!r}") from exc
    if not MIN_TEMPLATE_LAYER_COUNT <= value <= MAX_TEMPLATE_LAYER_COUNT:
        raise ValueError(
            f"Template layer count must be between {MIN_TEMPLATE_LAYER_COUNT} "
            f"and {MAX_TEMPLATE_LAYER_COUNT}, got {value}"
        )
    return value


def validate_geometry_path(path: Any) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"Geometry file not found: {resolved}")
    size = resolved.stat().st_size
    if size > MAX_GEOMETRY_JSON_BYTES:
        raise ValueError(
            f"Geometry file is too large ({size} bytes; limit {MAX_GEOMETRY_JSON_BYTES})"
        )
    return resolved


def validate_fetch_url(url: str) -> str:
    try:
        from build_profile import networking_disabled

        if networking_disabled():
            raise ValueError("Networking is disabled for this build profile")
    except ValueError:
        raise
    except Exception:
        pass
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Only HTTPS URLs are allowed (got {url!r})")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_FETCH_HOSTS:
        raise ValueError(f"URL host {host!r} is not on the fetch allowlist")
    return url


def validate_fh6_session(session: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    if not session or not isinstance(session, dict):
        return False, "missing session"
    if session.get("type") != SESSION_SCHEMA:
        return False, "invalid session type"
    try:
        pid = int(session["pid"])
        layer_count = validate_template_layer_count(session["layer_count"])
        count_address = validate_user_address(session["count_address"], "count_address")
        table_address = validate_user_address(session["table_address"], "table_address")
    except (KeyError, TypeError, ValueError) as exc:
        return False, str(exc)
    if pid <= 0:
        return False, "invalid pid"
    score = session.get("score")
    if score is not None:
        try:
            if float(score) <= 0:
                return False, "invalid locator score"
        except (TypeError, ValueError):
            return False, "invalid locator score"
    _ = layer_count, count_address, table_address
    return True, ""


def parse_safe_hex_address(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return None
    if not _HEX_ADDRESS_RE.match(text):
        raise ValueError(f"Invalid memory address format: {text!r}")
    return validate_user_address(text, "memory address")


def redact_sensitive_log_text(text: str) -> str:
    if not log_redaction_enabled() or not text:
        return text
    redacted = re.sub(r"0x[0-9a-fA-F]{4,}", "0x<redacted>", text)
    redacted = re.sub(r"\bpid[=\s]+\d+\b", "pid=<redacted>", redacted, flags=re.I)
    return redacted


def load_geometry_json_text(path: Path) -> Any:
    validate_geometry_path(path)
    raw = path.read_text(encoding="utf-8")
    if len(raw.encode("utf-8")) > MAX_GEOMETRY_JSON_BYTES:
        raise ValueError("Geometry file exceeds size limit")
    return json.loads(raw)
