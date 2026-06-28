"""Configuration loading and normalization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from image_gallery_browser.errors import ConfigError
from image_gallery_browser.models import GalleryConfig
from image_gallery_browser.paths import resolve_path

DEFAULT_CONFIG_PATH = Path("config.example.json")
DEFAULT_THUMBNAIL_SIZE = (320, 320)
DEFAULT_SUPPORTED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
DEFAULT_MAX_IMAGES_PER_VIEW = 200


def load_config(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    *,
    project_dir: Path | None = None,
) -> GalleryConfig:
    """Load JSON configuration and apply normalized defaults."""
    base_dir = project_dir or Path.cwd()
    path = resolve_path(config_path, base_dir)
    try:
        raw_config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"configuration file contains invalid JSON: {path}") from exc

    if not isinstance(raw_config, dict):
        raise ConfigError("configuration root must be a JSON object")

    return parse_config(raw_config, base_dir=path.parent)


def parse_config(raw_config: dict[str, Any], *, base_dir: Path) -> GalleryConfig:
    """Normalize raw JSON configuration values."""
    projects_root = resolve_path(
        _get_string(raw_config, "projects_root", "sample_projects"), base_dir
    )
    data_dir = resolve_path(_get_string(raw_config, "data_dir", "data"), base_dir)
    _reject_nested_data_dir(projects_root, data_dir)
    gallery_label = _get_optional_string(raw_config, "gallery_label")
    thumbnail_size = _parse_thumbnail_size(
        raw_config.get("thumbnail_size", DEFAULT_THUMBNAIL_SIZE)
    )
    supported_extensions = _parse_extensions(
        raw_config.get("supported_extensions", DEFAULT_SUPPORTED_EXTENSIONS)
    )
    auto_scan_on_empty = _get_bool(raw_config, "auto_scan_on_empty", True)
    max_images_per_view = _get_positive_int(
        raw_config, "max_images_per_view", DEFAULT_MAX_IMAGES_PER_VIEW
    )
    show_diagnostics = _get_bool(raw_config, "show_diagnostics", False)

    return GalleryConfig(
        projects_root=projects_root,
        data_dir=data_dir,
        gallery_label=gallery_label,
        thumbnail_size=thumbnail_size,
        supported_extensions=supported_extensions,
        auto_scan_on_empty=auto_scan_on_empty,
        max_images_per_view=max_images_per_view,
        show_diagnostics=show_diagnostics,
    )


def _get_string(raw_config: dict[str, Any], key: str, default: str) -> str:
    value = raw_config.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} must be a non-empty string")
    return value


def _get_optional_string(raw_config: dict[str, Any], key: str) -> str | None:
    value = raw_config.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} must be a non-empty string when provided")
    return value.strip()


def _get_bool(raw_config: dict[str, Any], key: str, default: bool) -> bool:
    value = raw_config.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be a boolean")
    return value


def _get_positive_int(raw_config: dict[str, Any], key: str, default: int) -> int:
    value = raw_config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{key} must be a positive integer")
    return value


def _parse_thumbnail_size(value: Any) -> tuple[int, int]:
    if (
        not isinstance(value, list | tuple)
        or len(value) != 2
        or not all(_is_positive_int(item) for item in value)
    ):
        raise ConfigError("thumbnail_size must contain two positive integers")
    return (value[0], value[1])


def _reject_nested_data_dir(projects_root: Path, data_dir: Path) -> None:
    try:
        data_dir.relative_to(projects_root)
    except ValueError:
        return
    raise ConfigError("data_dir must be outside projects_root")


def _is_positive_int(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value > 0


def _parse_extensions(value: Any) -> frozenset[str]:
    if not isinstance(value, list | tuple | set | frozenset) or not value:
        raise ConfigError("supported_extensions must be a non-empty list")

    extensions = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ConfigError("supported_extensions entries must be strings")
        normalized = item.strip().lower()
        if not normalized.startswith("."):
            normalized = f".{normalized}"
        extensions.append(normalized)

    return frozenset(extensions)
