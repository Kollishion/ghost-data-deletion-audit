"""Audit the curated file set intended for code.zip."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE_ROOTS = (ROOT / "code",)
INCLUDE_FILES = (ROOT / "README.md", ROOT / "DESIGN.md", ROOT / "PROGRESS.md")
FORBIDDEN_PARTS = {"dataset", "__pycache__", ".venv"}
SECRET_PATTERN = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|secret|bearer)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,}"
)
OUTPUT_BACKUP = re.compile(r"(?i)(?:^|[_ .-])output(?:[_ .-].*)?backup|output.*backup")


def package_files() -> list[Path]:
    files = [
        path for folder in INCLUDE_ROOTS for path in folder.rglob("*")
        if path.is_file()
        and "__pycache__" not in {part.lower() for part in path.relative_to(ROOT).parts}
        and ".venv" not in {part.lower() for part in path.relative_to(ROOT).parts}
        and path.name.lower() != ".env"
        and not OUTPUT_BACKUP.search(path.name)
    ]
    files.extend(path for path in INCLUDE_FILES if path.is_file())
    return sorted(set(files), key=lambda path: path.relative_to(ROOT).as_posix().lower())


def main() -> None:
    errors: list[str] = []
    if not (ROOT / "README.md").is_file():
        errors.append("README.md is missing")
    files = package_files()
    for path in files:
        rel = path.relative_to(ROOT)
        parts = {part.lower() for part in rel.parts}
        if parts & FORBIDDEN_PARTS or path.name.lower() == ".env":
            errors.append(f"forbidden package path: {rel}")
        if OUTPUT_BACKUP.search(path.name):
            errors.append(f"output backup would be packaged: {rel}")
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if SECRET_PATTERN.search(content):
            errors.append(f"possible API key/token pattern in {rel}")
    print("code_zip_files:")
    for path in files:
        print(f"  {path.relative_to(ROOT).as_posix()}")
    if errors:
        print(f"hygiene=FAIL errors={len(errors)}")
        for error in errors:
            print(f"  {error}")
        raise SystemExit(1)
    print(f"hygiene=PASS files={len(files)} README.md=present")


if __name__ == "__main__":
    main()
