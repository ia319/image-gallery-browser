from pathlib import Path

from PIL import Image

from image_gallery_browser.database import GalleryDatabase
from image_gallery_browser.errors import ScanErrorType, ScanStage
from image_gallery_browser.models import GalleryConfig
from image_gallery_browser.services import GalleryService


def test_scan_on_empty_respects_auto_scan_config(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    database = GalleryDatabase(":memory:")
    service = GalleryService(
        _config(projects_root, tmp_path / "data", auto_scan_on_empty=False),
        database=database,
    )

    try:
        assert service.scan_on_empty() is None
        assert service.is_empty()
        assert database.count_rows("scans") == 0
    finally:
        database.close()


def test_rescan_indexes_images_and_skips_unchanged_files(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    data_dir = tmp_path / "data"
    source_path = projects_root / "Project" / "render.png"
    _save_image(source_path, "PNG", size=(80, 40))

    database = GalleryDatabase(":memory:")
    service = GalleryService(_config(projects_root, data_dir), database=database)

    try:
        first_summary = service.rescan()
        second_summary = service.rescan()
        images = service.list_images(folder_relative_path="Project").images

        assert first_summary.images_added == 1
        assert first_summary.errors_count == 0
        assert second_summary.images_skipped == 1
        assert second_summary.images_added == 0
        assert len(images) == 1
        assert images[0].width == 80
        assert images[0].height == 40
        assert service.thumbnail_path(images[0]) is not None
        assert service.thumbnail_path(images[0]).exists()
    finally:
        database.close()


def test_rescan_marks_missing_images_without_deleting_records(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    data_dir = tmp_path / "data"
    source_path = projects_root / "render.jpg"
    _save_image(source_path, "JPEG", size=(32, 32))

    database = GalleryDatabase(":memory:")
    service = GalleryService(_config(projects_root, data_dir), database=database)

    try:
        service.rescan()
        source_path.unlink()
        summary = service.rescan()

        assert summary.images_missing == 1
        assert service.list_images().images == ()
        assert database.count_rows("images") == 1
    finally:
        database.close()


def test_rescan_records_thumbnail_errors_and_continues(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    data_dir = tmp_path / "data"
    _save_image(projects_root / "valid.png", "PNG", size=(20, 20))
    broken_path = projects_root / "broken.png"
    broken_path.parent.mkdir(parents=True, exist_ok=True)
    broken_path.write_bytes(b"not an image")

    database = GalleryDatabase(":memory:")
    service = GalleryService(_config(projects_root, data_dir), database=database)

    try:
        summary = service.rescan()
        latest_scan = service.latest_scan()

        assert summary.images_added == 1
        assert summary.errors_count == 1
        assert summary.errors[0].stage == ScanStage.IMAGE_OPEN
        assert summary.errors[0].error_type == ScanErrorType.CORRUPT_IMAGE
        assert latest_scan is not None
        assert latest_scan.status == "completed_with_errors"
        assert database.list_scan_errors(latest_scan.id) == summary.errors
    finally:
        database.close()


def test_rescan_records_failed_scan_when_scanner_raises(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    database = GalleryDatabase(":memory:")

    def failing_scan(_root, _extensions):
        raise RuntimeError("scan failed")

    service = GalleryService(
        _config(projects_root, tmp_path / "data"),
        database=database,
        scan_func=failing_scan,
    )

    try:
        summary = service.rescan()
        latest_scan = service.latest_scan()

        assert summary.errors_count == 1
        assert summary.errors[0].stage == ScanStage.SCAN
        assert latest_scan is not None
        assert latest_scan.status == "failed"
        assert database.list_scan_errors(latest_scan.id) == summary.errors
    finally:
        database.close()


def test_list_images_reports_truncation(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    data_dir = tmp_path / "data"
    for index in range(3):
        _save_image(projects_root / f"render-{index}.png", "PNG", size=(16, 16))

    database = GalleryDatabase(":memory:")
    service = GalleryService(
        _config(projects_root, data_dir, max_images_per_view=2),
        database=database,
    )

    try:
        service.rescan()
        result = service.list_images()

        assert len(result.images) == 2
        assert result.limit == 2
        assert result.truncated is True
    finally:
        database.close()


def _config(
    projects_root: Path,
    data_dir: Path,
    *,
    auto_scan_on_empty: bool = True,
    max_images_per_view: int = 200,
) -> GalleryConfig:
    return GalleryConfig(
        projects_root=projects_root,
        data_dir=data_dir,
        auto_scan_on_empty=auto_scan_on_empty,
        max_images_per_view=max_images_per_view,
    )


def _save_image(path: Path, format_name: str, size: tuple[int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, color=(40, 100, 150))
    try:
        image.save(path, format=format_name)
    finally:
        image.close()
