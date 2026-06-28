"""Record conversion helpers for SQLite persistence."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

from image_gallery_browser.errors import ScanErrorType, ScanStage
from image_gallery_browser.models import FolderRecord, ImageRecord, ScanErrorRecord

ImageUpsertAction = Literal["added", "updated", "skipped"]


@dataclass(frozen=True)
class ImageUpsertResult:
    """Represent the persistence result for one indexed image."""

    image_id: int
    action: ImageUpsertAction


def folder_record_from_row(row: sqlite3.Row) -> FolderRecord:
    """Build a folder domain record from a SQLite row."""
    return FolderRecord(
        relative_path=str(row["relative_path"]),
        name=str(row["name"]),
        parent_relative_path=row["parent_relative_path"],
        depth=int(row["depth"]),
    )


def image_record_from_row(row: sqlite3.Row) -> ImageRecord:
    """Build an image domain record from a SQLite row."""
    return ImageRecord(
        source_relative_path=str(row["source_relative_path"]),
        folder_relative_path=str(row["folder_relative_path"]),
        filename=str(row["filename"]),
        extension=str(row["extension"]),
        file_size=int(row["file_size"]),
        modified_time=float(row["modified_time"]),
        width=row["width"],
        height=row["height"],
        thumbnail_relative_path=row["thumbnail_relative_path"],
        status=str(row["status"]),
    )


def image_upsert_action(
    existing: sqlite3.Row,
    image: ImageRecord,
    folder_id: int,
) -> ImageUpsertAction:
    """Classify one image write against an existing database row."""
    if (
        int(existing["folder_id"]) == folder_id
        and int(existing["file_size"]) == image.file_size
        and float(existing["modified_time"]) == image.modified_time
        and existing["width"] == image.width
        and existing["height"] == image.height
        and existing["thumbnail_relative_path"] == image.thumbnail_relative_path
        and existing["status"] == "active"
    ):
        return "skipped"
    return "updated"


def scan_error_record_from_row(row: sqlite3.Row) -> ScanErrorRecord:
    """Build a scan error domain record from a SQLite row."""
    return ScanErrorRecord(
        stage=ScanStage(str(row["stage"])),
        relative_path=row["relative_path"],
        error_type=ScanErrorType(str(row["error_type"])),
        message=str(row["message"]),
    )
