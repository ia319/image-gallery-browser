"""Folder selection helpers for the Streamlit UI."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from image_gallery_browser.models import FolderRecord
from image_gallery_browser.paths import ROOT_RELATIVE_PATH


@dataclass(frozen=True)
class FolderOption:
    """Represent one selectable folder label."""

    relative_path: str
    label: str


def build_folder_options(folders: Sequence[FolderRecord]) -> tuple[FolderOption, ...]:
    """Return stable display labels for folder records."""
    if not folders:
        return (FolderOption(ROOT_RELATIVE_PATH, "Root"),)

    return tuple(_folder_option(folder) for folder in folders)


def render_folder_selector(st, folders: Sequence[FolderRecord]) -> str:
    """Render a folder selector and return the selected relative path."""
    options = build_folder_options(folders)
    selected_label = st.selectbox(
        "Folder",
        [option.label for option in options],
        index=0,
    )
    selected = next(option for option in options if option.label == selected_label)
    return selected.relative_path


def _folder_option(folder: FolderRecord) -> FolderOption:
    name = "Root" if folder.relative_path == ROOT_RELATIVE_PATH else folder.name
    indent = "  " * folder.depth
    return FolderOption(folder.relative_path, f"{indent}{name}")
