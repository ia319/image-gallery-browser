"""Streamlit presentation layer for Image Gallery Browser."""

from __future__ import annotations

from image_gallery_browser.models import (
    GalleryConfig,
    ScanErrorRecord,
    ScanRecord,
    ScanSummary,
)
from image_gallery_browser.services import GalleryService
from image_gallery_browser.ui.folder_tree import render_folder_selector
from image_gallery_browser.ui.gallery import render_gallery
from image_gallery_browser.ui.preview import render_image_preview

INITIAL_SCAN_KEY = "image_gallery_browser_initial_scan_attempted"


def render_app(st, service: GalleryService) -> None:
    """Render the gallery browser using service-layer operations."""
    initial_summary = _run_initial_scan_once(st, service)

    with st.sidebar:
        rescan_clicked = st.button("Rescan", type="primary")
        search = st.text_input("Search", value="")

    summary = service.rescan() if rescan_clicked else initial_summary
    with st.sidebar:
        _render_configuration(st, service)

    if summary is not None:
        render_scan_summary(
            st,
            summary,
            show_diagnostics=service.config.show_diagnostics,
        )

    folders = service.list_folders()
    selected_folder = render_folder_selector(st, folders)
    image_result = service.list_images(
        folder_relative_path=selected_folder,
        search=search.strip() or None,
    )
    selected_image = render_gallery(st, service, image_result)
    if selected_image is not None:
        render_image_preview(st, service, selected_image)


def render_scan_summary(
    st,
    summary: ScanSummary,
    *,
    show_diagnostics: bool = False,
) -> None:
    """Render aggregate scan counts and recoverable errors."""
    columns = st.columns(6)
    values = (
        ("Seen", summary.total_files_seen),
        ("Added", summary.images_added),
        ("Updated", summary.images_updated),
        ("Skipped", summary.images_skipped),
        ("Missing", summary.images_missing),
        ("Errors", summary.errors_count),
    )
    for column, (label, value) in zip(columns, values, strict=True):
        column.metric(label, value)

    if summary.errors:
        with st.expander("Errors", expanded=True):
            for error in summary.errors:
                st.code(format_scan_error(error, show_diagnostics=show_diagnostics))


def _run_initial_scan_once(st, service: GalleryService) -> ScanSummary | None:
    if st.session_state.get(INITIAL_SCAN_KEY):
        return None
    st.session_state[INITIAL_SCAN_KEY] = True
    return service.scan_on_empty()


def _render_configuration(st, service: GalleryService) -> None:
    latest_scan = service.latest_scan()
    is_empty = service.is_empty()

    st.caption(f"Gallery: {format_gallery_label(service.config)}")
    st.caption(f"Index: {format_index_status(latest_scan, is_empty)}")
    st.caption(f"Last scan: {format_last_scan(latest_scan)}")

    if service.config.show_diagnostics:
        with st.expander("Configuration details"):
            st.code(f"Root path: {service.config.projects_root}")
            st.code(f"Database path: {service.database_path}")


def format_gallery_label(config: GalleryConfig) -> str:
    """Return a safe short gallery label for default UI display."""
    if config.gallery_label:
        return config.gallery_label
    return config.projects_root.name or "Gallery"


def format_index_status(latest_scan: ScanRecord | None, is_empty: bool) -> str:
    """Return a user-facing index status without exposing filesystem paths."""
    if latest_scan is None:
        return "Empty" if is_empty else "Ready"
    if latest_scan.status == "completed":
        return "Ready"
    if latest_scan.status == "completed_with_errors":
        return "Ready with errors"
    if latest_scan.status == "failed":
        return "Failed"
    if latest_scan.status == "running":
        return "Scanning"
    return latest_scan.status.replace("_", " ").title()


def format_last_scan(latest_scan: ScanRecord | None) -> str:
    """Return compact last-scan text for sidebar display."""
    if latest_scan is None:
        return "None"
    scan_time = latest_scan.finished_at or latest_scan.started_at
    return f"{scan_time} ({latest_scan.status})"


def format_scan_error(
    error: ScanErrorRecord,
    *,
    show_diagnostics: bool = False,
) -> str:
    """Return recoverable error text with diagnostics gated by configuration."""
    path = error.relative_path or "root"
    safe_text = f"{error.stage.value} | {error.error_type.value} | {path}"
    if not show_diagnostics:
        return safe_text
    return f"{safe_text} | {error.message}"
