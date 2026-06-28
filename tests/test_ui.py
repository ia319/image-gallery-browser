import pytest

from image_gallery_browser.models import FolderRecord, ImageRecord
from image_gallery_browser.paths import ROOT_RELATIVE_PATH
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
