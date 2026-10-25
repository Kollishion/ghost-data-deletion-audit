"""Run the full pipeline twice and compare output.csv SHA-256 digests."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def main() -> None:
    output = ROOT / "output.csv"
    hashes = []
    exit_codes = []
    for run in (1, 2):
        result = subprocess.run(
            [sys.executable, str(ROOT / "code" / "main.py")],
            cwd=ROOT, text=True, capture_output=True,
        )
        exit_codes.append(result.returncode)
        if not output.is_file():
            print(f"determinism=FAIL run={run} output.csv missing (exit={result.returncode})")
            raise SystemExit(1)
        hashes.append(digest(output))
    same = hashes[0] == hashes[1]
    print(f"determinism={'PASS' if same else 'FAIL'} sha256_run1={hashes[0]} sha256_run2={hashes[1]} pipeline_exit_codes={exit_codes}")
    if hashes[0] != hashes[1]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
