"""Application service layer for gallery scans and reads."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from image_gallery_browser.database import GalleryDatabase
from image_gallery_browser.errors import ScanErrorType, ScanStage
from image_gallery_browser.models import (
    FilesystemScanResult,
    FolderRecord,
    GalleryConfig,
    ImageRecord,
    ScanErrorRecord,
    ScanRecord,
    ScanSummary,
)
from image_gallery_browser.scanner import scan_gallery_root
from image_gallery_browser.thumbnails import (
    ThumbnailResult,
    process_image_thumbnail,
    source_image_path,
    thumbnail_cache_path,
)

DATABASE_FILENAME = "gallery.sqlite3"

ScanFunction = Callable[[str | Path, Iterable[str]], FilesystemScanResult]
ThumbnailFunction = Callable[
    [ImageRecord, str | Path, str | Path, tuple[int, int]],
    ThumbnailResult,
]


@dataclass(frozen=True)
class ImageQueryResult:
    """Represent a bounded image listing for the UI."""

    images: tuple[ImageRecord, ...]
    limit: int
    truncated: bool = False


def default_database_path(data_dir: str | Path) -> Path:
    """Return the default SQLite database path under the data directory."""
    return Path(data_dir) / DATABASE_FILENAME


class GalleryService:
    """Coordinate scans, thumbnail processing, persistence, and reads."""

    def __init__(
        self,
        config: GalleryConfig,
        *,
        database: GalleryDatabase | None = None,
        scan_func: ScanFunction = scan_gallery_root,
        thumbnail_func: ThumbnailFunction = process_image_thumbnail,
    ) -> None:
        self.config = config
        self.database_path = default_database_path(config.data_dir)
        self.database = database or GalleryDatabase(self.database_path)
        self._owns_database = database is None
        self._scan_func = scan_func
        self._thumbnail_func = thumbnail_func
        self.root_id = self.database.upsert_root(config.projects_root)

    def __enter__(self) -> GalleryService:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: object,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the owned database connection."""
        if self._owns_database:
            self.database.close()

    def scan_on_empty(self) -> ScanSummary | None:
        """Run the initial scan when configuration and database state allow it."""
        if not self.config.auto_scan_on_empty or not self.is_empty():
            return None
        return self.rescan()

    def is_empty(self) -> bool:
        """Return whether this root has no indexed folders or images."""
        return not self.database.list_folders(
            self.root_id
        ) and not self.database.list_images(self.root_id, limit=1)

    def rescan(self) -> ScanSummary:
        """Scan the configured root and persist the resulting index changes."""
        scan_id = self.database.start_scan(self.root_id)
        try:
            scan_result = self._scan_func(
                self.config.projects_root,
                self.config.supported_extensions,
            )
        except Exception as exc:
            return self._fail_scan(scan_id, ScanStage.SCAN, exc)

        try:
            summary = self._persist_scan_result(scan_id, scan_result)
        except Exception as exc:
            return self._fail_scan(scan_id, ScanStage.DATABASE, exc)

        self.database.finish_scan(scan_id, summary)
        return summary

    def list_folders(self) -> tuple[FolderRecord, ...]:
        """Return active folders for the configured root."""
        return self.database.list_folders(self.root_id)

    def list_images(
        self,
        *,
        folder_relative_path: str = ".",
        search: str | None = None,
    ) -> ImageQueryResult:
        """Return active images with one extra row for truncation detection."""
        limit = self.config.max_images_per_view
        images = self.database.list_images(
            self.root_id,
            folder_relative_path=folder_relative_path,
            search=search,
            limit=limit + 1,
        )
        truncated = len(images) > limit
        return ImageQueryResult(
            images=images[:limit],
            limit=limit,
            truncated=truncated,
        )

    def latest_scan(self) -> ScanRecord | None:
        """Return the latest scan metadata for the configured root."""
        return self.database.get_latest_scan(self.root_id)

    def list_scan_errors(self, scan_id: int) -> tuple[ScanErrorRecord, ...]:
        """Return persisted recoverable errors for one scan."""
        return self.database.list_scan_errors(scan_id)

    def source_path(self, image: ImageRecord) -> Path:
        """Return the absolute source path for an indexed image."""
        return source_image_path(self.config.projects_root, image.source_relative_path)

    def thumbnail_path(self, image: ImageRecord) -> Path | None:
        """Return the absolute thumbnail path when the image has a cache entry."""
        if image.thumbnail_relative_path is None:
            return None
        return thumbnail_cache_path(self.config.data_dir, image.thumbnail_relative_path)

    def _persist_scan_result(
        self,
        scan_id: int,
        scan_result: FilesystemScanResult,
    ) -> ScanSummary:
        errors = list(scan_result.errors)
        active_folder_paths = {folder.relative_path for folder in scan_result.folders}
        active_image_paths = {
            image.source_relative_path for image in scan_result.images
        }
        counts = {"added": 0, "updated": 0, "skipped": 0}

        for folder in scan_result.folders:
            self.database.upsert_folder(self.root_id, folder)

        for image in scan_result.images:
            result = self._process_image(image)
            if result.error is not None:
                errors.append(result.error)
                self._persist_error_image(scan_id, image)
                continue
            if result.image is None:
                continue
            upsert_result = self.database.upsert_image(
                self.root_id,
                result.image,
                scan_id,
            )
            counts[upsert_result.action] += 1

        missing_images = self.database.mark_missing_images(
            self.root_id,
            active_image_paths,
        )
        self.database.mark_missing_folders(self.root_id, active_folder_paths)

        summary = ScanSummary(
            total_files_seen=scan_result.total_files_seen,
            images_added=counts["added"],
            images_updated=counts["updated"],
            images_skipped=counts["skipped"],
            images_missing=missing_images,
            errors=tuple(errors),
        )

        for error in summary.errors:
            self.database.add_scan_error(scan_id, error)

        return summary

    def _process_image(self, image: ImageRecord) -> ThumbnailResult:
        try:
            return self._thumbnail_func(
                image,
                self.config.projects_root,
                self.config.data_dir,
                self.config.thumbnail_size,
            )
        except Exception as exc:
            return ThumbnailResult(
                image=None,
                error=ScanErrorRecord(
                    stage=ScanStage.THUMBNAIL,
                    error_type=ScanErrorType.UNKNOWN_ERROR,
                    relative_path=image.source_relative_path,
                    message=str(exc),
                ),
            )

    def _persist_error_image(self, scan_id: int, image: ImageRecord) -> None:
        self.database.upsert_image(self.root_id, image, scan_id)
        self.database.mark_image_error(
            self.root_id,
            image.source_relative_path,
            scan_id,
        )

    def _fail_scan(
        self,
        scan_id: int,
        stage: ScanStage,
        exc: Exception,
    ) -> ScanSummary:
        error = ScanErrorRecord(
            stage=stage,
            error_type=ScanErrorType.UNKNOWN_ERROR,
            relative_path=None,
            message=str(exc),
        )
        self.database.add_scan_error(scan_id, error)
        self.database.fail_scan(scan_id, errors_count=1)
        return ScanSummary(errors=(error,))
