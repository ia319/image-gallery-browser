import json
from pathlib import Path

import pytest

from image_gallery_browser.config import load_config, parse_config
from image_gallery_browser.errors import ConfigError


def test_parse_config_applies_defaults(tmp_path: Path) -> None:
    config = parse_config({}, base_dir=tmp_path)

    assert config.projects_root == (tmp_path / "sample_projects").resolve()
    assert config.data_dir == (tmp_path / "data").resolve()
    assert config.thumbnail_size == (320, 320)
    assert config.supported_extensions == frozenset({".jpg", ".jpeg", ".png", ".webp"})
    assert config.auto_scan_on_empty is True
    assert config.max_images_per_view == 200


def test_parse_config_normalizes_extensions(tmp_path: Path) -> None:
    config = parse_config(
        {"supported_extensions": [" JPG ", ".PNG"]},
        base_dir=tmp_path,
    )

    assert config.supported_extensions == frozenset({".jpg", ".png"})


def test_load_config_reads_json_file(tmp_path: Path) -> None:
    config_path = tmp_path / "gallery.json"
    config_path.write_text(
        json.dumps({"projects_root": "images", "auto_scan_on_empty": False}),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.projects_root == (tmp_path / "images").resolve()
    assert config.auto_scan_on_empty is False


def test_parse_config_rejects_invalid_thumbnail_size(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        parse_config({"thumbnail_size": [320, 0]}, base_dir=tmp_path)
