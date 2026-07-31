#!/usr/bin/env python3
"""Run ShellCheck against inline Bash in composite actions."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SHELLCHECK = shutil.which("shellcheck")
if SHELLCHECK is None:
    raise SystemExit("shellcheck executable is required")

failed = False
for path in sorted((ROOT / "actions").glob("*/action.yml")):
    data = yaml.safe_load(path.read_text())
    for index, step in enumerate(data.get("runs", {}).get("steps", []), 1):
        script = step.get("run") if isinstance(step, dict) else None
        if not isinstance(script, str):
            continue
        label = f"{path.relative_to(ROOT)} step {index}"
        result = subprocess.run(
            [SHELLCHECK, "--shell=bash", "--external-sources", "-"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            failed = True
            print(f"{label}:\n{result.stdout}{result.stderr}")
if failed:
    raise SystemExit(1)
print("composite action ShellCheck: OK")
