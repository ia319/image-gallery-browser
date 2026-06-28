from collections.abc import Iterator
from pathlib import Path

from image_gallery_browser import scanner
from image_gallery_browser.errors import ScanErrorType, ScanStage
from image_gallery_browser.paths import ROOT_RELATIVE_PATH
from image_gallery_browser.scanner import scan_gallery_root


def test_scan_gallery_root_discovers_nested_folders_and_images(
    tmp_path: Path,
) -> None:
    root = tmp_path / "gallery"
    (root / "Project A" / "Drafts").mkdir(parents=True)
    (root / "Project B" / "Second Level").mkdir(parents=True)
    (root / "cover.JPG").write_bytes(b"image")
    (root / "Project A" / "Drafts" / "render.png").write_bytes(b"image")
    (root / "Project B" / "Second Level" / "view.webp").write_bytes(b"image")
    (root / "Project A" / "notes.txt").write_text("skip", encoding="utf-8")

    result = scan_gallery_root(root, [".jpg", ".png", ".webp"])

    assert result.errors == ()
    assert result.total_files_seen == 4
    assert {folder.relative_path for folder in result.folders} == {
        ROOT_RELATIVE_PATH,
        "Project A",
        "Project A/Drafts",
        "Project B",
        "Project B/Second Level",
    }
    assert {image.source_relative_path for image in result.images} == {
        "cover.JPG",
        "Project A/Drafts/render.png",
        "Project B/Second Level/view.webp",
    }


def test_scan_gallery_root_discovers_deep_nested_images(tmp_path: Path) -> None:
    root = tmp_path / "gallery"
    second_level = root / "Project A" / "Renders"
    archive = second_level / "Archive"
    archive.mkdir(parents=True)
    (second_level / "render.png").write_bytes(b"image")
    (archive / "archived.png").write_bytes(b"image")

    result = scan_gallery_root(root, [".png"])

    assert result.total_files_seen == 2
    assert {folder.relative_path for folder in result.folders} == {
        ROOT_RELATIVE_PATH,
        "Project A",
        "Project A/Renders",
        "Project A/Renders/Archive",
    }
    assert {image.source_relative_path for image in result.images} == {
        "Project A/Renders/render.png",
        "Project A/Renders/Archive/archived.png",
    }


def test_scan_gallery_root_assigns_root_images_to_root_folder(
    tmp_path: Path,
) -> None:
    root = tmp_path / "gallery"
    root.mkdir()
    image_path = root / "render.jpeg"
    image_path.write_bytes(b"image")

    result = scan_gallery_root(root, ["jpeg"])

    assert len(result.images) == 1
    assert result.images[0].folder_relative_path == ROOT_RELATIVE_PATH
    assert result.images[0].filename == "render.jpeg"
    assert result.images[0].extension == ".jpeg"
    assert result.images[0].file_size == 5


def test_scan_gallery_root_builds_folder_metadata(tmp_path: Path) -> None:
    root = tmp_path / "gallery"
    nested = root / "Project" / "Renders"
    nested.mkdir(parents=True)

    result = scan_gallery_root(root, [".jpg"])
    folders = {folder.relative_path: folder for folder in result.folders}

    assert folders[ROOT_RELATIVE_PATH].parent_relative_path is None
    assert folders[ROOT_RELATIVE_PATH].depth == 0
    assert folders["Project"].parent_relative_path == ROOT_RELATIVE_PATH
    assert folders["Project"].depth == 1
    assert folders["Project/Renders"].parent_relative_path == "Project"
    assert folders["Project/Renders"].depth == 2


def test_scan_gallery_root_ignores_unsupported_files(tmp_path: Path) -> None:
    root = tmp_path / "gallery"
    root.mkdir()
    (root / "notes.txt").write_text("skip", encoding="utf-8")

    result = scan_gallery_root(root, [".jpg"])

    assert result.total_files_seen == 1
    assert result.images == ()
    assert result.errors == ()


def test_scan_gallery_root_reports_invalid_root(tmp_path: Path) -> None:
    result = scan_gallery_root(tmp_path / "missing", [".jpg"])

    assert result.folders == ()
    assert result.images == ()
    assert result.errors_count == 1
    assert result.errors[0].stage == ScanStage.SCAN
    assert result.errors[0].error_type == ScanErrorType.INVALID_PATH


def test_scan_gallery_root_records_directory_permission_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "gallery"
    blocked = root / "blocked"
    blocked.mkdir(parents=True)
    original_iter_directory = scanner._iter_directory

    def iter_directory(directory: Path) -> Iterator[Path]:
        if directory == blocked:
            raise PermissionError("blocked directory")
        return original_iter_directory(directory)

    monkeypatch.setattr(scanner, "_iter_directory", iter_directory)

    result = scan_gallery_root(root, [".jpg"])

    assert result.errors_count == 1
    assert result.errors[0].stage == ScanStage.SCAN
    assert result.errors[0].error_type == ScanErrorType.PERMISSION_DENIED
    assert result.errors[0].relative_path == "blocked"
