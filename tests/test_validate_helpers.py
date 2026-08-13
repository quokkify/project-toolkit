from __future__ import annotations

import importlib.util
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
            missing = Path(temporary) / "copier.yml"
            errors: list[str] = []

            result = helpers.load_yaml_or_error(missing, errors, "copier.yml")

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


if __name__ == "__main__":
    main()
