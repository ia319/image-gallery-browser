import os
from pathlib import Path

import pytest
from PIL import Image, features

from image_gallery_browser.errors import ScanErrorType, ScanStage
from image_gallery_browser.models import ImageRecord
from image_gallery_browser.thumbnails import (
    THUMBNAIL_DIR_NAME,
    process_image_thumbnail,
    read_image_size,
    thumbnail_cache_path,
    thumbnail_relative_path,
)


def test_thumbnail_relative_path_uses_source_path_hash() -> None:
    first = thumbnail_relative_path("Project A/render.png", (320, 320))
    second = thumbnail_relative_path("Project B/render.png", (320, 320))

    assert first != second
    assert first.startswith(f"{THUMBNAIL_DIR_NAME}/")
    assert first.endswith(".png")


def test_thumbnail_relative_path_includes_thumbnail_size() -> None:
    first = thumbnail_relative_path("Project A/render.png", (320, 320))
    second = thumbnail_relative_path("Project A/render.png", (640, 640))

    assert first != second


def test_process_image_thumbnail_generates_cache_and_updates_record(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    data_dir = tmp_path / "data"
    source_path = projects_root / "Project" / "render.png"
    _save_image(source_path, "PNG", size=(120, 80))
    image = _image_record("Project/render.png", source_path)

    result = process_image_thumbnail(image, projects_root, data_dir, (32, 32))

    assert result.ok
    assert result.generated is True
    assert result.image is not None
    assert result.image.width == 120
    assert result.image.height == 80
    assert result.image.thumbnail_relative_path is not None
    thumbnail_path = thumbnail_cache_path(
        data_dir, result.image.thumbnail_relative_path
    )
    assert thumbnail_path.exists()
    assert thumbnail_path.is_relative_to(data_dir)
    assert not (projects_root / THUMBNAIL_DIR_NAME).exists()
    with Image.open(thumbnail_path) as thumbnail:
        assert thumbnail.width <= 32
        assert thumbnail.height <= 32


def test_read_image_size_returns_dimensions(tmp_path: Path) -> None:
    image_path = tmp_path / "source.jpg"
    _save_image(image_path, "JPEG", size=(64, 48))

    assert read_image_size(image_path) == (64, 48)


def test_process_image_thumbnail_reuses_valid_cache(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    data_dir = tmp_path / "data"
    source_path = projects_root / "render.png"
    _save_image(source_path, "PNG", size=(80, 60))
    os.utime(source_path, (1_700_000_000, 1_700_000_000))
    image = _image_record("render.png", source_path)

    first = process_image_thumbnail(image, projects_root, data_dir, (40, 40))
    assert first.image is not None
    thumbnail_path = thumbnail_cache_path(data_dir, first.image.thumbnail_relative_path)
    first_modified_time = thumbnail_path.stat().st_mtime

    second = process_image_thumbnail(image, projects_root, data_dir, (40, 40))

    assert second.ok
    assert second.generated is False
    assert thumbnail_path.stat().st_mtime == first_modified_time


def test_process_image_thumbnail_regenerates_after_size_change(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    data_dir = tmp_path / "data"
    source_path = projects_root / "render.png"
    _save_image(source_path, "PNG", size=(80, 60))
    os.utime(source_path, (1_700_000_000, 1_700_000_000))
    image = _image_record("render.png", source_path)

    first = process_image_thumbnail(image, projects_root, data_dir, (40, 40))
    second = process_image_thumbnail(image, projects_root, data_dir, (20, 20))

    assert first.image is not None
    assert second.image is not None
    assert second.generated is True
    assert second.image.thumbnail_relative_path != first.image.thumbnail_relative_path
    thumbnail_path = thumbnail_cache_path(
        data_dir, second.image.thumbnail_relative_path
    )
    with Image.open(thumbnail_path) as thumbnail:
        assert thumbnail.width <= 20
        assert thumbnail.height <= 20


def test_process_image_thumbnail_reports_corrupt_image(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    data_dir = tmp_path / "data"
    source_path = projects_root / "broken.png"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"not an image")
    image = _image_record("broken.png", source_path)

    result = process_image_thumbnail(image, projects_root, data_dir, (32, 32))

    assert result.image is None
    assert result.error is not None
    assert result.error.stage == ScanStage.IMAGE_OPEN
    assert result.error.error_type == ScanErrorType.CORRUPT_IMAGE
    assert result.error.relative_path == "broken.png"


def test_process_image_thumbnail_reports_invalid_relative_path(tmp_path: Path) -> None:
    image = ImageRecord(
        source_relative_path="../outside.png",
        folder_relative_path=".",
        filename="outside.png",
        extension=".png",
        file_size=0,
        modified_time=0,
    )

    result = process_image_thumbnail(
        image, tmp_path / "projects", tmp_path / "data", (32, 32)
    )

    assert result.image is None
    assert result.error is not None
    assert result.error.stage == ScanStage.PATH
    assert result.error.error_type == ScanErrorType.INVALID_PATH
    assert result.error.relative_path == "../outside.png"


def test_process_image_thumbnail_reports_thumbnail_write_failure(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    data_file = tmp_path / "data"
    source_path = projects_root / "render.png"
    _save_image(source_path, "PNG", size=(80, 60))
    data_file.write_text("not a directory", encoding="utf-8")
    image = _image_record("render.png", source_path)

    result = process_image_thumbnail(image, projects_root, data_file, (32, 32))

    assert result.image is None
    assert result.error is not None
    assert result.error.stage == ScanStage.THUMBNAIL
    assert result.error.error_type == ScanErrorType.THUMBNAIL_FAILED


def test_process_image_thumbnail_does_not_leave_final_file_on_write_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    projects_root = tmp_path / "projects"
    data_dir = tmp_path / "data"
    source_path = projects_root / "render.png"
    _save_image(source_path, "PNG", size=(80, 60))
    image = _image_record("render.png", source_path)
    thumbnail_relative = thumbnail_relative_path("render.png", (32, 32))
    thumbnail_path = thumbnail_cache_path(data_dir, thumbnail_relative)

    def fail_save(self, fp, *args, **kwargs) -> None:
        raise OSError("save failed")

    monkeypatch.setattr(Image.Image, "save", fail_save)

    result = process_image_thumbnail(image, projects_root, data_dir, (32, 32))

    assert result.image is None
    assert result.error is not None
    assert not thumbnail_path.exists()
    assert list(thumbnail_path.parent.glob("*.tmp")) == []


@pytest.mark.parametrize(
    ("extension", "format_name"),
    [
        (".jpg", "JPEG"),
        (".jpeg", "JPEG"),
        (".png", "PNG"),
        (".webp", "WEBP"),
    ],
)
def test_process_image_thumbnail_supports_configured_formats(
    tmp_path: Path,
    extension: str,
    format_name: str,
) -> None:
    if format_name == "WEBP" and not features.check("webp"):
        pytest.skip("Pillow build does not include WebP support")

    projects_root = tmp_path / "projects"
    data_dir = tmp_path / "data"
    source_path = projects_root / f"render{extension}"
    _save_image(source_path, format_name, size=(50, 30))
    image = _image_record(f"render{extension}", source_path)

    result = process_image_thumbnail(image, projects_root, data_dir, (25, 25))

    assert result.ok
    assert result.image is not None
    assert result.image.width == 50
    assert result.image.height == 30
    assert result.image.thumbnail_relative_path is not None


def _save_image(path: Path, format_name: str, size: tuple[int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, color=(20, 80, 140))
    try:
        image.save(path, format=format_name)
    finally:
        image.close()


def _image_record(source_relative_path: str, source_path: Path) -> ImageRecord:
    source_stat = source_path.stat()
    return ImageRecord(
        source_relative_path=source_relative_path,
        folder_relative_path=".",
        filename=source_path.name,
        extension=source_path.suffix.lower(),
        file_size=source_stat.st_size,
        modified_time=source_stat.st_mtime,
    )
