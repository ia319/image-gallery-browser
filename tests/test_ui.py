import pytest

from image_gallery_browser.errors import ScanErrorType, ScanStage
from image_gallery_browser.models import (
    FolderRecord,
    GalleryConfig,
    ImageRecord,
    ScanErrorRecord,
    ScanRecord,
)
from image_gallery_browser.paths import ROOT_RELATIVE_PATH
from image_gallery_browser.ui import (
    format_gallery_label,
    format_index_status,
    format_last_scan,
    format_scan_error,
)
from image_gallery_browser.ui.folder_tree import build_folder_options
from image_gallery_browser.ui.gallery import chunk_images
from image_gallery_browser.ui.preview import format_dimensions, format_file_size


def test_build_folder_options_returns_indented_labels() -> None:
    folders = (
        FolderRecord(ROOT_RELATIVE_PATH, "projects", None, 0),
        FolderRecord("Project A", "Project A", ROOT_RELATIVE_PATH, 1),
        FolderRecord("Project A/Renders", "Renders", "Project A", 2),
    )

    options = build_folder_options(folders)

    assert [option.relative_path for option in options] == [
        ROOT_RELATIVE_PATH,
        "Project A",
        "Project A/Renders",
    ]
    assert [option.label for option in options] == [
        "Root",
        "  Project A",
        "    Renders",
    ]


def test_build_folder_options_returns_root_for_empty_index() -> None:
    options = build_folder_options(())

    assert len(options) == 1
    assert options[0].relative_path == ROOT_RELATIVE_PATH
    assert options[0].label == "Root"


def test_chunk_images_splits_rows_by_column_count() -> None:
    images = tuple(
        ImageRecord(f"image-{index}.png", ".", f"image-{index}.png", ".png", 1, 1.0)
        for index in range(5)
    )

    rows = chunk_images(images, columns=2)

    assert [[image.filename for image in row] for row in rows] == [
        ["image-0.png", "image-1.png"],
        ["image-2.png", "image-3.png"],
        ["image-4.png"],
    ]


def test_chunk_images_rejects_invalid_column_count() -> None:
    with pytest.raises(ValueError, match="columns must be positive"):
        chunk_images((), columns=0)


def test_preview_format_helpers() -> None:
    image = ImageRecord("render.png", ".", "render.png", ".png", 1536, 1.0, 80, 40)

    assert format_file_size(512) == "512 B"
    assert format_file_size(1536) == "1.5 KB"
    assert format_dimensions(image) == "80 x 40"
    assert (
        format_dimensions(ImageRecord("broken.png", ".", "broken.png", ".png", 1, 1.0))
        == "Unknown"
    )


def test_format_gallery_label_prefers_configured_label(tmp_path) -> None:
    config = GalleryConfig(
        projects_root=tmp_path / "private-client-projects",
        data_dir=tmp_path / "data",
        gallery_label="Sample Gallery",
    )

    assert format_gallery_label(config) == "Sample Gallery"


def test_format_gallery_label_falls_back_to_directory_name(tmp_path) -> None:
    config = GalleryConfig(
        projects_root=tmp_path / "sample_projects",
        data_dir=tmp_path / "data",
    )

    assert format_gallery_label(config) == "sample_projects"


@pytest.mark.parametrize(
    ("scan_status", "is_empty", "expected"),
    [
        (None, True, "Empty"),
        (None, False, "Ready"),
        ("completed", False, "Ready"),
        ("completed_with_errors", False, "Ready with errors"),
        ("failed", False, "Failed"),
        ("running", False, "Scanning"),
    ],
)
def test_format_index_status(scan_status: str | None, is_empty: bool, expected: str):
    latest_scan = None
    if scan_status is not None:
        latest_scan = ScanRecord(
            id=1,
            status=scan_status,
            started_at="2026-06-29T10:00:00+00:00",
            finished_at="2026-06-29T10:00:01+00:00",
            total_files_seen=1,
            images_added=1,
            images_updated=0,
            images_skipped=0,
            images_missing=0,
            errors_count=0,
        )

    assert format_index_status(latest_scan, is_empty) == expected


def test_format_last_scan_returns_compact_status() -> None:
    latest_scan = ScanRecord(
        id=1,
        status="completed",
        started_at="2026-06-29T10:00:00+00:00",
        finished_at="2026-06-29T10:00:01+00:00",
        total_files_seen=1,
        images_added=1,
        images_updated=0,
        images_skipped=0,
        images_missing=0,
        errors_count=0,
    )

    assert format_last_scan(latest_scan) == "2026-06-29T10:00:01+00:00 (completed)"
    assert format_last_scan(None) == "None"


def test_format_scan_error_hides_message_until_diagnostics_enabled() -> None:
    error = ScanErrorRecord(
        stage=ScanStage.SCAN,
        error_type=ScanErrorType.UNKNOWN_ERROR,
        relative_path=None,
        message="failed at D:\\private\\gallery\\image.jpg",
    )

    assert format_scan_error(error) == "scan | unknown_error | root"
    assert (
        format_scan_error(error, show_diagnostics=True)
        == "scan | unknown_error | root | failed at D:\\private\\gallery\\image.jpg"
    )
