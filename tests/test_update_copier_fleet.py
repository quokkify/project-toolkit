from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main, mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "update_copier_fleet", ROOT / "scripts/update_copier_fleet.py"
)
assert SPEC and SPEC.loader
fleet = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = fleet
SPEC.loader.exec_module(fleet)


class DiscoveryTests(TestCase):
    @mock.patch.object(fleet, "gh_json", return_value=[])
    def test_public_only_discovery_is_explicit(self, gh_json_mock: mock.Mock) -> None:
        self.assertEqual(fleet.discover_repositories("quokkify", env={}, public_only=True), [])
        arguments = gh_json_mock.call_args.args[0]
        self.assertIn("--visibility", arguments)
        self.assertEqual(arguments[arguments.index("--visibility") + 1], "public")


class TemplateSourceTests(TestCase):
    def test_accepts_supported_github_source_forms(self) -> None:
        expected = "quokkify/project-toolkit"
        for source in (
            "gh:quokkify/project-toolkit",
            "https://github.com/quokkify/project-toolkit.git",
            "git@github.com:quokkify/project-toolkit.git",
            "ssh://git@github.com/quokkify/project-toolkit/",
        ):
            with self.subTest(source=source):
                self.assertEqual(fleet.normalize_template_source(source), expected)

    def test_rejects_local_or_ambiguous_sources(self) -> None:
        for source in ("../project-toolkit", "/tmp/template", "github.com/quokkify/project-toolkit"):
            with self.subTest(source=source):
                self.assertIsNone(fleet.normalize_template_source(source))

    def test_requires_answers_source(self) -> None:
        self.assertEqual(
            fleet.parse_template_source("_src_path: gh:quokkify/project-toolkit\n"),
            "gh:quokkify/project-toolkit",
        )
        with self.assertRaises(fleet.FleetUpdateError):
            fleet.parse_template_source("project_name: example\n")

    def test_rewrites_copier_shorthand_to_renovate_compatible_url(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            answers = repository / fleet.ANSWERS_FILE
            answers.write_text(
                "_commit: v2.8.2\n_src_path: gh:quokkify/project-toolkit\nproject_name: example\n",
                encoding="utf-8",
            )
            self.assertTrue(
                fleet.canonicalize_answers_source(repository, "quokkify/project-toolkit")
            )
            self.assertEqual(
                answers.read_text(encoding="utf-8"),
                "_commit: v2.8.2\n"
                "_src_path: https://github.com/quokkify/project-toolkit.git\n"
                "project_name: example\n",
            )

    def test_leaves_canonical_copier_source_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            answers = repository / fleet.ANSWERS_FILE
            content = "_commit: v2.8.2\n_src_path: https://github.com/quokkify/project-toolkit.git\n"
            answers.write_text(content, encoding="utf-8")
            self.assertFalse(
                fleet.canonicalize_answers_source(repository, "quokkify/project-toolkit")
            )
            self.assertEqual(answers.read_text(encoding="utf-8"), content)

    def test_rejects_duplicate_copier_source_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            answers = repository / fleet.ANSWERS_FILE
            answers.write_text(
                "_src_path: gh:quokkify/project-toolkit\n"
                "_src_path: gh:quokkify/project-toolkit\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(fleet.FleetUpdateError, "exactly one"):
                fleet.canonicalize_answers_source(repository, "quokkify/project-toolkit")

    def test_rejects_symlinked_answers_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            target = repository / "target.yml"
            target.write_text(
                "_src_path: gh:quokkify/project-toolkit\n",
                encoding="utf-8",
            )
            (repository / fleet.ANSWERS_FILE).symlink_to(target)
            with self.assertRaisesRegex(fleet.FleetUpdateError, "must not be a symlink"):
                fleet.canonicalize_answers_source(repository, "quokkify/project-toolkit")
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                "_src_path: gh:quokkify/project-toolkit\n",
            )


class TemplateUpdateTests(TestCase):
    @mock.patch.object(fleet, "changed_paths", return_value=[])
    @mock.patch.object(fleet, "canonicalize_answers_source")
    @mock.patch.object(fleet, "run")
    def test_canonicalizes_source_after_clean_copier_update(
        self,
        run_mock: mock.Mock,
        canonicalize_mock: mock.Mock,
        _: mock.Mock,
    ) -> None:
        events: list[str] = []
        run_mock.side_effect = lambda *args, **kwargs: events.append("copier-update")
        canonicalize_mock.side_effect = lambda *args, **kwargs: events.append("canonicalize")

        fleet.update_template(
            Path("/tmp/repository"),
            template_source="quokkify/project-toolkit",
            template_ref="v2.8.1",
            env={},
        )

        self.assertEqual(events, ["copier-update", "canonicalize"])


class GitStatusTests(TestCase):
    @mock.patch.object(fleet, "run")
    def test_parses_modified_untracked_and_renamed_paths(self, run_mock: mock.Mock) -> None:
        run_mock.return_value.stdout = (
            " M README.md\0?? .github/workflows/codeql.yml\0"
            "R  new-name.yml\0old-name.yml\0"
        )
        paths = fleet.changed_paths(Path("/tmp/repository"))
        self.assertEqual(
            paths,
            [".github/workflows/codeql.yml", "README.md", "new-name.yml"],
        )


class RepositoryProcessingTests(TestCase):
    @mock.patch.object(fleet, "fetch_answers", return_value=None)
    def test_skips_repository_without_answers(self, _: mock.Mock) -> None:
        result = fleet.process_repository(
            fleet.Repository("quokkify/plain", "main"),
            expected_template="quokkify/project-toolkit",
            branch=fleet.DEFAULT_BRANCH,
            dry_run=True,
            template_ref=None,
            env={},
            workspace=Path("/tmp"),
        )
        self.assertEqual(result.status, "not-managed")

    @mock.patch.object(
        fleet,
        "fetch_answers",
        return_value="_src_path: gh:someone/other-template\n",
    )
    def test_skips_foreign_template(self, _: mock.Mock) -> None:
        result = fleet.process_repository(
            fleet.Repository("quokkify/foreign", "main"),
            expected_template="quokkify/project-toolkit",
            branch=fleet.DEFAULT_BRANCH,
            dry_run=True,
            template_ref=None,
            env={},
            workspace=Path("/tmp"),
        )
        self.assertEqual(result.status, "foreign-template")

    @mock.patch.object(fleet, "update_template", return_value=["renovate.json", "validate.yml"])
    @mock.patch.object(fleet, "clone_repository")
    @mock.patch.object(
        fleet,
        "fetch_answers",
        return_value="_src_path: gh:quokkify/project-toolkit\n",
    )
    def test_dry_run_reports_changes_without_push(
        self,
        _: mock.Mock,
        clone_mock: mock.Mock,
        update_mock: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = fleet.process_repository(
                fleet.Repository("quokkify/example", "main"),
                expected_template="quokkify/project-toolkit",
                branch=fleet.DEFAULT_BRANCH,
                dry_run=True,
                template_ref="v3.0.0",
                env={},
                workspace=Path(temporary),
            )
        self.assertEqual(result.status, "would-update")
        self.assertIn("renovate.json", result.detail)
        clone_mock.assert_called_once()
        self.assertEqual(update_mock.call_args.kwargs["template_ref"], "v3.0.0")
        self.assertEqual(
            update_mock.call_args.kwargs["template_source"], "quokkify/project-toolkit"
        )

    @mock.patch.object(fleet, "ensure_pull_request", return_value="https://github.com/quokkify/example/pull/1")
    @mock.patch.object(fleet, "push_automation_branch")
    @mock.patch.object(fleet, "update_template", return_value=[".github/workflows/validate.yml"])
    @mock.patch.object(fleet, "clone_repository")
    @mock.patch.object(
        fleet,
        "fetch_answers",
        return_value="_src_path: gh:quokkify/project-toolkit\n",
    )
    def test_write_mode_pushes_branch_and_returns_pull_request(
        self,
        _: mock.Mock,
        clone_mock: mock.Mock,
        update_mock: mock.Mock,
        push_mock: mock.Mock,
        pull_request_mock: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = fleet.process_repository(
                fleet.Repository("quokkify/example", "main"),
                expected_template="gh:quokkify/project-toolkit.git",
                branch=fleet.DEFAULT_BRANCH,
                dry_run=False,
                template_ref=None,
                env={},
                workspace=Path(temporary),
            )
        self.assertEqual(result.status, "pull-request")
        self.assertEqual(result.detail, "https://github.com/quokkify/example/pull/1")
        clone_mock.assert_called_once()
        update_mock.assert_called_once()
        push_mock.assert_called_once()
        pull_request_mock.assert_called_once()

    @mock.patch.object(fleet, "ensure_pull_request")
    @mock.patch.object(fleet, "push_automation_branch")
    @mock.patch.object(fleet, "update_template", return_value=[])
    @mock.patch.object(fleet, "clone_repository")
    @mock.patch.object(
        fleet,
        "fetch_answers",
        return_value="_src_path: gh:quokkify/project-toolkit\n",
    )
    def test_up_to_date_repository_does_not_push(
        self,
        _: mock.Mock,
        clone_mock: mock.Mock,
        update_mock: mock.Mock,
        push_mock: mock.Mock,
        pull_request_mock: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = fleet.process_repository(
                fleet.Repository("quokkify/example", "main"),
                expected_template="quokkify/project-toolkit",
                branch=fleet.DEFAULT_BRANCH,
                dry_run=False,
                template_ref=None,
                env={},
                workspace=Path(temporary),
            )
        self.assertEqual(result.status, "up-to-date")
        clone_mock.assert_called_once()
        update_mock.assert_called_once()
        push_mock.assert_not_called()
        pull_request_mock.assert_not_called()


class CommandLineTests(TestCase):
    @mock.patch.object(fleet, "discover_repositories", return_value=[])
    @mock.patch.object(fleet.shutil, "which", return_value="/usr/bin/tool")
    @mock.patch.dict(
        "os.environ",
        {
            "GITHUB_TOKEN": "repository-scoped-token",
            "GH_TOKEN": "ambient-codeowner-token",
        },
        clear=False,
    )
    def test_dry_run_prefers_repository_scoped_token(
        self,
        _: mock.Mock,
        discover_mock: mock.Mock,
    ) -> None:
        self.assertEqual(fleet.main(["--dry-run"]), 0)
        self.assertEqual(discover_mock.call_args.kwargs["env"]["GH_TOKEN"], "repository-scoped-token")

    @mock.patch.object(
        fleet,
        "process_repository",
        return_value=fleet.Result("quokkify/example", "would-update", "README.md"),
    )
    @mock.patch.object(
        fleet,
        "discover_repositories",
        return_value=[fleet.Repository("quokkify/example", "main")],
    )
    @mock.patch.object(fleet.shutil, "which", return_value="/usr/bin/tool")
    @mock.patch.dict(
        "os.environ",
        {"GITHUB_TOKEN": "repository-scoped-token", "GH_TOKEN": ""},
        clear=False,
    )
    def test_dry_run_returns_distinct_status_when_drift_exists(
        self,
        _: mock.Mock,
        __: mock.Mock,
        process_mock: mock.Mock,
    ) -> None:
        self.assertEqual(fleet.main(["--dry-run"]), 3)
        process_mock.assert_called_once()

    @mock.patch.dict(
        "os.environ",
        {"GH_TOKEN": "", "GITHUB_TOKEN": ""},
        clear=False,
    )
    def test_write_mode_requires_codeowner_session_token(self) -> None:
        self.assertEqual(fleet.main(["--write", "--repo", "quokkify/example"]), 2)


if __name__ == "__main__":
    main()
