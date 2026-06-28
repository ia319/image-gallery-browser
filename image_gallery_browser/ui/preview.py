"""Image preview rendering for the Streamlit UI."""

from __future__ import annotations

from image_gallery_browser.models import ImageRecord
from image_gallery_browser.services import GalleryService


def format_file_size(file_size: int) -> str:
    """Format bytes as compact display text."""
    if file_size < 1024:
        return f"{file_size} B"
    if file_size < 1024 * 1024:
        return f"{file_size / 1024:.1f} KB"
    return f"{file_size / (1024 * 1024):.1f} MB"


def format_dimensions(image: ImageRecord) -> str:
    """Format image dimensions for display."""
    if image.width is None or image.height is None:
        return "Unknown"
    return f"{image.width} x {image.height}"


def render_image_preview(st, service: GalleryService, image: ImageRecord) -> None:
    """Render image preview with a dialog when available."""
    dialog = getattr(st, "dialog", None)
    if dialog is None:
        st.subheader("Image Preview")
        _render_preview_body(st, service, image)
        return

    @dialog("Image Preview")
    def show_preview() -> None:
        _render_preview_body(st, service, image)

    show_preview()


def _render_preview_body(st, service: GalleryService, image: ImageRecord) -> None:
    source_path = service.source_path(image)
    if source_path.exists():
        st.image(str(source_path), use_container_width=True)
    else:
        st.warning("Source image is missing.")

    st.text_input(
        "Relative path",
        value=image.source_relative_path,
        key=f"relative-path:{image.source_relative_path}",
        disabled=True,
    )
    st.caption(f"Filename: {image.filename}")
    st.caption(f"Dimensions: {format_dimensions(image)}")
    st.caption(f"Size: {format_file_size(image.file_size)}")
    st.caption(f"Modified time: {image.modified_time}")
    st.caption(f"Status: {image.status}")
