"""fetch_solver.py — Download the TexasSolver v0.2.0 console binary.

TexasSolver (github.com/bupticybee/TexasSolver, AGPL v3) is the multi-street
DCFR engine texas_adapter.py drives. This fetches the Windows release zip
and extracts it into cfr_solver/bin/ (gitignored). Run once:

    python fetch_solver.py

The console executable lands at bin/console_solver.exe (plus its resources/
directory, which the exe expects next to itself).
"""

from __future__ import annotations

import io
import sys
import urllib.request
import zipfile
from pathlib import Path

RELEASE_URL = (
    "https://github.com/bupticybee/TexasSolver/releases/download/"
    "v0.2.0/TexasSolver-v0.2.0-Windows.zip"
)
BIN_DIR = Path(__file__).parent / "bin"


def fetch() -> Path:
    BIN_DIR.mkdir(exist_ok=True)
    exe = find_console_exe()
    if exe:
        print(f"Already present: {exe}")
        return exe

    print(f"Downloading {RELEASE_URL} (~39 MB)...")
    with urllib.request.urlopen(RELEASE_URL) as resp:
        data = resp.read()
    print(f"Downloaded {len(data) // 1024 // 1024} MB, extracting...")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(BIN_DIR)

    exe = find_console_exe()
    if not exe:
        sys.exit(f"Extraction finished but no console_solver.exe found under {BIN_DIR}")
    print(f"Ready: {exe}")
    return exe


def find_console_exe() -> Path | None:
    matches = list(BIN_DIR.rglob("console_solver.exe"))
    return matches[0] if matches else None


if __name__ == "__main__":
    fetch()
