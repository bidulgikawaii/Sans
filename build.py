"""Build the Sans client and server with PyInstaller.

Run from the project directory:
    python build.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
APP_NAME = "TheBattles"
SERVER_NAME = "TheBattlesServer"
DATA_DIRECTORIES = ("Image", "Font", "Sound")


def pyinstaller_data_arg(directory: str) -> str:
    """Return a platform-correct PyInstaller --add-data argument."""
    return f"{ROOT / directory}{os.pathsep}{directory}"


def ensure_required_paths() -> None:
    required = [ROOT / "TheTest.py", ROOT / "Server.py"]
    required.extend(ROOT / directory for directory in DATA_DIRECTORIES)
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing build input: " + ", ".join(missing))


def run_pyinstaller(entry_point: str, name: str, windowed: bool) -> None:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        name,
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR / name),
        "--specpath",
        str(BUILD_DIR),
        "--paths",
        str(ROOT),
    ]
    if windowed:
        command.append("--windowed")
    else:
        command.append("--console")

    for directory in DATA_DIRECTORIES:
        command.extend(("--add-data", pyinstaller_data_arg(directory)))

    command.append(str(ROOT / entry_point))
    print("Running:", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    try:
        ensure_required_paths()
        run_pyinstaller("TheTest.py", APP_NAME, windowed=True)
        run_pyinstaller("Server.py", SERVER_NAME, windowed=False)
    except FileNotFoundError as error:
        print(f"Build failed: {error}", file=sys.stderr)
        print("Install dependencies with: python -m pip install -r requirements.txt", file=sys.stderr)
        print("Install PyInstaller with: python -m pip install pyinstaller", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print(f"PyInstaller failed with exit code {error.returncode}.", file=sys.stderr)
        return error.returncode or 1

    print()
    print(f"Client: {DIST_DIR / APP_NAME / (APP_NAME + '.exe')}")
    print(f"Server: {DIST_DIR / SERVER_NAME / (SERVER_NAME + '.exe')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
