"""Path normalization helpers for gallery roots and indexed files."""

from __future__ import annotations

import os
from pathlib import Path

from image_gallery_browser.errors import PathBoundaryError

ROOT_RELATIVE_PATH = "."


def resolve_path(path: str | Path, base_dir: Path | None = None) -> Path:
    """Resolve a configured path without requiring it to exist."""
    candidate = Path(path).expanduser()
    if not candidate.is_absolute() and base_dir is not None:
        candidate = base_dir / candidate
    return candidate.resolve(strict=False)


def is_unc_path(path: str | Path) -> bool:
    """Detect Windows UNC paths without touching the filesystem."""
    value = str(path)
    return value.startswith("\\\\") or value.startswith("//")


def to_posix_relative_path(path: str | Path) -> str:
    """Normalize an existing relative path value for database storage."""
    normalized = Path(path).as_posix().strip("/")
    return normalized or ROOT_RELATIVE_PATH


def relative_to_root(path: str | Path, root: str | Path) -> str:
    """Return a POSIX path relative to the configured gallery root."""
    resolved_root = resolve_path(root)
    resolved_path = resolve_path(path)

    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        if not _is_within_root(resolved_path, resolved_root):
            raise PathBoundaryError(
                f"path is outside the configured root: {resolved_path}"
            ) from exc
        relative = Path(os.path.relpath(resolved_path, resolved_root))

    return to_posix_relative_path(relative)


def folder_relative_path_for_image(source_relative_path: str) -> str:
    """Return the containing folder path for an indexed image."""
    parent = Path(source_relative_path).parent.as_posix()
    return parent if parent != "." else ROOT_RELATIVE_PATH


def _is_within_root(path: Path, root: Path) -> bool:
    normalized_path = os.path.normcase(os.path.abspath(path))
    normalized_root = os.path.normcase(os.path.abspath(root))
    common = os.path.commonpath([normalized_path, normalized_root])
    return common == normalized_root
