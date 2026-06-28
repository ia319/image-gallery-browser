"""Streamlit entry point for Image Gallery Browser."""

from __future__ import annotations

from image_gallery_browser.config import load_config
from image_gallery_browser.errors import ConfigError
from image_gallery_browser.services import GalleryService
from image_gallery_browser.ui import render_app


def main() -> None:
    """Render the Streamlit application."""
    import streamlit as st

    st.set_page_config(page_title="Image Gallery Browser", layout="wide")
    st.title("Image Gallery Browser")

    try:
        config = load_config()
    except ConfigError:
        st.error("Configuration could not be loaded. Check config.example.json.")
        return

    with GalleryService(config) as service:
        render_app(st, service)


if __name__ == "__main__":
    main()
