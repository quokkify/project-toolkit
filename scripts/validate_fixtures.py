#!/usr/bin/env python3
"""Run executable language fixtures independently or as one canonical suite."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ("python", "node", "java")


def run(cmd: list[str], cwd: Path) -> None:
    """Run a fixture command with visible, repository-relative provenance."""
    print("+", " ".join(cmd), f"(cwd={cwd})")
    subprocess.run(cmd, cwd=cwd, check=True)


def validate_python(path: Path) -> None:
    """Compile, test, and package the Python fixture."""
    run([sys.executable, "-m", "compileall", "-q", "src"], path)
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], path)
    (path / "dist").mkdir()
    run(
        [sys.executable, "-m", "zipapp", "src", "-o", "dist/app.pyz", "-m", "app:main"],
        path,
    )


def validate_node(path: Path) -> None:
    """Lint, test, and build the Node.js fixture."""
    run(["npm", "run", "lint"], path)
    run(["npm", "test"], path)
    run(["npm", "run", "build"], path)


def validate_java(path: Path) -> None:
    """Compile, test, package, and Maven-test the Java fixture."""
    (path / "build/classes").mkdir(parents=True)
    (path / "build/test-classes").mkdir(parents=True)
    run(["javac", "-Xlint:all", "-d", "build/classes", "src/toolkit/App.java"], path)
    run(
        [
            "javac",
            "-Xlint:all",
            "-cp",
            "build/classes",
            "-d",
            "build/test-classes",
            "test/toolkit/AppTest.java",
        ],
        path,
    )
    run(["java", "-cp", "build/classes:build/test-classes", "toolkit.AppTest"], path)
    run(
        [
            "jar",
            "--create",
            "--file",
            "build/toolkit-java-fixture.jar",
            "-C",
            "build/classes",
            ".",
        ],
        path,
    )
    run(["mvn", "--batch-mode", "--no-transfer-progress", "test"], path)


VALIDATORS: dict[str, Callable[[Path], None]] = {
    "python": validate_python,
    "node": validate_node,
    "java": validate_java,
}


def validate_fixtures(languages: tuple[str, ...]) -> None:
    """Copy and execute only the requested language fixtures."""
    with tempfile.TemporaryDirectory(prefix="project-toolkit-fixtures-") as tmp:
        fixture_root = Path(tmp)
        for language in languages:
            fixture = shutil.copytree(
                ROOT / "tests/fixtures" / language,
                fixture_root / language,
            )
            VALIDATORS[language](fixture)
            print(f"{language} fixture: OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "language",
        choices=(*LANGUAGES, "all"),
        help="fixture suite to execute",
    )
    args = parser.parse_args()
    languages = LANGUAGES if args.language == "all" else (args.language,)
    validate_fixtures(languages)
    print("fixture validation: OK")


if __name__ == "__main__":
    main()
