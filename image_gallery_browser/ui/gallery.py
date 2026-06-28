"""Thumbnail grid rendering for the Streamlit UI."""

from __future__ import annotations

from collections.abc import Sequence

from image_gallery_browser.models import ImageRecord
from image_gallery_browser.services import GalleryService, ImageQueryResult

GRID_COLUMNS = 4


def chunk_images(
    images: Sequence[ImageRecord],
    columns: int = GRID_COLUMNS,
) -> tuple[tuple[ImageRecord, ...], ...]:
    """Split images into fixed-width rows for grid rendering."""
    if columns <= 0:
        raise ValueError("columns must be positive")
    return tuple(
        tuple(images[index : index + columns])
        for index in range(0, len(images), columns)
    )


def render_gallery(
    st,
    service: GalleryService,
    image_result: ImageQueryResult,
) -> ImageRecord | None:
    """Render a thumbnail grid and return the selected image."""
    if image_result.truncated:
        st.warning(f"Showing {image_result.limit} images. Narrow the folder or search.")

    if not image_result.images:
        st.info("No images found.")
        return None

    selected_image = None
    for row in chunk_images(image_result.images):
        columns = st.columns(GRID_COLUMNS)
        for column, image in zip(columns, row, strict=False):
            with column:
                thumbnail_path = service.thumbnail_path(image)
                if thumbnail_path is not None and thumbnail_path.exists():
                    st.image(
                        str(thumbnail_path),
                        caption=image.filename,
                        use_container_width=True,
                    )
                else:
                    st.caption(image.filename)
                    st.warning("Thumbnail unavailable.")
                if st.button("View", key=f"view:{image.source_relative_path}"):
                    selected_image = image

    return selected_image
