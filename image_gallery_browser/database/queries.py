"""SQLite query declarations for gallery persistence."""

SELECT_SCHEMA_VERSION = "SELECT value FROM schema_meta WHERE key = 'schema_version'"

UPSERT_ROOT = """
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
    root_label = CASE
        WHEN ? THEN excluded.root_label
        ELSE roots.root_label
    END,
    updated_at = excluded.updated_at
"""

SELECT_ROOT_ID = "SELECT id FROM roots WHERE root_path_hash = ?"

UPSERT_FOLDER = """
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
"""

SELECT_FOLDER_ID = """
SELECT id
FROM folders
WHERE root_id = ? AND relative_path = ?
"""

INSERT_IMAGE = """
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
"""

UPDATE_IMAGE = """
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
    last_seen_scan_id = COALESCE(?, last_seen_scan_id),
    updated_at = CASE
        WHEN ? = 'skipped' THEN updated_at
        ELSE ?
    END
WHERE id = ?
"""

SELECT_IMAGE = """
SELECT *
FROM images
WHERE root_id = ? AND source_relative_path = ?
"""

SELECT_FOLDERS = """
SELECT relative_path, name, parent_relative_path, depth
FROM folders
WHERE root_id = ? AND status = ?
ORDER BY depth, relative_path
"""

START_SCAN = """
INSERT INTO scans (root_id, started_at, status)
VALUES (?, ?, 'running')
"""

FINISH_SCAN = """
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
"""

FAIL_SCAN = """
UPDATE scans
SET finished_at = ?, status = 'failed', errors_count = ?
WHERE id = ?
"""

INSERT_SCAN_ERROR = """
INSERT INTO scan_errors (
    scan_id,
    stage,
    relative_path,
    error_type,
    message,
    created_at
)
VALUES (?, ?, ?, ?, ?, ?)
"""

SELECT_SCAN_ERRORS = """
SELECT stage, relative_path, error_type, message
FROM scan_errors
WHERE scan_id = ?
ORDER BY id
"""

SELECT_SCAN_STATUS = "SELECT status FROM scans WHERE id = ?"

SELECT_LATEST_SCAN = """
SELECT
    id,
    status,
    started_at,
    finished_at,
    total_files_seen,
    images_added,
    images_updated,
    images_skipped,
    images_missing,
    errors_count
FROM scans
WHERE root_id = ?
ORDER BY id DESC
LIMIT 1
"""

MARK_IMAGE_ERROR = """
UPDATE images
SET status = 'error', last_seen_scan_id = COALESCE(?, last_seen_scan_id), updated_at = ?
WHERE root_id = ? AND source_relative_path = ?
"""

TEMP_ACTIVE_KEYS_TABLE = "temp_active_missing_keys"

CREATE_TEMP_ACTIVE_KEYS = """
CREATE TEMP TABLE IF NOT EXISTS temp_active_missing_keys (
    active_key TEXT PRIMARY KEY
)
"""

DELETE_TEMP_ACTIVE_KEYS = "DELETE FROM temp_active_missing_keys"

INSERT_TEMP_ACTIVE_KEY = """
INSERT INTO temp_active_missing_keys (active_key)
VALUES (?)
"""

MARK_MISSING_QUERIES = {
    ("folders", "relative_path", False): """
        UPDATE folders
        SET status = 'missing'
        WHERE root_id = ? AND status != 'missing'
    """,
    ("folders", "relative_path", True): """
        UPDATE folders
        SET status = 'missing'
        WHERE root_id = ? AND status != 'missing'
        AND NOT EXISTS (
            SELECT 1
            FROM temp_active_missing_keys
            WHERE temp_active_missing_keys.active_key = folders.relative_path
        )
    """,
    ("images", "source_relative_path", False): """
        UPDATE images
        SET status = 'missing'
        WHERE root_id = ? AND status != 'missing'
    """,
    ("images", "source_relative_path", True): """
        UPDATE images
        SET status = 'missing'
        WHERE root_id = ? AND status != 'missing'
        AND NOT EXISTS (
            SELECT 1
            FROM temp_active_missing_keys
            WHERE temp_active_missing_keys.active_key = images.source_relative_path
        )
    """,
}


def build_list_images_query(where_clause: str, limit_clause: str) -> str:
    """Build the image listing query from validated SQL fragments."""
    return f"""
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
    WHERE {where_clause}
    ORDER BY images.source_relative_path
    {limit_clause}
    """
