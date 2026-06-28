"""SQLite schema declarations for gallery persistence."""

SCHEMA_VERSION = "1"

APPLICATION_TABLES = frozenset(
    {
        "roots",
        "folders",
        "images",
        "scans",
        "scan_errors",
    }
)
MISSING_TABLES = frozenset({"folders", "images"})
MISSING_KEY_COLUMNS = frozenset({"relative_path", "source_relative_path"})

SCHEMA_SQL = f"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_meta (key, value)
VALUES ('schema_version', '{SCHEMA_VERSION}');

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
    FOREIGN KEY (first_seen_scan_id) REFERENCES scans(id) ON DELETE SET NULL,
    FOREIGN KEY (last_seen_scan_id) REFERENCES scans(id) ON DELETE SET NULL,
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
