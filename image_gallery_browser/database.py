"""SQLite persistence layer for indexed gallery data."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from image_gallery_browser.models import (
    FolderRecord,
    ImageRecord,
    ScanErrorRecord,
    ScanSummary,
)
from image_gallery_browser.paths import ROOT_RELATIVE_PATH, resolve_path

SCHEMA_VERSION = "1"
ImageUpsertAction = Literal["added", "updated", "skipped"]


@dataclass(frozen=True)
class ImageUpsertResult:
    """Represent the persistence result for one indexed image."""

    image_id: int
    action: ImageUpsertAction


class GalleryDatabase:
    """Manage SQLite schema, writes, and read queries."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = database_path
        self.connection = _connect(database_path)
        self.initialize_schema()

    def __enter__(self) -> GalleryDatabase:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self.connection.close()

    def initialize_schema(self) -> None:
        """Create tables and indexes required by schema version 1."""
        self.connection.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            INSERT OR IGNORE INTO schema_meta (key, value)
            VALUES ('schema_version', '1');

            CREATE TABLE IF NOT EXISTS roots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                root_path TEXT NOT NULL,
                root_path_hash TEXT NOT NULL UNIQUE,
                root_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                root_id INTEGER NOT NULL,
                relative_path TEXT NOT NULL,
                name TEXT NOT NULL,
                parent_relative_path TEXT,
                depth INTEGER NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('active', 'missing')),
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                FOREIGN KEY (root_id) REFERENCES roots(id) ON DELETE CASCADE,
                UNIQUE (root_id, relative_path)
            );

            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                root_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                source_relative_path TEXT NOT NULL,
                filename TEXT NOT NULL,
                extension TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                modified_time REAL NOT NULL,
                width INTEGER,
                height INTEGER,
                thumbnail_relative_path TEXT,
                status TEXT NOT NULL CHECK (status IN ('active', 'missing', 'error')),
                first_seen_scan_id INTEGER,
                last_seen_scan_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (root_id) REFERENCES roots(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE,
                FOREIGN KEY (first_seen_scan_id)
                    REFERENCES scans(id) ON DELETE SET NULL,
                FOREIGN KEY (last_seen_scan_id)
                    REFERENCES scans(id) ON DELETE SET NULL,
                UNIQUE (root_id, source_relative_path)
            );

            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                root_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL CHECK (
                    status IN (
                        'running',
                        'completed',
                        'completed_with_errors',
                        'failed'
                    )
                ),
                total_files_seen INTEGER NOT NULL DEFAULT 0,
                images_added INTEGER NOT NULL DEFAULT 0,
                images_updated INTEGER NOT NULL DEFAULT 0,
                images_skipped INTEGER NOT NULL DEFAULT 0,
                images_missing INTEGER NOT NULL DEFAULT 0,
                errors_count INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (root_id) REFERENCES roots(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS scan_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id INTEGER NOT NULL,
                stage TEXT NOT NULL,
                relative_path TEXT,
                error_type TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (scan_id) REFERENCES scans(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_folders_root_relative_path
                ON folders (root_id, relative_path);
            CREATE INDEX IF NOT EXISTS idx_folders_root_parent
                ON folders (root_id, parent_relative_path);
            CREATE INDEX IF NOT EXISTS idx_folders_root_status
                ON folders (root_id, status);
            CREATE INDEX IF NOT EXISTS idx_images_root_source
                ON images (root_id, source_relative_path);
            CREATE INDEX IF NOT EXISTS idx_images_root_folder
                ON images (root_id, folder_id);
            CREATE INDEX IF NOT EXISTS idx_images_root_status
                ON images (root_id, status);
            CREATE INDEX IF NOT EXISTS idx_scan_errors_scan_id
                ON scan_errors (scan_id);
            """
        )
        self.connection.commit()

    def get_schema_version(self) -> str:
        """Return the active database schema version."""
        row = self.connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            raise RuntimeError("schema version is missing")
        return str(row["value"])

    def upsert_root(self, root_path: str | Path, root_label: str | None = None) -> int:
        """Insert or update a gallery root and return its id."""
        normalized_path = normalize_root_path(root_path)
        normalized_hash = root_path_hash(normalized_path)
        label = root_label or _root_label(normalized_path)
        name = _root_name(normalized_path)
        now = _now()

        with self.connection:
            self.connection.execute(
                """
                INSERT INTO roots (
                    name,
                    root_path,
                    root_path_hash,
                    root_label,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(root_path_hash) DO UPDATE SET
                    name = excluded.name,
                    root_path = excluded.root_path,
                    root_label = excluded.root_label,
                    updated_at = excluded.updated_at
                """,
                (name, normalized_path, normalized_hash, label, now, now),
            )

        return self._require_root_id(normalized_hash)

    def upsert_folder(self, root_id: int, folder: FolderRecord) -> int:
        """Insert or update one folder record and return its id."""
        now = _now()
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO folders (
                    root_id,
                    relative_path,
                    name,
                    parent_relative_path,
                    depth,
                    status,
                    first_seen_at,
                    last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(root_id, relative_path) DO UPDATE SET
                    name = excluded.name,
                    parent_relative_path = excluded.parent_relative_path,
                    depth = excluded.depth,
                    status = 'active',
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    root_id,
                    folder.relative_path,
                    folder.name,
                    folder.parent_relative_path,
                    folder.depth,
                    now,
                    now,
                ),
            )

        return self._require_folder_id(root_id, folder.relative_path)

    def mark_missing_folders(
        self,
        root_id: int,
        active_relative_paths: set[str],
    ) -> int:
        """Mark folders absent from the latest scan without deleting rows."""
        return self._mark_missing(
            table="folders",
            root_id=root_id,
            key_column="relative_path",
            active_keys=active_relative_paths,
        )

    def upsert_image(
        self,
        root_id: int,
        image: ImageRecord,
        scan_id: int | None = None,
    ) -> ImageUpsertResult:
        """Insert, update, or mark one image as seen."""
        folder_id = self._require_folder_id(root_id, image.folder_relative_path)
        existing = self._get_image_row(root_id, image.source_relative_path)
        now = _now()

        if existing is None:
            with self.connection:
                cursor = self.connection.execute(
                    """
                    INSERT INTO images (
                        root_id,
                        folder_id,
                        source_relative_path,
                        filename,
                        extension,
                        file_size,
                        modified_time,
                        width,
                        height,
                        thumbnail_relative_path,
                        status,
                        first_seen_scan_id,
                        last_seen_scan_id,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
                    """,
                    (
                        root_id,
                        folder_id,
                        image.source_relative_path,
                        image.filename,
                        image.extension,
                        image.file_size,
                        image.modified_time,
                        image.width,
                        image.height,
                        image.thumbnail_relative_path,
                        scan_id,
                        scan_id,
                        now,
                        now,
                    ),
                )
            return ImageUpsertResult(image_id=int(cursor.lastrowid), action="added")

        action = _image_upsert_action(existing, image, folder_id)
        with self.connection:
            self.connection.execute(
                """
                UPDATE images
                SET
                    folder_id = ?,
                    filename = ?,
                    extension = ?,
                    file_size = ?,
                    modified_time = ?,
                    width = ?,
                    height = ?,
                    thumbnail_relative_path = ?,
                    status = 'active',
                    last_seen_scan_id = ?,
                    updated_at = CASE
                        WHEN ? = 'skipped' THEN updated_at
                        ELSE ?
                    END
                WHERE id = ?
                """,
                (
                    folder_id,
                    image.filename,
                    image.extension,
                    image.file_size,
                    image.modified_time,
                    image.width,
                    image.height,
                    image.thumbnail_relative_path,
                    scan_id,
                    action,
                    now,
                    existing["id"],
                ),
            )

        return ImageUpsertResult(image_id=int(existing["id"]), action=action)

    def mark_missing_images(
        self,
        root_id: int,
        active_source_relative_paths: set[str],
    ) -> int:
        """Mark images absent from the latest scan without deleting rows."""
        return self._mark_missing(
            table="images",
            root_id=root_id,
            key_column="source_relative_path",
            active_keys=active_source_relative_paths,
        )

    def list_folders(
        self,
        root_id: int,
        *,
        status: str = "active",
    ) -> tuple[FolderRecord, ...]:
        """Return folders for one root ordered by hierarchy depth and path."""
        rows = self.connection.execute(
            """
            SELECT relative_path, name, parent_relative_path, depth
            FROM folders
            WHERE root_id = ? AND status = ?
            ORDER BY depth, relative_path
            """,
            (root_id, status),
        ).fetchall()
        return tuple(
            FolderRecord(
                relative_path=str(row["relative_path"]),
                name=str(row["name"]),
                parent_relative_path=row["parent_relative_path"],
                depth=int(row["depth"]),
            )
            for row in rows
        )

    def list_images(
        self,
        root_id: int,
        *,
        folder_relative_path: str = ROOT_RELATIVE_PATH,
        include_descendants: bool = True,
        search: str | None = None,
        status: str = "active",
        limit: int | None = None,
    ) -> tuple[ImageRecord, ...]:
        """Return images for a folder, optionally including descendants."""
        where_parts = ["images.root_id = ?", "images.status = ?"]
        params: list[object] = [root_id, status]

        if folder_relative_path != ROOT_RELATIVE_PATH:
            if include_descendants:
                where_parts.append(
                    "("
                    "folders.relative_path = ? "
                    "OR folders.relative_path LIKE ? ESCAPE '\\'"
                    ")"
                )
                params.extend(
                    [
                        folder_relative_path,
                        f"{_escape_like(folder_relative_path)}/%",
                    ]
                )
            else:
                where_parts.append("folders.relative_path = ?")
                params.append(folder_relative_path)

        if search:
            where_parts.append(
                """
                (
                    images.filename LIKE ? ESCAPE '\\'
                    OR images.source_relative_path LIKE ? ESCAPE '\\'
                )
                """
            )
            search_pattern = f"%{_escape_like(search)}%"
            params.extend([search_pattern, search_pattern])

        limit_clause = ""
        if limit is not None:
            limit_clause = " LIMIT ?"
            params.append(limit)

        rows = self.connection.execute(
            f"""
            SELECT
                images.source_relative_path,
                folders.relative_path AS folder_relative_path,
                images.filename,
                images.extension,
                images.file_size,
                images.modified_time,
                images.width,
                images.height,
                images.thumbnail_relative_path,
                images.status
            FROM images
            JOIN folders ON folders.id = images.folder_id
            WHERE {" AND ".join(where_parts)}
            ORDER BY images.source_relative_path
            {limit_clause}
            """,
            params,
        ).fetchall()
        return tuple(_image_record_from_row(row) for row in rows)

    def start_scan(self, root_id: int) -> int:
        """Create a running scan record and return its id."""
        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO scans (root_id, started_at, status)
                VALUES (?, ?, 'running')
                """,
                (root_id, _now()),
            )
        return int(cursor.lastrowid)

    def finish_scan(self, scan_id: int, summary: ScanSummary) -> None:
        """Mark a scan completed and store aggregate counts."""
        status = "completed_with_errors" if summary.errors_count else "completed"
        with self.connection:
            self.connection.execute(
                """
                UPDATE scans
                SET
                    finished_at = ?,
                    status = ?,
                    total_files_seen = ?,
                    images_added = ?,
                    images_updated = ?,
                    images_skipped = ?,
                    images_missing = ?,
                    errors_count = ?
                WHERE id = ?
                """,
                (
                    _now(),
                    status,
                    summary.total_files_seen,
                    summary.images_added,
                    summary.images_updated,
                    summary.images_skipped,
                    summary.images_missing,
                    summary.errors_count,
                    scan_id,
                ),
            )

    def fail_scan(self, scan_id: int, errors_count: int = 0) -> None:
        """Mark a scan failed after an unrecoverable error."""
        with self.connection:
            self.connection.execute(
                """
                UPDATE scans
                SET finished_at = ?, status = 'failed', errors_count = ?
                WHERE id = ?
                """,
                (_now(), errors_count, scan_id),
            )

    def add_scan_error(self, scan_id: int, error: ScanErrorRecord) -> int:
        """Persist one recoverable scan error and return its id."""
        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO scan_errors (
                    scan_id,
                    stage,
                    relative_path,
                    error_type,
                    message,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    scan_id,
                    error.stage.value,
                    error.relative_path,
                    error.error_type.value,
                    error.message,
                    _now(),
                ),
            )
        return int(cursor.lastrowid)

    def list_scan_errors(self, scan_id: int) -> tuple[ScanErrorRecord, ...]:
        """Return persisted errors for a scan in insertion order."""
        from image_gallery_browser.errors import ScanErrorType, ScanStage

        rows = self.connection.execute(
            """
            SELECT stage, relative_path, error_type, message
            FROM scan_errors
            WHERE scan_id = ?
            ORDER BY id
            """,
            (scan_id,),
        ).fetchall()
        return tuple(
            ScanErrorRecord(
                stage=ScanStage(str(row["stage"])),
                relative_path=row["relative_path"],
                error_type=ScanErrorType(str(row["error_type"])),
                message=str(row["message"]),
            )
            for row in rows
        )

    def get_scan_status(self, scan_id: int) -> str | None:
        """Return the status for one scan record."""
        row = self.connection.execute(
            "SELECT status FROM scans WHERE id = ?",
            (scan_id,),
        ).fetchone()
        if row is None:
            return None
        return str(row["status"])

    def count_rows(self, table_name: str) -> int:
        """Return a row count for a known application table."""
        if table_name not in {
            "roots",
            "folders",
            "images",
            "scans",
            "scan_errors",
        }:
            raise ValueError(f"unsupported table: {table_name}")
        row = self.connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}")
        return int(row.fetchone()["count"])

    def _require_root_id(self, root_path_hash_value: str) -> int:
        row = self.connection.execute(
            "SELECT id FROM roots WHERE root_path_hash = ?",
            (root_path_hash_value,),
        ).fetchone()
        if row is None:
            raise RuntimeError("root upsert did not return a row")
        return int(row["id"])

    def _require_folder_id(self, root_id: int, relative_path: str) -> int:
        row = self.connection.execute(
            """
            SELECT id FROM folders
            WHERE root_id = ? AND relative_path = ?
            """,
            (root_id, relative_path),
        ).fetchone()
        if row is None:
            raise ValueError(f"folder does not exist: {relative_path}")
        return int(row["id"])

    def _get_image_row(
        self,
        root_id: int,
        source_relative_path: str,
    ) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT *
            FROM images
            WHERE root_id = ? AND source_relative_path = ?
            """,
            (root_id, source_relative_path),
        ).fetchone()

    def _mark_missing(
        self,
        *,
        table: str,
        root_id: int,
        key_column: str,
        active_keys: set[str],
    ) -> int:
        if table not in {"folders", "images"}:
            raise ValueError(f"unsupported missing table: {table}")
        if key_column not in {"relative_path", "source_relative_path"}:
            raise ValueError(f"unsupported missing key: {key_column}")

        params: list[object] = [root_id]
        exclusion_clause = ""
        if active_keys:
            placeholders = ", ".join("?" for _ in active_keys)
            exclusion_clause = f" AND {key_column} NOT IN ({placeholders})"
            params.extend(sorted(active_keys))

        with self.connection:
            cursor = self.connection.execute(
                f"""
                UPDATE {table}
                SET status = 'missing'
                WHERE root_id = ? AND status != 'missing'
                {exclusion_clause}
                """,
                params,
            )
        return cursor.rowcount


def normalize_root_path(root_path: str | Path) -> str:
    """Return a stable absolute root path string for storage."""
    return str(resolve_path(root_path))


def root_path_hash(root_path: str | Path) -> str:
    """Hash a normalized root path for stable root identity."""
    normalized = os.path.normcase(normalize_root_path(root_path))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _connect(database_path: str | Path) -> sqlite3.Connection:
    if str(database_path) != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _root_label(normalized_path: str) -> str:
    return _root_name(normalized_path)


def _root_name(normalized_path: str) -> str:
    path = Path(normalized_path)
    return path.name or normalized_path


def _image_upsert_action(
    existing: sqlite3.Row,
    image: ImageRecord,
    folder_id: int,
) -> ImageUpsertAction:
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


def _image_record_from_row(row: sqlite3.Row) -> ImageRecord:
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


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
