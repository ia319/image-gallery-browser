"""Check repository text files for UTF-8 without BOM and Unix LF endings."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_FILE_RE = re.compile(
    r"(^|/)(LICENSE|README|\.gitignore|\.gitattributes|\.editorconfig)$"
    r"|.*\.(cfg|css|html|ini|json|md|ps1|py|sh|toml|txt|yaml|yml)$"
    r"|^\.githooks/[^/]+$"
)
EXCLUDED_PATH_RE = re.compile(
    r"(^|/)(\.git|\.mypy_cache|\.pytest_cache|\.ruff_cache|\.venv|"
    r"__pycache__|data)(/|$)"
    r"|.*\.(db|gif|ico|jpeg|jpg|pdf|png|pyc|sqlite|sqlite3|webp)$"
)


def should_skip(path: Path) -> bool:
    relative_path = path.relative_to(ROOT).as_posix()
    return bool(EXCLUDED_PATH_RE.search(relative_path)) or not TEXT_FILE_RE.search(
        relative_path
    )


def iter_source_files() -> list[Path]:
    return [
        path
        for path in sorted(ROOT.rglob("*"))
        if path.is_file() and not should_skip(path)
    ]


def iter_staged_files() -> list[Path]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    paths = []
    for line in result.stdout.splitlines():
        path = ROOT / line
        if path.exists() and path.is_file() and not should_skip(path):
            paths.append(path)
    return paths


def check_bytes(path: Path, data: bytes) -> list[str]:
    failures: list[str] = []

    if data.startswith(b"\xef\xbb\xbf"):
        failures.append(f"{path}: UTF-8 BOM detected")

    if b"\r\n" in data:
        failures.append(f"{path}: CRLF line endings detected")

    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        failures.append(f"{path}: invalid UTF-8 at byte {exc.start}")

    return failures


def check_file(path: Path) -> list[str]:
    return check_bytes(path, path.read_bytes())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Check staged source files instead of every source file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    failures = []
    files = iter_staged_files() if args.staged else iter_source_files()
    for path in files:
        failures.extend(check_file(path))

    if failures:
        for failure in failures:
            print(failure)
        return 1

    print("Text file encoding and line endings passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
