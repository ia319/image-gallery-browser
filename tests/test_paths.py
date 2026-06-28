from pathlib import Path

import pytest

from image_gallery_browser import paths
from image_gallery_browser.errors import PathBoundaryError
from image_gallery_browser.paths import (
    ROOT_RELATIVE_PATH,
    folder_relative_path_for_image,
    is_unc_path,
    relative_to_root,
    to_posix_relative_path,
)


def test_relative_to_root_returns_posix_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    image = root / "Project A" / "render.png"
    image.parent.mkdir(parents=True)
    image.touch()

    assert relative_to_root(image, root) == "Project A/render.png"


def test_relative_to_root_returns_root_marker_for_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    assert relative_to_root(root, root) == ROOT_RELATIVE_PATH


def test_relative_to_root_rejects_outside_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside" / "image.png"
    root.mkdir()
    outside.parent.mkdir()
    outside.touch()

    with pytest.raises(PathBoundaryError):
        relative_to_root(outside, root)


def test_relative_to_root_handles_commonpath_value_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside" / "image.png"
    root.mkdir()
    outside.parent.mkdir()
    outside.touch()

    def commonpath(_paths: list[str]) -> str:
        raise ValueError("paths are on different drives")

    monkeypatch.setattr(paths.os.path, "commonpath", commonpath)

    with pytest.raises(PathBoundaryError):
        relative_to_root(outside, root)


def test_folder_relative_path_for_root_image() -> None:
    assert folder_relative_path_for_image("render.png") == ROOT_RELATIVE_PATH


def test_folder_relative_path_for_nested_image() -> None:
    assert folder_relative_path_for_image("project/renders/render.png") == (
        "project/renders"
    )


def test_to_posix_relative_path_normalizes_empty_path() -> None:
    assert to_posix_relative_path("") == ROOT_RELATIVE_PATH


def test_is_unc_path_detects_unc_strings() -> None:
    assert is_unc_path(r"\\server\share")
