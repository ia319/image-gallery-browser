from pathlib import Path

from image_gallery_browser.database import GalleryDatabase, root_path_hash
from image_gallery_browser.errors import ScanErrorType, ScanStage
from image_gallery_browser.models import (
    FolderRecord,
    ImageRecord,
    ScanErrorRecord,
    ScanSummary,
)
from image_gallery_browser.paths import ROOT_RELATIVE_PATH


def test_initialize_schema_is_repeatable(tmp_path: Path) -> None:
    with GalleryDatabase(tmp_path / "gallery.sqlite") as database:
        assert database.get_schema_version() == "1"

        root_id = database.upsert_root(tmp_path / "gallery")
        database.initialize_schema()

        assert database.count_rows("roots") == 1
        assert database.upsert_root(tmp_path / "gallery") == root_id


def test_upsert_root_deduplicates_by_normalized_hash(tmp_path: Path) -> None:
    root = tmp_path / "gallery"
    root.mkdir()

    with GalleryDatabase(tmp_path / "gallery.sqlite") as database:
        first_root_id = database.upsert_root(root)
        second_root_id = database.upsert_root(root.resolve(), root_label="Gallery")

        assert first_root_id == second_root_id
        assert database.count_rows("roots") == 1
        assert root_path_hash(root) == root_path_hash(root.resolve())


def test_upsert_folder_and_image_deduplicates_source_path(tmp_path: Path) -> None:
    with GalleryDatabase(tmp_path / "gallery.sqlite") as database:
        root_id = database.upsert_root(tmp_path / "gallery")
        database.upsert_folder(
            root_id,
            FolderRecord(ROOT_RELATIVE_PATH, "gallery", None, 0),
        )
        database.upsert_folder(
            root_id,
            FolderRecord("Project", "Project", ROOT_RELATIVE_PATH, 1),
        )

        image = ImageRecord(
            source_relative_path="Project/render.png",
            folder_relative_path="Project",
            filename="render.png",
            extension=".png",
            file_size=10,
            modified_time=1.0,
            width=100,
            height=80,
            thumbnail_relative_path="thumbs/render.webp",
        )
        added = database.upsert_image(root_id, image)
        skipped = database.upsert_image(root_id, image)
        updated = database.upsert_image(
            root_id,
            ImageRecord(
                source_relative_path="Project/render.png",
                folder_relative_path="Project",
                filename="render.png",
                extension=".png",
                file_size=12,
                modified_time=2.0,
                width=100,
                height=80,
                thumbnail_relative_path="thumbs/render.webp",
            ),
        )

        images = database.list_images(root_id)

        assert added.action == "added"
        assert skipped.action == "skipped"
        assert updated.action == "updated"
        assert added.image_id == skipped.image_id == updated.image_id
        assert database.count_rows("images") == 1
        assert images[0].file_size == 12
        assert images[0].modified_time == 2.0


def test_mark_missing_images_and_folders_preserves_rows(tmp_path: Path) -> None:
    with GalleryDatabase(tmp_path / "gallery.sqlite") as database:
        root_id = database.upsert_root(tmp_path / "gallery")
        database.upsert_folder(
            root_id,
            FolderRecord(ROOT_RELATIVE_PATH, "gallery", None, 0),
        )
        database.upsert_folder(
            root_id,
            FolderRecord("Project", "Project", ROOT_RELATIVE_PATH, 1),
        )
        database.upsert_folder(
            root_id,
            FolderRecord("Other", "Other", ROOT_RELATIVE_PATH, 1),
        )
        database.upsert_image(
            root_id,
            ImageRecord("Project/render.png", "Project", "render.png", ".png", 1, 1.0),
        )
        database.upsert_image(
            root_id,
            ImageRecord("Other/view.jpg", "Other", "view.jpg", ".jpg", 1, 1.0),
        )

        missing_images = database.mark_missing_images(root_id, {"Project/render.png"})
        missing_folders = database.mark_missing_folders(
            root_id,
            {ROOT_RELATIVE_PATH, "Project"},
        )

        assert missing_images == 1
        assert missing_folders == 1
        assert database.count_rows("images") == 2
        assert [
            image.source_relative_path for image in database.list_images(root_id)
        ] == ["Project/render.png"]
        assert [
            image.source_relative_path
            for image in database.list_images(root_id, status="missing")
        ] == ["Other/view.jpg"]
        assert [folder.relative_path for folder in database.list_folders(root_id)] == [
            ROOT_RELATIVE_PATH,
            "Project",
        ]
        assert [
            folder.relative_path
            for folder in database.list_folders(root_id, status="missing")
        ] == ["Other"]


def test_list_images_includes_descendant_folders_by_default(tmp_path: Path) -> None:
    with GalleryDatabase(tmp_path / "gallery.sqlite") as database:
        root_id = database.upsert_root(tmp_path / "gallery")
        for folder in (
            FolderRecord(ROOT_RELATIVE_PATH, "gallery", None, 0),
            FolderRecord("Project", "Project", ROOT_RELATIVE_PATH, 1),
            FolderRecord("Project/Renders", "Renders", "Project", 2),
            FolderRecord("Other", "Other", ROOT_RELATIVE_PATH, 1),
        ):
            database.upsert_folder(root_id, folder)

        for image in (
            ImageRecord("Project/cover.jpg", "Project", "cover.jpg", ".jpg", 1, 1.0),
            ImageRecord(
                "Project/Renders/view.png",
                "Project/Renders",
                "view.png",
                ".png",
                1,
                1.0,
            ),
            ImageRecord("Other/view.png", "Other", "view.png", ".png", 1, 1.0),
        ):
            database.upsert_image(root_id, image)

        project_images = database.list_images(
            root_id,
            folder_relative_path="Project",
        )
        direct_project_images = database.list_images(
            root_id,
            folder_relative_path="Project",
            include_descendants=False,
        )
        searched_images = database.list_images(root_id, search="cover")

        assert [image.source_relative_path for image in project_images] == [
            "Project/Renders/view.png",
            "Project/cover.jpg",
        ]
        assert [image.source_relative_path for image in direct_project_images] == [
            "Project/cover.jpg"
        ]
        assert [image.source_relative_path for image in searched_images] == [
            "Project/cover.jpg"
        ]


def test_scan_records_store_status_and_errors(tmp_path: Path) -> None:
    with GalleryDatabase(tmp_path / "gallery.sqlite") as database:
        root_id = database.upsert_root(tmp_path / "gallery")
        scan_id = database.start_scan(root_id)
        error = ScanErrorRecord(
            stage=ScanStage.SCAN,
            error_type=ScanErrorType.PERMISSION_DENIED,
            relative_path="blocked",
            message="blocked directory",
        )

        database.add_scan_error(scan_id, error)
        database.finish_scan(
            scan_id,
            ScanSummary(
                total_files_seen=2,
                images_added=1,
                errors=(error,),
            ),
        )

        failed_scan_id = database.start_scan(root_id)
        database.fail_scan(failed_scan_id, errors_count=1)

        assert database.get_scan_status(scan_id) == "completed_with_errors"
        assert database.get_scan_status(failed_scan_id) == "failed"
        assert database.list_scan_errors(scan_id) == (error,)
