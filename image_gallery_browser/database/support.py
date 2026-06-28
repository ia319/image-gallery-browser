"""Support functions for SQLite persistence."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from image_gallery_browser.paths import resolve_path


def connect_database(database_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection with application defaults."""
    if str(database_path) != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def utc_now() -> str:
    """Return an ISO 8601 UTC timestamp for database records."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def normalize_root_path(root_path: str | Path) -> str:
    """Return a stable absolute root path string for storage."""
    return str(resolve_path(root_path))


def root_path_hash(root_path: str | Path) -> str:
    """Hash a normalized root path for stable root identity."""
    normalized = os.path.normcase(normalize_root_path(root_path))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def default_root_label(normalized_path: str) -> str:
    """Return a compact display label for a stored root path."""
    return root_name(normalized_path)


def root_name(normalized_path: str) -> str:
    """Return the final path segment for a stored root path."""
    path = Path(normalized_path)
    return path.name or normalized_path


def escape_like(value: str) -> str:
    """Escape user-provided text for SQLite LIKE patterns."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
