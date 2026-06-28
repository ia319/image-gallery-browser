"""Shared error types for scan and path handling."""

from __future__ import annotations

from enum import StrEnum


class ScanStage(StrEnum):
    """Identify the processing stage that produced a recoverable error."""

    SCAN = "scan"
    PATH = "path"
    IMAGE_OPEN = "image_open"
    THUMBNAIL = "thumbnail"
    DATABASE = "database"


class ScanErrorType(StrEnum):
    """Identify stable error categories for storage and UI reporting."""

    PERMISSION_DENIED = "permission_denied"
    INVALID_PATH = "invalid_path"
    CORRUPT_IMAGE = "corrupt_image"
    UNSUPPORTED_IMAGE = "unsupported_image"
    THUMBNAIL_FAILED = "thumbnail_failed"
    DATABASE_ERROR = "database_error"
    UNKNOWN_ERROR = "unknown_error"


class ConfigError(ValueError):
    """Raise when configuration values cannot be normalized safely."""


class PathBoundaryError(ValueError):
    """Raise when a path escapes the configured gallery root."""
