#!/usr/bin/env python3
"""Compile, test, and package the executable Python fixture."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], cwd: Path) -> None:
    """Run a fixture command with visible provenance."""
    print("+", " ".join(cmd), f"(cwd={cwd})")
    subprocess.run(cmd, cwd=cwd, check=True)


def validate_python_fixture() -> None:
    """Run the complete Python fixture contract in an isolated copy."""
    with tempfile.TemporaryDirectory(prefix="project-toolkit-python-fixture-") as tmp:
        fixture = shutil.copytree(ROOT / "tests/fixtures/python", Path(tmp) / "python")
        run([sys.executable, "-m", "compileall", "-q", "src"], fixture)
        run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], fixture)
        (fixture / "dist").mkdir()
        run(
            [
                sys.executable,
                "-m",
                "zipapp",
                "src",
                "-o",
                "dist/app.pyz",
                "-m",
                "app:main",
            ],
            fixture,
        )
    print("python fixture: OK")


if __name__ == "__main__":
    validate_python_fixture()
