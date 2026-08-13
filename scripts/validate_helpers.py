from __future__ import annotations

from pathlib import Path

import yaml


def load_yaml_or_error(path: Path, errors: list[str], label: str) -> object | None:
    """Load YAML and record a validation error instead of raising."""
    try:
        return yaml.safe_load(path.read_text())
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        errors.append(f"{label}: YAML parse failed: {exc}")
        return None
