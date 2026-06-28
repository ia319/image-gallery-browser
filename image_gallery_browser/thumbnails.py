"""Pillow thumbnail generation and cache helpers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

from PIL import Image, ImageOps, UnidentifiedImageError

from image_gallery_browser.errors import ScanErrorType, ScanStage
from image_gallery_browser.models import ImageRecord, ScanErrorRecord

THUMBNAIL_DIR_NAME = "thumbnails"
THUMBNAIL_EXTENSION = ".png"
THUMBNAIL_FORMAT = "PNG"


@dataclass(frozen=True)
class ThumbnailResult:
    """Represent a thumbnail operation result for one image."""

    image: ImageRecord | None
    generated: bool = False
    error: ScanErrorRecord | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def process_image_thumbnail(
    image: ImageRecord,
    projects_root: str | Path,
    data_dir: str | Path,
    thumbnail_size: tuple[int, int],
) -> ThumbnailResult:
    """Read image dimensions and ensure a cached thumbnail exists."""
    try:
        source_path = source_image_path(projects_root, image.source_relative_path)
    except ValueError as exc:
        return _error_result(
            image,
            ScanStage.PATH,
            ScanErrorType.INVALID_PATH,
            exc,
        )

    thumbnail_relative = thumbnail_relative_path(image.source_relative_path)
    thumbnail_path = thumbnail_cache_path(data_dir, thumbnail_relative)

    loaded_image_result = _load_image(source_path, image.source_relative_path)
    if isinstance(loaded_image_result, ScanErrorRecord):
        return ThumbnailResult(image=None, error=loaded_image_result)

    loaded_image = loaded_image_result
    try:
        width, height = loaded_image.size
        generated = False
        if not is_thumbnail_cache_valid(thumbnail_path, image.modified_time):
            _write_thumbnail(loaded_image, thumbnail_path, thumbnail_size)
            generated = True
    except (OSError, ValueError) as exc:
        return _error_result(
            image,
            ScanStage.THUMBNAIL,
            ScanErrorType.THUMBNAIL_FAILED,
            exc,
        )
    finally:
        loaded_image.close()

    return ThumbnailResult(
        image=replace(
            image,
            width=width,
            height=height,
            thumbnail_relative_path=thumbnail_relative,
        ),
        generated=generated,
    )


def read_image_size(source_path: str | Path) -> tuple[int, int]:
    """Return display-oriented image dimensions."""
    image = _open_oriented_copy(Path(source_path))
    try:
        return image.size
    finally:
        image.close()


def thumbnail_cache_key(source_relative_path: str) -> str:
    """Return a stable cache key for a source-relative image path."""
    normalized = _normalize_source_relative_path(source_relative_path)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def thumbnail_relative_path(source_relative_path: str) -> str:
    """Return the POSIX relative thumbnail cache path for one image."""
    return (
        f"{THUMBNAIL_DIR_NAME}/"
        f"{thumbnail_cache_key(source_relative_path)}{THUMBNAIL_EXTENSION}"
    )


def thumbnail_cache_path(data_dir: str | Path, thumbnail_relative: str) -> Path:
    """Return an absolute thumbnail cache path under the application data dir."""
    relative = PurePosixPath(thumbnail_relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"invalid thumbnail relative path: {thumbnail_relative}")
    return Path(data_dir).joinpath(*relative.parts)


def source_image_path(projects_root: str | Path, source_relative_path: str) -> Path:
    """Return an absolute source path from a POSIX relative image path."""
    relative = PurePosixPath(_normalize_source_relative_path(source_relative_path))
    if relative.is_absolute() or ".." in relative.parts or relative.parts == (".",):
        raise ValueError(f"invalid source relative path: {source_relative_path}")
    return Path(projects_root).joinpath(*relative.parts)


def is_thumbnail_cache_valid(
    thumbnail_path: str | Path,
    source_modified_time: float,
) -> bool:
    """Return whether an existing thumbnail is newer than the source image."""
    path = Path(thumbnail_path)
    try:
        return path.exists() and path.stat().st_mtime >= source_modified_time
    except OSError:
        return False


def _load_image(
    source_path: Path,
    source_relative_path: str,
) -> Image.Image | ScanErrorRecord:
    try:
        return _open_oriented_copy(source_path)
    except UnidentifiedImageError as exc:
        return _scan_error(
            source_relative_path,
            ScanStage.IMAGE_OPEN,
            ScanErrorType.CORRUPT_IMAGE,
            exc,
        )
    except PermissionError as exc:
        return _scan_error(
            source_relative_path,
            ScanStage.IMAGE_OPEN,
            ScanErrorType.PERMISSION_DENIED,
            exc,
        )
    except OSError as exc:
        return _scan_error(
            source_relative_path,
            ScanStage.IMAGE_OPEN,
            ScanErrorType.UNKNOWN_ERROR,
            exc,
        )


def _open_oriented_copy(source_path: Path) -> Image.Image:
    with Image.open(source_path) as opened:
        oriented = ImageOps.exif_transpose(opened)
        try:
            return oriented.copy()
        finally:
            if oriented is not opened:
                oriented.close()


def _write_thumbnail(
    image: Image.Image,
    thumbnail_path: Path,
    thumbnail_size: tuple[int, int],
) -> None:
    width, height = _validate_thumbnail_size(thumbnail_size)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail = _png_compatible_image(image)
    try:
        thumbnail.thumbnail((width, height), Image.Resampling.LANCZOS)
        thumbnail.save(thumbnail_path, format=THUMBNAIL_FORMAT)
    finally:
        thumbnail.close()


def _png_compatible_image(image: Image.Image) -> Image.Image:
    copied = image.copy()
    if copied.mode in {"RGB", "RGBA"}:
        return copied
    if "A" in copied.getbands() or copied.mode in {"LA", "PA"}:
        converted = copied.convert("RGBA")
    else:
        converted = copied.convert("RGB")
    copied.close()
    return converted


def _validate_thumbnail_size(thumbnail_size: tuple[int, int]) -> tuple[int, int]:
    if (
        not isinstance(thumbnail_size, tuple)
        or len(thumbnail_size) != 2
        or not all(isinstance(value, int) and value > 0 for value in thumbnail_size)
    ):
        raise ValueError("thumbnail_size must contain two positive integers")
    return thumbnail_size


def _normalize_source_relative_path(source_relative_path: str) -> str:
    normalized = PurePosixPath(source_relative_path).as_posix().strip("/")
    if not normalized or normalized == "." or ".." in PurePosixPath(normalized).parts:
        raise ValueError("source_relative_path must be a safe POSIX relative path")
    return normalized


def _error_result(
    image: ImageRecord,
    stage: ScanStage,
    error_type: ScanErrorType,
    exc: Exception,
) -> ThumbnailResult:
    return ThumbnailResult(
        image=None,
        error=_scan_error(image.source_relative_path, stage, error_type, exc),
    )


def _scan_error(
    source_relative_path: str,
    stage: ScanStage,
    error_type: ScanErrorType,
    exc: Exception,
) -> ScanErrorRecord:
    return ScanErrorRecord(
        stage=stage,
        error_type=error_type,
        relative_path=source_relative_path,
        message=str(exc),
    )
