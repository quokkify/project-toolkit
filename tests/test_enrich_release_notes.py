import importlib.util
import tempfile
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("enrich_release_notes", ROOT / "scripts/enrich_release_notes.py")
assert spec and spec.loader
notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notes)


class RichNotesTests(TestCase):
    def test_standard_release_please_links_are_supported_by_workflow_contract(self):
        workflow = (ROOT / ".github/workflows/release-please.yml").read_text(encoding="utf-8")
        self.assertIn(r"\[#(\d+)\]\([^)]*\)", workflow)

    def test_extracts_sections_and_preserves_java_fence(self):
        body = "## Description\r\ninternal\r\n## Usage example\r\n```java\r\nVerifier.verify();\r\n```\r\n## Migration\r\n<!-- guidance -->\r\n"
        sections = notes.extract_rich_sections(body)
        self.assertIn("```java\nVerifier.verify();\n```", sections["usage example"])
        self.assertNotIn("migration", sections)

    def test_comments_and_unknown_or_duplicate_headings_are_ignored(self):
        body = "## Highlight\n<!-- only guidance -->\n## Highlight\nsecond\n## Other\nno\n"
        self.assertEqual(notes.extract_rich_sections(body), {})

    def test_enrichment_is_sorted_and_idempotent(self):
        changelog = "# Changelog\n\n## 2.1.0\n\n### ✨ Features\n\n- normal\n"
        prs = [
            {"number": 12, "title": "Second", "body": "## Migration\nUpgrade now."},
            {"number": 4, "title": "First", "body": "## Highlight\nImportant."},
            {"number": 99, "title": "Empty", "body": "## Usage example\n<!-- optional -->"},
        ]
        first = notes.enrich_changelog(changelog, prs)
        self.assertLess(first.index("#### First"), first.index("#### Second"))
        self.assertEqual(notes.enrich_changelog(first, prs), first)
        self.assertEqual(first.count("rich-release-notes"), 2)

    def test_shell_looking_text_is_data(self):
        changelog = "## 1.0.0\n"
        body = "## Release notes\n${{ github.token }}\n$(touch /tmp/pwned)\n"
        output = notes.enrich_changelog(changelog, [{"number": 7, "body": body}])
        self.assertIn("${{ github.token }}", output)
        self.assertIn("$(touch /tmp/pwned)", output)

    def test_cli_writes_generated_markdown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            changelog = root / "CHANGELOG.md"
            prs = root / "prs.json"
            changelog.write_text("## 1.0.0\n", encoding="utf-8")
            prs.write_text('[{"number": 1, "body": "## Highlight\\nHello"}]', encoding="utf-8")
            output = notes.enrich_changelog(changelog.read_text(), [{"number": 1, "body": "## Highlight\nHello"}])
            changelog.write_text(output, encoding="utf-8")
            self.assertIn("### Highlights", changelog.read_text())

    def test_headings_inside_fences_are_not_sections_or_versions(self):
        body = "## Usage example\n```java\n## Migration\n```\nAfter\n"
        self.assertIn("```java\n## Migration\n```\nAfter", notes.extract_rich_sections(body)["usage example"])
        self.assertNotIn("migration", notes.extract_rich_sections(body))
        changelog = "## 1.0.0\n```md\n## fake\n```\n### Features\n- x\n## 0.9.0\n"
        self.assertEqual(len(notes._version_ranges(changelog)), 2)

    def test_release_body_block_is_replaced_once(self):
        body = "## Generated\n" + notes.BLOCK_START + "\nold\n" + notes.BLOCK_END + "\nFooter\n"
        updated = notes.enrich_release_body(body, "new\n```md\n## nested\n```")
        self.assertEqual(updated.count(notes.BLOCK_START), 1)
        self.assertIn("new", updated)
        self.assertNotIn("old", updated)

    def test_empty_sources_remove_existing_block(self):
        changelog = "## 1.0.0\n\n" + notes.BLOCK_START + "\nold\n" + notes.BLOCK_END + "\n\n### Features\n- x\n"
        updated = notes.enrich_changelog(changelog, [])
        self.assertNotIn(notes.BLOCK_START, updated)
        self.assertIn("### Features", updated)

    def test_legacy_marker_cleanup_preserves_fenced_headings(self):
        changelog = (
            "## 1.0.0\n\n<!-- project-toolkit:rich-release-notes pr=1 -->\n"
            "### Highlights\nold\n```md\n### Keep this\n```\n### Features\n- normal\n"
        )
        updated = notes.enrich_changelog(changelog, [])
        self.assertNotIn("old", updated)
        self.assertIn("### Features", updated)

    def test_legacy_marker_cleanup_in_generated_helper_matches_root(self):
        template = (ROOT / "templates/project/template/.github/scripts/enrich_release_notes.py.jinja").read_text(encoding="utf-8")
        self.assertIn("def _remove_legacy", template)
        self.assertIn("if not had_block: top=_remove_legacy(top)", template)

    def test_nested_fences_require_matching_outer_length(self):
        body = "## Usage example\n````markdown\n```java\n## Migration\n```\n````\n## Migration\nApply it.\n"
        sections = notes.extract_rich_sections(body)
        self.assertIn("usage example", sections)
        self.assertIn("migration", sections)
        changelog = "## 1.0.0\n````md\n## fake\n```\n````\n## 0.9.0\n"
        self.assertEqual(len(notes._version_ranges(changelog)), 2)

    def test_reserved_delimiters_in_pr_body_are_rejected(self):
        body = f"## Highlight\nattacker {notes.BLOCK_END} tail"
        output = notes.enrich_changelog("## 1.0.0\n", [{"number": 7, "body": body}])
        self.assertNotIn(notes.BLOCK_START, output)
        self.assertEqual(notes.enrich_changelog(output, [{"number": 7, "body": body}]), output)

    def test_reserved_delimiters_in_pr_title_are_rejected(self):
        title = f"unsafe {notes.BLOCK_END} title"
        prs = [{"number": 7, "title": title, "body": "## Highlight\ncontent"}]
        output = notes.enrich_changelog("## 1.0.0\n", prs)
        self.assertNotIn(notes.BLOCK_START, output)
        self.assertEqual(notes.enrich_changelog(output, prs), output)

    def test_workflow_parser_contract_tracks_nested_fences_and_rich_block(self):
        workflow = (ROOT / ".github/workflows/release-please.yml").read_text(encoding="utf-8")
        self.assertEqual(workflow.count("fence = (token[0], len(token))"), 2)
        self.assertEqual(workflow.count("in_rich_block = False"), 4)
        self.assertIn("not in_rich_block and fence is None", workflow)