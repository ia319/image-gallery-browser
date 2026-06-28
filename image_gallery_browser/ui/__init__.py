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
ScanMetrics = ScanRecord | ScanSummary


def render_app(st, service: GalleryService) -> None:
    """Render the gallery browser using service-layer operations."""
    initial_summary = _run_initial_scan_once(st, service)

    with st.sidebar:
        rescan_clicked = st.button("Rescan", type="primary")
        search = st.text_input("Search", value="")

    summary = service.rescan() if rescan_clicked else initial_summary
    latest_scan = service.latest_scan()
    with st.sidebar:
        _render_configuration(st, service, latest_scan)

    scan_metrics = summary or latest_scan
    if scan_metrics is not None:
        render_scan_summary(
            st,
            scan_metrics,
            errors=_scan_errors_for_display(summary, latest_scan, service),
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
    scan_metrics: ScanMetrics,
    *,
    errors: tuple[ScanErrorRecord, ...] = (),
    show_diagnostics: bool = False,
) -> None:
    """Render aggregate scan counts and recoverable errors."""
    columns = st.columns(6)
    values = scan_metric_values(scan_metrics)
    for column, (label, value) in zip(columns, values, strict=True):
        column.metric(label, value)

    if errors:
        with st.expander("Errors", expanded=True):
            for error in errors:
                st.code(format_scan_error(error, show_diagnostics=show_diagnostics))


def _run_initial_scan_once(st, service: GalleryService) -> ScanSummary | None:
    if st.session_state.get(INITIAL_SCAN_KEY):
        return None
    st.session_state[INITIAL_SCAN_KEY] = True
    return service.scan_on_empty()


def _render_configuration(
    st,
    service: GalleryService,
    latest_scan: ScanRecord | None,
) -> None:
    is_empty = service.is_empty()

    st.caption(f"Gallery: {format_gallery_label(service.config)}")
    st.caption(f"Index: {format_index_status(latest_scan, is_empty)}")
    st.caption(f"Last scan: {format_last_scan(latest_scan)}")

    if service.config.show_diagnostics:
        with st.expander("Configuration details"):
            st.code(f"Root path: {service.config.projects_root}")
            st.code(f"Database path: {service.database_path}")


def _scan_errors_for_display(
    summary: ScanSummary | None,
    latest_scan: ScanRecord | None,
    service: GalleryService,
) -> tuple[ScanErrorRecord, ...]:
    if summary is not None:
        return summary.errors
    if latest_scan is None or latest_scan.errors_count == 0:
        return ()
    return service.list_scan_errors(latest_scan.id)


def scan_metric_values(scan_metrics: ScanMetrics) -> tuple[tuple[str, int], ...]:
    """Return metric labels and values for current or persisted scan data."""
    return (
        ("Seen", scan_metrics.total_files_seen),
        ("Added", scan_metrics.images_added),
        ("Updated", scan_metrics.images_updated),
        ("Skipped", scan_metrics.images_skipped),
        ("Missing", scan_metrics.images_missing),
        ("Errors", scan_metrics.errors_count),
    )


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
