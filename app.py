"""Streamlit entry point for Image Gallery Browser."""

from __future__ import annotations

import os
from pathlib import Path

from image_gallery_browser.config import load_config
from image_gallery_browser.errors import ConfigError
from image_gallery_browser.models import GalleryConfig
from image_gallery_browser.services import GalleryService
from image_gallery_browser.ui import render_app

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH_ENV = "IMAGE_GALLERY_CONFIG"


def load_app_config() -> GalleryConfig:
    """Load configuration from an explicit override or the deployment directory."""
    config_path = os.environ.get(CONFIG_PATH_ENV)
    if config_path:
        return load_config(config_path, project_dir=Path.cwd())
    return load_config(project_dir=APP_DIR)


def main() -> None:
    """Render the Streamlit application."""
    import streamlit as st

    st.set_page_config(page_title="Image Gallery Browser", layout="wide")
    st.title("Image Gallery Browser")

    try:
        config = load_app_config()
    except ConfigError:
        st.error("Configuration could not be loaded. Check the gallery JSON file.")
        return

    with GalleryService(config) as service:
        render_app(st, service)


if __name__ == "__main__":
    main()
