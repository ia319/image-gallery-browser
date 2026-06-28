# Image Gallery Browser

Browse local image folders with Streamlit, Pillow thumbnails, and SQLite indexing.

## Features

- Scan a configured image root recursively.
- Store source image paths as root-relative POSIX paths.
- Generate cached thumbnails outside the source image directory.
- Keep source image folders read-only.
- Prepare a modular codebase for scanning, indexing, thumbnails, and UI.

## Quick Start

Create a virtual environment, install reviewed dependencies, and run the app.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

## Configuration

Copy `config.example.json` and adjust `projects_root` for a local folder or UNC
network share.

```json
{
  "projects_root": "sample_projects",
  "data_dir": "data",
  "thumbnail_size": [320, 320],
  "supported_extensions": [".jpg", ".jpeg", ".png", ".webp"],
  "auto_scan_on_empty": true,
  "max_images_per_view": 200
}
```

Use `auto_scan_on_empty: false` for large local folders or network shares.

## Quality Checks

Run the local checks before committing changes.

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python scripts/check_links.py
python scripts/check_text_files.py --staged
```

Enable the repository hook for automatic checks before each commit.

```powershell
git config core.hooksPath .githooks
```

## License

MIT
