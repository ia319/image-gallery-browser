"""SQLite persistence layer for indexed gallery data."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType

from image_gallery_browser.database.queries import (
    FAIL_SCAN,
    FINISH_SCAN,
    INSERT_IMAGE,
    INSERT_SCAN_ERROR,
    MARK_IMAGE_ERROR,
    SELECT_FOLDER_ID,
    SELECT_FOLDERS,
    SELECT_IMAGE,
    SELECT_LATEST_SCAN,
    SELECT_ROOT_ID,
    SELECT_SCAN_ERRORS,
    SELECT_SCAN_STATUS,
    SELECT_SCHEMA_VERSION,
    START_SCAN,
    UPDATE_IMAGE,
    UPSERT_FOLDER,
    UPSERT_ROOT,
    build_list_images_query,
)
from image_gallery_browser.database.records import (
    ImageUpsertResult,
    folder_record_from_row,
    image_record_from_row,
    image_upsert_action,
    scan_error_record_from_row,
    scan_record_from_row,
)
from image_gallery_browser.database.schema import (
    APPLICATION_TABLES,
    MISSING_KEY_COLUMNS,
    MISSING_TABLES,
    SCHEMA_SQL,
)
from image_gallery_browser.database.support import (
    connect_database,
    default_root_label,
    escape_like,
    normalize_root_path,
    root_name,
    root_path_hash,
    utc_now,
)
from image_gallery_browser.models import (
    FolderRecord,
    ImageRecord,
    ScanErrorRecord,
    ScanRecord,
    ScanSummary,
)
from image_gallery_browser.paths import ROOT_RELATIVE_PATH


class GalleryDatabase:
    """Manage SQLite schema, writes, and read queries."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = database_path
        self.connection = connect_database(database_path)
        self.initialize_schema()

    def __enter__(self) -> GalleryDatabase:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self.connection.close()

    def initialize_schema(self) -> None:
        """Create tables and indexes required by schema version 1."""
        self.connection.executescript(SCHEMA_SQL)
        self.connection.commit()

    def get_schema_version(self) -> str:
        """Return the active database schema version."""
        row = self.connection.execute(SELECT_SCHEMA_VERSION).fetchone()
        if row is None:
            raise RuntimeError("schema version is missing")
        return str(row["value"])

    def upsert_root(self, root_path: str | Path, root_label: str | None = None) -> int:
        """Insert or update a gallery root and return its id."""
        normalized_path = normalize_root_path(root_path)
        normalized_hash = root_path_hash(normalized_path)
        label = root_label or default_root_label(normalized_path)
        name = root_name(normalized_path)
        now = utc_now()

        with self.connection:
            self.connection.execute(
                UPSERT_ROOT,
                (name, normalized_path, normalized_hash, label, now, now),
            )

        return self._require_root_id(normalized_hash)

    def upsert_folder(self, root_id: int, folder: FolderRecord) -> int:
        """Insert or update one folder record and return its id."""
        now = utc_now()
        with self.connection:
            self.connection.execute(
                UPSERT_FOLDER,
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
        now = utc_now()

        if existing is None:
            with self.connection:
                cursor = self.connection.execute(
                    INSERT_IMAGE,
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

        action = image_upsert_action(existing, image, folder_id)
        with self.connection:
            self.connection.execute(
                UPDATE_IMAGE,
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

    def mark_image_error(
        self,
        root_id: int,
        source_relative_path: str,
        scan_id: int | None = None,
    ) -> int:
        """Mark one seen image as errored without deleting metadata."""
        with self.connection:
            cursor = self.connection.execute(
                MARK_IMAGE_ERROR,
                (scan_id, utc_now(), root_id, source_relative_path),
            )
        return cursor.rowcount

    def list_folders(
        self,
        root_id: int,
        *,
        status: str = "active",
    ) -> tuple[FolderRecord, ...]:
        """Return folders for one root ordered by hierarchy depth and path."""
        rows = self.connection.execute(
            SELECT_FOLDERS,
            (root_id, status),
        ).fetchall()
        return tuple(folder_record_from_row(row) for row in rows)

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
                        f"{escape_like(folder_relative_path)}/%",
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
            search_pattern = f"%{escape_like(search)}%"
            params.extend([search_pattern, search_pattern])

        limit_clause = ""
        if limit is not None:
            limit_clause = " LIMIT ?"
            params.append(limit)

        rows = self.connection.execute(
            build_list_images_query(" AND ".join(where_parts), limit_clause),
            params,
        ).fetchall()
        return tuple(image_record_from_row(row) for row in rows)

    def start_scan(self, root_id: int) -> int:
        """Create a running scan record and return its id."""
        with self.connection:
            cursor = self.connection.execute(
                START_SCAN,
                (root_id, utc_now()),
            )
        return int(cursor.lastrowid)

    def finish_scan(self, scan_id: int, summary: ScanSummary) -> None:
        """Mark a scan completed and store aggregate counts."""
        status = "completed_with_errors" if summary.errors_count else "completed"
        with self.connection:
            self.connection.execute(
                FINISH_SCAN,
                (
                    utc_now(),
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
                FAIL_SCAN,
                (utc_now(), errors_count, scan_id),
            )

    def add_scan_error(self, scan_id: int, error: ScanErrorRecord) -> int:
        """Persist one recoverable scan error and return its id."""
        with self.connection:
            cursor = self.connection.execute(
                INSERT_SCAN_ERROR,
                (
                    scan_id,
                    error.stage.value,
                    error.relative_path,
                    error.error_type.value,
                    error.message,
                    utc_now(),
                ),
            )
        return int(cursor.lastrowid)

    def list_scan_errors(self, scan_id: int) -> tuple[ScanErrorRecord, ...]:
        """Return persisted errors for a scan in insertion order."""
        rows = self.connection.execute(
            SELECT_SCAN_ERRORS,
            (scan_id,),
        ).fetchall()
        return tuple(scan_error_record_from_row(row) for row in rows)

    def get_scan_status(self, scan_id: int) -> str | None:
        """Return the status for one scan record."""
        row = self.connection.execute(
            SELECT_SCAN_STATUS,
            (scan_id,),
        ).fetchone()
        if row is None:
            return None
        return str(row["status"])

    def get_latest_scan(self, root_id: int) -> ScanRecord | None:
        """Return the newest scan metadata for one root."""
        row = self.connection.execute(
            SELECT_LATEST_SCAN,
            (root_id,),
        ).fetchone()
        if row is None:
            return None
        return scan_record_from_row(row)

    def count_rows(self, table_name: str) -> int:
        """Return a row count for a known application table."""
        if table_name not in APPLICATION_TABLES:
            raise ValueError(f"unsupported table: {table_name}")
        row = self.connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}")
        return int(row.fetchone()["count"])

    def _require_root_id(self, root_path_hash_value: str) -> int:
        row = self.connection.execute(
            SELECT_ROOT_ID,
            (root_path_hash_value,),
        ).fetchone()
        if row is None:
            raise RuntimeError("root upsert did not return a row")
        return int(row["id"])

    def _require_folder_id(self, root_id: int, relative_path: str) -> int:
        row = self.connection.execute(
            SELECT_FOLDER_ID,
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
            SELECT_IMAGE,
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
        if table not in MISSING_TABLES:
            raise ValueError(f"unsupported missing table: {table}")
        if key_column not in MISSING_KEY_COLUMNS:
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
