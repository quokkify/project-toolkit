from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_helpers", ROOT / "scripts/validate_helpers.py"
)
assert SPEC and SPEC.loader
helpers = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = helpers
SPEC.loader.exec_module(helpers)


class LoadYamlOrErrorTests(TestCase):
    def test_missing_yaml_records_validation_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            errors: list[str] = []
            result = helpers.load_yaml_or_error(Path(temporary) / "copier.yml", errors, "copier.yml")
        self.assertIsNone(result)
        self.assertEqual(len(errors), 1)
        self.assertIn("copier.yml: YAML parse failed:", errors[0])

    def test_malformed_yaml_records_validation_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "copier.yml"
            path.write_text("foo: [bar\n", encoding="utf-8")
            errors: list[str] = []
            result = helpers.load_yaml_or_error(path, errors, "copier.yml")
        self.assertIsNone(result)
        self.assertEqual(len(errors), 1)
        self.assertIn("copier.yml: YAML parse failed:", errors[0])

    def test_non_utf8_yaml_records_validation_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "copier.yml"
            path.write_bytes(b"\xff\xfe\xfd")
            errors: list[str] = []
            result = helpers.load_yaml_or_error(path, errors, "copier.yml")
        self.assertIsNone(result)
        self.assertEqual(len(errors), 1)
        self.assertIn("copier.yml: YAML parse failed:", errors[0])


class ValidatorIntegrationTests(TestCase):
    def run_validator(self, copier_content: bytes | None) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "checkout"
            shutil.copytree(ROOT, checkout, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            copier = checkout / "copier.yml"
            if copier_content is None:
                copier.unlink()
            else:
                copier.write_bytes(copier_content)
            return subprocess.run(
                [sys.executable, "scripts/validate.py", "--static"],
                cwd=checkout,
                env={**os.environ, "PYTHONPATH": str(checkout / "scripts")},
                text=True,
                capture_output=True,
                check=False,
            )

    def assert_yaml_error(self, content: bytes | None) -> None:
        result = self.run_validator(content)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        combined = result.stdout + result.stderr
        self.assertIn("copier.yml: YAML parse failed:", combined)
        self.assertNotIn("Traceback (most recent call last)", combined)

    def test_static_validator_reports_missing_copier_yaml(self) -> None:
        self.assert_yaml_error(None)

    def test_static_validator_reports_malformed_copier_yaml(self) -> None:
        self.assert_yaml_error(b"_min_copier_version: [broken\n")

    def test_static_validator_reports_non_utf8_copier_yaml(self) -> None:
        self.assert_yaml_error(b"\xff\xfe\xfd")


if __name__ == "__main__":
    main()
