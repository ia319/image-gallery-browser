"""Check local Markdown links without external dependencies."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def iter_markdown_files() -> list[Path]:
    return [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]


def is_external_link(target: str) -> bool:
    parsed = urlparse(target)
    return parsed.scheme in {"http", "https", "mailto"}


def normalize_link_target(target: str) -> str:
    return target.split("#", 1)[0].strip()


def check_file(path: Path) -> list[str]:
    failures: list[str] = []
    if not path.exists():
        return failures

    content = path.read_text(encoding="utf-8")
    for match in MARKDOWN_LINK_RE.finditer(content):
        raw_target = match.group(1)
        target = normalize_link_target(raw_target)
        if not target or is_external_link(target):
            continue

        linked_path = (path.parent / target).resolve()
        try:
            linked_path.relative_to(ROOT)
        except ValueError:
            failures.append(f"{path}: link escapes repository: {raw_target}")
            continue

        if not linked_path.exists():
            failures.append(f"{path}: missing local link target: {raw_target}")

    return failures


def main() -> int:
    failures = []
    for markdown_file in iter_markdown_files():
        failures.extend(check_file(markdown_file))

    if failures:
        for failure in failures:
            print(failure)
        return 1

    print("Markdown local links passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
