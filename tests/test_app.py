import sys
from pathlib import Path
from types import SimpleNamespace

import app
from image_gallery_browser.models import GalleryConfig


class StubGalleryService:
    def __init__(self, config: GalleryConfig) -> None:
        self.config = config

    def __enter__(self) -> "StubGalleryService":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None


def test_main_loads_config_from_app_directory(monkeypatch, tmp_path: Path) -> None:
    calls = {}
    streamlit = SimpleNamespace(
        set_page_config=lambda **kwargs: calls.setdefault("page_config", kwargs),
        title=lambda value: calls.setdefault("title", value),
        error=lambda value: calls.setdefault("error", value),
    )

    def load_app_config_stub() -> GalleryConfig:
        return GalleryConfig(
            projects_root=tmp_path / "projects",
            data_dir=tmp_path / "data",
        )

    def render_app_stub(streamlit_module, service: StubGalleryService) -> None:
        calls["rendered"] = streamlit_module is streamlit
        calls["service_config"] = service.config

    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    monkeypatch.setattr(app, "load_app_config", load_app_config_stub)
    monkeypatch.setattr(app, "GalleryService", StubGalleryService)
    monkeypatch.setattr(app, "render_app", render_app_stub)

    app.main()

    assert calls["title"] == "Image Gallery Browser"
    assert calls["rendered"] is True
    assert calls["service_config"].projects_root == tmp_path / "projects"


def test_load_app_config_defaults_to_app_directory(monkeypatch, tmp_path: Path) -> None:
    calls = {}
    monkeypatch.delenv(app.CONFIG_PATH_ENV, raising=False)

    def load_config_stub(*, project_dir: Path) -> GalleryConfig:
        calls["project_dir"] = project_dir
        return GalleryConfig(
            projects_root=tmp_path / "projects",
            data_dir=tmp_path / "data",
        )

    monkeypatch.setattr(app, "load_config", load_config_stub)

    config = app.load_app_config()

    assert calls["project_dir"] == app.APP_DIR
    assert config.projects_root == tmp_path / "projects"


def test_load_app_config_accepts_environment_path(monkeypatch, tmp_path: Path) -> None:
    calls = {}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(app.CONFIG_PATH_ENV, "gallery.json")

    def load_config_stub(config_path: str, *, project_dir: Path) -> GalleryConfig:
        calls["config_path"] = config_path
        calls["project_dir"] = project_dir
        return GalleryConfig(
            projects_root=tmp_path / "projects",
            data_dir=tmp_path / "data",
        )

    monkeypatch.setattr(app, "load_config", load_config_stub)

    config = app.load_app_config()

    assert calls["config_path"] == "gallery.json"
    assert calls["project_dir"] == tmp_path
    assert config.data_dir == tmp_path / "data"
