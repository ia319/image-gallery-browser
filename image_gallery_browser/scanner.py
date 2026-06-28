"""Discover gallery folders and image files from the filesystem."""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from pathlib import Path, PurePosixPath
from stat import S_ISDIR, S_ISREG

from image_gallery_browser.errors import (
    PathBoundaryError,
    ScanErrorType,
    ScanStage,
)
from image_gallery_browser.models import (
    FilesystemScanResult,
    FolderRecord,
    ImageRecord,
    ScanErrorRecord,
)
from image_gallery_browser.paths import (
    ROOT_RELATIVE_PATH,
    folder_relative_path_for_image,
    relative_to_root,
    resolve_path,
)


def scan_gallery_root(
    root: str | Path,
    supported_extensions: Iterable[str],
) -> FilesystemScanResult:
    """Scan a gallery root and return normalized filesystem records."""
    resolved_root = resolve_path(root)
    extensions = _normalize_extensions(supported_extensions)
    folders: list[FolderRecord] = []
    images: list[ImageRecord] = []
    errors: list[ScanErrorRecord] = []

    root_error = _validate_root(resolved_root)
    if root_error is not None:
        return FilesystemScanResult(errors=(root_error,))

    folders.append(_build_folder_record(resolved_root, resolved_root))
    total_files_seen = _scan_directory(
        resolved_root,
        resolved_root,
        extensions,
        folders,
        images,
        errors,
    )

    return FilesystemScanResult(
        folders=tuple(folders),
        images=tuple(images),
        total_files_seen=total_files_seen,
        errors=tuple(errors),
    )


def _scan_directory(
    directory: Path,
    root: Path,
    supported_extensions: frozenset[str],
    folders: list[FolderRecord],
    images: list[ImageRecord],
    errors: list[ScanErrorRecord],
) -> int:
    total_files_seen = 0

    try:
        entries = _iter_directory(directory)
        for entry in entries:
            total_files_seen += _scan_entry(
                entry,
                root,
                supported_extensions,
                folders,
                images,
                errors,
            )
    except PermissionError as exc:
        errors.append(
            _build_scan_error(directory, root, ScanErrorType.PERMISSION_DENIED, exc)
        )
    except OSError as exc:
        errors.append(
            _build_scan_error(directory, root, ScanErrorType.UNKNOWN_ERROR, exc)
        )

    return total_files_seen


def _scan_entry(
    entry: Path,
    root: Path,
    supported_extensions: frozenset[str],
    folders: list[FolderRecord],
    images: list[ImageRecord],
    errors: list[ScanErrorRecord],
) -> int:
    try:
        path_stat = _stat_path(entry)
    except PermissionError as exc:
        errors.append(
            _build_scan_error(entry, root, ScanErrorType.PERMISSION_DENIED, exc)
        )
        return 0
    except OSError as exc:
        errors.append(_build_scan_error(entry, root, ScanErrorType.UNKNOWN_ERROR, exc))
        return 0

    # Avoid following symlinks so directory traversal cannot loop or leave the root.
    if S_ISDIR(path_stat.st_mode):
        try:
            folders.append(_build_folder_record(entry, root))
        except PathBoundaryError as exc:
            errors.append(_build_path_error(entry, root, exc))
            return 0
        return _scan_directory(
            entry,
            root,
            supported_extensions,
            folders,
            images,
            errors,
        )

    if not S_ISREG(path_stat.st_mode):
        return 0

    if entry.suffix.lower() in supported_extensions:
        try:
            source_relative_path = relative_to_root(entry, root)
        except PathBoundaryError as exc:
            errors.append(_build_path_error(entry, root, exc))
            return 1

        images.append(
            ImageRecord(
                source_relative_path=source_relative_path,
                folder_relative_path=folder_relative_path_for_image(
                    source_relative_path
                ),
                filename=entry.name,
                extension=entry.suffix.lower(),
                file_size=path_stat.st_size,
                modified_time=path_stat.st_mtime,
            )
        )

    return 1


def _build_folder_record(path: Path, root: Path) -> FolderRecord:
    relative_path = relative_to_root(path, root)
    return FolderRecord(
        relative_path=relative_path,
        name=_folder_name(path, relative_path),
        parent_relative_path=_parent_relative_path(relative_path),
        depth=_folder_depth(relative_path),
    )


def _validate_root(root: Path) -> ScanErrorRecord | None:
    try:
        if not root.exists():
            return _build_scan_error(
                root,
                root,
                ScanErrorType.INVALID_PATH,
                ValueError("gallery root does not exist"),
            )
        if not root.is_dir():
            return _build_scan_error(
                root,
                root,
                ScanErrorType.INVALID_PATH,
                ValueError("gallery root is not a directory"),
            )
    except PermissionError as exc:
        return _build_scan_error(root, root, ScanErrorType.PERMISSION_DENIED, exc)
    except OSError as exc:
        return _build_scan_error(root, root, ScanErrorType.UNKNOWN_ERROR, exc)

    return None


def _build_scan_error(
    path: Path,
    root: Path,
    error_type: ScanErrorType,
    exc: Exception,
) -> ScanErrorRecord:
    return ScanErrorRecord(
        stage=ScanStage.SCAN,
        error_type=error_type,
        relative_path=_safe_relative_path(path, root),
        message=str(exc),
    )


def _build_path_error(path: Path, root: Path, exc: Exception) -> ScanErrorRecord:
    return ScanErrorRecord(
        stage=ScanStage.PATH,
        error_type=ScanErrorType.INVALID_PATH,
        relative_path=_safe_relative_path(path, root),
        message=str(exc),
    )


def _safe_relative_path(path: Path, root: Path) -> str | None:
    try:
        return relative_to_root(path, root)
    except PathBoundaryError:
        return None


def _folder_name(path: Path, relative_path: str) -> str:
    if relative_path == ROOT_RELATIVE_PATH:
        return path.name or str(path)
    return path.name


def _parent_relative_path(relative_path: str) -> str | None:
    if relative_path == ROOT_RELATIVE_PATH:
        return None

    parent = PurePosixPath(relative_path).parent.as_posix()
    return parent if parent != "." else ROOT_RELATIVE_PATH


def _folder_depth(relative_path: str) -> int:
    if relative_path == ROOT_RELATIVE_PATH:
        return 0
    return len(PurePosixPath(relative_path).parts)


def _normalize_extensions(supported_extensions: Iterable[str]) -> frozenset[str]:
    extensions = set()
    for extension in supported_extensions:
        normalized = extension.strip().lower()
        if not normalized:
            continue
        if not normalized.startswith("."):
            normalized = f".{normalized}"
        extensions.add(normalized)
    return frozenset(extensions)


def _iter_directory(directory: Path) -> Iterator[Path]:
    return directory.iterdir()


def _stat_path(path: Path) -> os.stat_result:
    return path.stat(follow_symlinks=False)
