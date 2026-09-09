from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / ".github/release-please/config.json"
TEMPLATE_CONFIG_PATH = ROOT / "templates/project/template/.github/release-please/config.json.jinja"
RENOVATE_PATH = ROOT / "renovate/default.json"


class ReleaseNotesConfigTests(unittest.TestCase):
    def load_config(self, path: Path) -> dict:
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsInstance(payload, dict)
        return payload

    def test_dependency_mapping_and_hidden_chore_contract(self) -> None:
        for path in (CONFIG_PATH, TEMPLATE_CONFIG_PATH):
            with self.subTest(path=path):
                package = self.load_config(path)["packages"]["."]
                sections = package["changelog-sections"]
                self.assertIn(
                    {"type": "deps", "section": "📦 Dependencies"},
                    sections,
                )
                self.assertIn(
                    {"type": "chore", "section": "🧹 Chores", "hidden": True},
                    sections,
                )
                self.assertEqual(package["changelog-path"], "CHANGELOG.md")

    def test_renovate_produces_release_please_native_dependency_type(self) -> None:
        renovate = self.load_config(RENOVATE_PATH)
        self.assertEqual(renovate["semanticCommits"], "enabled")
        self.assertEqual(renovate["semanticCommitType"], "deps")
        self.assertEqual(renovate["semanticCommitScope"], "deps")
        # Release Please 17.6.x sections match commit.type, not scope.  The
        # producer therefore emits deps(deps), which also preserves existing
        # consumers that already use that Conventional Commit form.
        self.assertEqual(
            f"{renovate['semanticCommitType']}({renovate['semanticCommitScope']})",
            "deps(deps)",
        )

    def test_root_and_template_have_matching_section_semantics(self) -> None:
        root_package = self.load_config(CONFIG_PATH)["packages"]["."]
        template_package = self.load_config(TEMPLATE_CONFIG_PATH)["packages"]["."]
        for package in (root_package, template_package):
            self.assertEqual(package["release-type"], "simple")
            self.assertTrue(package["bump-minor-pre-major"])
        self.assertEqual(
            root_package["changelog-sections"], template_package["changelog-sections"]
        )

    def test_copier_rendered_config_keeps_dependency_mapping(self) -> None:
        copier = shutil.which("copier")
        if copier is None:
            self.skipTest("copier is required for rendered template coverage")
        version_output = subprocess.run(
            [copier, "--version"], capture_output=True, text=True, check=False
        ).stdout
        version_match = re.search(r"(\d+)\.(\d+)\.(\d+)", version_output)
        with tempfile.TemporaryDirectory(prefix="release-notes-config-") as temporary:
            source = Path(temporary) / "template-source"
            shutil.copytree(
                ROOT,
                source,
                ignore=shutil.ignore_patterns(".git", "__pycache__"),
            )
            if version_match and tuple(map(int, version_match.groups())) < (9, 18, 2):
                copier_config = source / "copier.yml"
                copier_config.write_text(
                    copier_config.read_text(encoding="utf-8").replace(
                        '_min_copier_version: "9.18.2"',
                        f'_min_copier_version: "{version_match.group(0)}"',
                        1,
                    ),
                    encoding="utf-8",
                )
            destination = Path(temporary) / "fixture"
            result = subprocess.run(
                [
                    copier,
                    "copy",
                    "--trust",
                    "--defaults",
                    "--data",
                    "project_name=release-notes-fixture",
                    "--data",
                    "release_please=true",
                    str(source),
                    str(destination),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            rendered = self.load_config(
                destination / ".github/release-please/config.json"
            )["packages"]["."]
            self.assertEqual(rendered["changelog-path"], "CHANGELOG.md")
            self.assertIn(
                {"type": "deps", "section": "📦 Dependencies"},
                rendered["changelog-sections"],
            )
            self.assertIn(
                {"type": "chore", "section": "🧹 Chores", "hidden": True},
                rendered["changelog-sections"],
            )


if __name__ == "__main__":
    unittest.main()
