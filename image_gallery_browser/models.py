"""Core data models for Image Gallery Browser."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from image_gallery_browser.errors import ScanErrorType, ScanStage


@dataclass(frozen=True)
class GalleryConfig:
    """Store normalized application configuration."""

    projects_root: Path
    data_dir: Path
    gallery_label: str | None = None
    thumbnail_size: tuple[int, int] = (320, 320)
    supported_extensions: frozenset[str] = field(
        default_factory=lambda: frozenset({".jpg", ".jpeg", ".png", ".webp"})
    )
    auto_scan_on_empty: bool = True
    max_images_per_view: int = 200
    show_diagnostics: bool = False


@dataclass(frozen=True)
class FolderRecord:
    """Represent a folder discovered under the configured root."""

    relative_path: str
    name: str
    parent_relative_path: str | None
    depth: int


@dataclass(frozen=True)
class ImageRecord:
    """Represent indexed image metadata."""

    source_relative_path: str
    folder_relative_path: str
    filename: str
    extension: str
    file_size: int
    modified_time: float
    width: int | None = None
    height: int | None = None
    thumbnail_relative_path: str | None = None
    status: str = "active"


@dataclass(frozen=True)
class ScanErrorRecord:
    """Represent a recoverable scan error."""

    stage: ScanStage
    error_type: ScanErrorType
    relative_path: str | None
    message: str


@dataclass(frozen=True)
class ScanSummary:
    """Represent aggregate scan results."""

    total_files_seen: int = 0
    images_added: int = 0
    images_updated: int = 0
    images_skipped: int = 0
    images_missing: int = 0
    errors: tuple[ScanErrorRecord, ...] = ()

    @property
    def errors_count(self) -> int:
        return len(self.errors)


@dataclass(frozen=True)
class ScanRecord:
    """Represent persisted scan metadata."""

    id: int
    status: str
    started_at: str
    finished_at: str | None
    total_files_seen: int
    images_added: int
    images_updated: int
    images_skipped: int
    images_missing: int
    errors_count: int


@dataclass(frozen=True)
class FilesystemScanResult:
    """Represent discovered filesystem records before persistence."""

    folders: tuple[FolderRecord, ...] = ()
    images: tuple[ImageRecord, ...] = ()
    total_files_seen: int = 0
    errors: tuple[ScanErrorRecord, ...] = ()

    @property
    def errors_count(self) -> int:
        return len(self.errors)
