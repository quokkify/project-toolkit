from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
from unittest import TestCase, main, mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "update_copier_fleet", ROOT / "scripts/update_copier_fleet.py"
)
assert SPEC and SPEC.loader
fleet = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = fleet
SPEC.loader.exec_module(fleet)


def cloned_answers(raw_answers: str):
    def materialize(_: object, destination: Path, *, env: dict[str, str]) -> None:
        del env
        destination.mkdir(parents=True, exist_ok=True)
        (destination / fleet.ANSWERS_FILE).write_text(raw_answers, encoding="utf-8")

    return materialize


class DiscoveryTests(TestCase):
    @mock.patch.object(fleet, "gh_json", return_value=[])
    def test_public_only_discovery_is_explicit(self, gh_json_mock: mock.Mock) -> None:
        self.assertEqual(fleet.discover_repositories("quokkify", env={}, public_only=True), [])
        arguments = gh_json_mock.call_args.args[0]
        self.assertIn("--visibility", arguments)
        self.assertEqual(arguments[arguments.index("--visibility") + 1], "public")
        self.assertIn("visibility", arguments[arguments.index("--json") + 1].split(","))

    @mock.patch.object(
        fleet,
        "gh_json",
        return_value=[
            {
                "nameWithOwner": "quokkify/leaked-private",
                "defaultBranchRef": {"name": "main"},
                "isArchived": False,
                "isFork": False,
                "visibility": "PRIVATE",
            },
            {
                "nameWithOwner": "quokkify/public-example",
                "defaultBranchRef": {"name": "main"},
                "isArchived": False,
                "isFork": False,
                "visibility": "PUBLIC",
            },
        ],
    )
    def test_public_only_discovery_rechecks_visibility_client_side(self, _: mock.Mock) -> None:
        discovered = fleet.discover_repositories("quokkify", env={}, public_only=True)
        self.assertEqual([repo.name_with_owner for repo in discovered], ["quokkify/public-example"])


class ProjectOwnedToolkitRefTests(TestCase):
    """The generated contract requires every toolkit reference to match toolkit_version."""

    def write_workflows(self, root: Path) -> None:
        workflows = root / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text(
            "jobs:\n"
            "  build:\n"
            "    uses: quokkify/project-toolkit/.github/workflows/node-ci.yml@v2.14.0\n"
            "    steps:\n"
            "      - uses: quokkify/project-toolkit/actions/setup-node@v2.14.0\n",
            encoding="utf-8",
        )
        (workflows / "pinned.yml").write_text(
            "jobs:\n"
            "  build:\n"
            "    uses: quokkify/project-toolkit/actions/setup-node@"
            + "a" * 40
            + " # v2.14.0\n",
            encoding="utf-8",
        )
        (workflows / "foreign.yml").write_text(
            "jobs:\n  build:\n    uses: other/repo/.github/workflows/ci.yml@v2.14.0\n",
            encoding="utf-8",
        )

    def test_tag_references_move_to_the_new_template_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_workflows(root)
            changed = fleet.bump_project_owned_toolkit_refs(root, "v2.19.0")
            ci = (root / ".github/workflows/ci.yml").read_text()
        self.assertEqual(changed, [".github/workflows/ci.yml"])
        self.assertIn("node-ci.yml@v2.19.0", ci)
        self.assertIn("setup-node@v2.19.0", ci)
        self.assertNotIn("v2.14.0", ci)

    def test_digest_pins_and_other_repositories_are_left_alone(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_workflows(root)
            fleet.bump_project_owned_toolkit_refs(root, "v2.19.0")
            pinned = (root / ".github/workflows/pinned.yml").read_text()
            foreign = (root / ".github/workflows/foreign.yml").read_text()
        self.assertIn("a" * 40, pinned)
        self.assertIn("# v2.14.0", pinned)
        self.assertIn("other/repo/.github/workflows/ci.yml@v2.14.0", foreign)


class AuthenticatedGitTests(TestCase):
    """git does not read GH_TOKEN; a hosted runner has no credential helper at all."""

    def test_push_and_ls_remote_authenticate_through_gh(self) -> None:
        repository = fleet.Repository("quokkify/example", "main")
        with (
            mock.patch.object(fleet, "run") as run_mock,
            tempfile.TemporaryDirectory() as temporary,
        ):
            run_mock.return_value.stdout = ""
            fleet.push_automation_branch(
                repository,
                Path(temporary),
                branch="automation/copier-template-update",
                env={"GH_TOKEN": "token"},
            )
        remote_commands = [
            call.args[0]
            for call in run_mock.call_args_list
            if call.args[0][0] == "git" and any(arg in ("push", "ls-remote") for arg in call.args[0])
        ]
        self.assertEqual(len(remote_commands), 2)
        for command in remote_commands:
            self.assertIn("credential.helper=!gh auth git-credential", command)
            # The empty helper must come first so an ambient one cannot win.
            self.assertLess(
                command.index("credential.helper="),
                command.index("credential.helper=!gh auth git-credential"),
            )

    def test_local_git_operations_are_not_given_credentials(self) -> None:
        repository = fleet.Repository("quokkify/example", "main")
        with (
            mock.patch.object(fleet, "run") as run_mock,
            tempfile.TemporaryDirectory() as temporary,
        ):
            run_mock.return_value.stdout = ""
            fleet.push_automation_branch(
                repository,
                Path(temporary),
                branch="automation/copier-template-update",
                env={"GH_TOKEN": "token"},
            )
        for call in run_mock.call_args_list:
            command = call.args[0]
            if command[0] == "git" and command[1] in ("config", "add", "commit", "switch"):
                self.assertNotIn("credential.helper=!gh auth git-credential", command)


class ExplicitRepositoryVisibilityTests(TestCase):
    """--public-only is an invariant of the public fleet front, not only a discovery filter."""

    def run_main(self, metadata: dict[str, object], arguments: list[str]) -> tuple[int, str]:
        buffer = StringIO()
        with (
            mock.patch.object(fleet, "gh_json", return_value=metadata),
            mock.patch.object(
                fleet,
                "process_repository",
                return_value=fleet.Result("quokkify/example", "up-to-date"),
            ) as process_mock,
            mock.patch.object(fleet.shutil, "which", return_value="/usr/bin/tool"),
            mock.patch.object(fleet, "resolve_template_ref", return_value="v2.16.0"),
            mock.patch.dict(
                "os.environ",
                {"GITHUB_TOKEN": "repository-scoped-token"},
                clear=False,
            ),
            redirect_stdout(buffer),
        ):
            status = fleet.main(arguments)
            self.processed = process_mock.call_count
        return status, buffer.getvalue()

    def test_public_only_rejects_an_explicitly_requested_private_repository(self) -> None:
        status, output = self.run_main(
            {
                "nameWithOwner": "quokkify/private-example",
                "defaultBranchRef": {"name": "main"},
                "isArchived": False,
                "isFork": False,
                "visibility": "PRIVATE",
            },
            ["--dry-run", "--public-only", "--repo", "quokkify/private-example"],
        )
        self.assertEqual(status, 1)
        self.assertIn("--public-only rejects non-public repositories", output)
        self.assertIn("without --public-only", output)
        self.assertEqual(self.processed, 0)

    def test_public_only_rejects_an_internal_repository(self) -> None:
        status, output = self.run_main(
            {
                "nameWithOwner": "quokkify/internal-example",
                "defaultBranchRef": {"name": "main"},
                "isArchived": False,
                "isFork": False,
                "visibility": "INTERNAL",
            },
            ["--dry-run", "--public-only", "--repo", "quokkify/internal-example"],
        )
        self.assertEqual(status, 1)
        self.assertIn("--public-only rejects non-public repositories", output)
        self.assertEqual(self.processed, 0)

    def test_public_only_rejects_metadata_without_a_visibility_field(self) -> None:
        status, output = self.run_main(
            {
                "nameWithOwner": "quokkify/unknown-example",
                "defaultBranchRef": {"name": "main"},
                "isArchived": False,
                "isFork": False,
            },
            ["--dry-run", "--public-only", "--repo", "quokkify/unknown-example"],
        )
        self.assertEqual(status, 1)
        self.assertIn("--public-only rejects non-public repositories", output)
        self.assertEqual(self.processed, 0)

    def test_public_only_rejects_a_null_visibility_field(self) -> None:
        status, _ = self.run_main(
            {
                "nameWithOwner": "quokkify/null-example",
                "defaultBranchRef": {"name": "main"},
                "isArchived": False,
                "isFork": False,
                "visibility": None,
            },
            ["--dry-run", "--public-only", "--repo", "quokkify/null-example"],
        )
        self.assertEqual(status, 1)
        self.assertEqual(self.processed, 0)

    def test_public_only_rejects_a_private_repository_in_write_mode(self) -> None:
        with mock.patch.dict("os.environ", {"GH_TOKEN": "codeowner-token"}, clear=False):
            status, output = self.run_main(
                {
                    "nameWithOwner": "quokkify/private-example",
                    "defaultBranchRef": {"name": "main"},
                    "isArchived": False,
                    "isFork": False,
                    "visibility": "PRIVATE",
                },
                ["--write", "--public-only", "--repo", "quokkify/private-example"],
            )
        self.assertEqual(status, 1)
        self.assertIn("--public-only rejects non-public repositories", output)
        self.assertEqual(self.processed, 0)

    def test_public_only_rejects_a_private_archived_repository_loudly(self) -> None:
        status, _ = self.run_main(
            {
                "nameWithOwner": "quokkify/private-archived",
                "defaultBranchRef": {"name": "main"},
                "isArchived": True,
                "isFork": False,
                "visibility": "PRIVATE",
            },
            ["--dry-run", "--public-only", "--repo", "quokkify/private-archived"],
        )
        self.assertEqual(status, 1)
        self.assertEqual(self.processed, 0)

    def test_public_only_accepts_an_explicitly_requested_public_repository(self) -> None:
        status, _ = self.run_main(
            {
                "nameWithOwner": "quokkify/public-example",
                "defaultBranchRef": {"name": "main"},
                "isArchived": False,
                "isFork": False,
                "visibility": "PUBLIC",
            },
            ["--dry-run", "--public-only", "--repo", "quokkify/public-example"],
        )
        self.assertEqual(status, 0)
        self.assertEqual(self.processed, 1)

    def test_without_public_only_visibility_does_not_gate_an_explicit_repository(self) -> None:
        status, _ = self.run_main(
            {
                "nameWithOwner": "quokkify/private-example",
                "defaultBranchRef": {"name": "main"},
                "isArchived": False,
                "isFork": False,
                "visibility": "PRIVATE",
            },
            ["--dry-run", "--repo", "quokkify/private-example"],
        )
        self.assertEqual(status, 0)
        self.assertEqual(self.processed, 1)

    def test_explicit_repository_metadata_requests_visibility(self) -> None:
        with (
            mock.patch.object(
                fleet,
                "gh_json",
                return_value={
                    "nameWithOwner": "quokkify/public-example",
                    "defaultBranchRef": {"name": "main"},
                    "isArchived": False,
                    "isFork": False,
                    "visibility": "PUBLIC",
                },
            ) as gh_json_mock,
            mock.patch.object(
                fleet,
                "process_repository",
                return_value=fleet.Result("quokkify/public-example", "up-to-date"),
            ),
            mock.patch.object(fleet.shutil, "which", return_value="/usr/bin/tool"),
            mock.patch.object(fleet, "resolve_template_ref", return_value="v2.16.0"),
            mock.patch.dict(
                "os.environ",
                {"GITHUB_TOKEN": "repository-scoped-token", "GH_TOKEN": ""},
                clear=False,
            ),
            redirect_stdout(StringIO()),
        ):
            fleet.main(["--dry-run", "--public-only", "--repo", "quokkify/public-example"])
        arguments = gh_json_mock.call_args.args[0]
        self.assertIn("visibility", arguments[arguments.index("--json") + 1])


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

        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            (repository / fleet.ANSWERS_FILE).write_text(
                "_src_path: https://github.com/quokkify/project-toolkit.git\n",
                encoding="utf-8",
            )
            fleet.update_template(
                repository,
                template_source="quokkify/project-toolkit",
                template_ref="v2.8.1",
                env={},
            )

        self.assertEqual(events, ["copier-update", "canonicalize"])
        copier_command = run_mock.call_args.args[0]
        self.assertIn("--vcs-ref", copier_command)
        self.assertIn("v2.8.1", copier_command)
        self.assertIn("--data", copier_command)
        self.assertIn("toolkit_version=v2.8.1", copier_command)

    def test_restores_prettier_formatting_when_answers_are_semantically_equal(self) -> None:
        original = (
            "_commit: v2.8.2\n"
            "_src_path: https://github.com/quokkify/project-toolkit.git\n"
            "renovate_presets:\n"
            "  - default\n"
            "  - github-actions\n"
        )
        copier_serialized = original.replace("  - ", "- ")
        with tempfile.TemporaryDirectory() as temporary:
            answers = Path(temporary) / fleet.ANSWERS_FILE
            answers.write_text(copier_serialized, encoding="utf-8")

            fleet.restore_answers_format_if_semantically_equal(answers, original)

            self.assertEqual(answers.read_text(encoding="utf-8"), original)

    def test_keeps_copier_answers_when_semantics_changed(self) -> None:
        original = "_commit: v2.8.1\nrenovate_presets:\n  - default\n"
        updated = "_commit: v2.8.2\nrenovate_presets:\n- default\n- github-actions\n"
        with tempfile.TemporaryDirectory() as temporary:
            answers = Path(temporary) / fleet.ANSWERS_FILE
            answers.write_text(updated, encoding="utf-8")

            fleet.restore_answers_format_if_semantically_equal(answers, original)

            self.assertEqual(
                answers.read_text(encoding="utf-8"),
                "_commit: v2.8.2\nrenovate_presets:\n  - default\n  - github-actions\n",
            )

    @mock.patch.object(fleet, "gh_json", return_value={"tagName": "v2.10.1"})
    def test_resolves_latest_release_when_template_ref_is_omitted(
        self,
        gh_json_mock: mock.Mock,
    ) -> None:
        resolved = fleet.resolve_template_ref("quokkify/project-toolkit", None, env={})

        self.assertEqual(resolved, "v2.10.1")
        gh_json_mock.assert_called_once_with(
            [
                "release",
                "view",
                "--repo",
                "quokkify/project-toolkit",
                "--json",
                "tagName",
            ],
            env={},
        )

    @mock.patch.object(fleet, "gh_json", return_value={"tagName": "v02.10.1"})
    def test_rejects_latest_release_with_leading_zero(
        self,
        _: mock.Mock,
    ) -> None:
        with self.assertRaisesRegex(fleet.FleetUpdateError, "exact vMAJOR.MINOR.PATCH"):
            fleet.resolve_template_ref("quokkify/project-toolkit", None, env={})

    def test_keeps_explicit_non_release_template_ref_for_preview(self) -> None:
        self.assertEqual(
            fleet.resolve_template_ref("quokkify/project-toolkit", "feature/allure", env={}),
            "feature/allure",
        )

    @mock.patch.object(fleet, "gh_json", return_value={"sha": "a" * 40})
    def test_resolves_release_tag_to_its_commit(self, gh_json_mock: mock.Mock) -> None:
        resolved = fleet.resolve_template_commit(
            "quokkify/project-toolkit", "v2.19.2", env={}
        )

        self.assertEqual(resolved, "a" * 40)
        gh_json_mock.assert_called_once_with(
            [
                "api",
                "repos/quokkify/project-toolkit/commits/v2.19.2",
                "--jq",
                "{sha: .sha}",
            ],
            env={},
        )

    @mock.patch.object(fleet, "gh_json", return_value={"sha": "not-a-commit"})
    def test_rejects_a_tag_that_does_not_resolve_to_a_commit(self, _: mock.Mock) -> None:
        with self.assertRaisesRegex(fleet.FleetUpdateError, "did not resolve to a commit"):
            fleet.resolve_template_commit("quokkify/project-toolkit", "v2.19.2", env={})


class ProjectOwnedToolkitRefTests(TestCase):
    """The consumer contract accepts a tag, or a digest whose comment names that tag."""

    NEW_COMMIT = "b" * 40
    OLD_COMMIT = "fd12c1b07b08c7f873942abd5e8fedbfa26b4583"

    def workflows(self, root: Path) -> Path:
        directory = root / ".github" / "workflows"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def test_rewrites_a_digest_pin_with_its_release_comment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            workflow = self.workflows(repository) / "publish-maven-central.yml"
            workflow.write_text(
                "        uses: quokkify/project-toolkit/actions/setup-java-gradle@"
                f"{self.OLD_COMMIT} # v2.19.1\n",
                encoding="utf-8",
            )

            changed = fleet.bump_project_owned_toolkit_refs(
                repository, "v2.19.2", resolve_commit=lambda: self.NEW_COMMIT
            )

            self.assertEqual(changed, [".github/workflows/publish-maven-central.yml"])
            self.assertEqual(
                workflow.read_text(encoding="utf-8"),
                "        uses: quokkify/project-toolkit/actions/setup-java-gradle@"
                f"{self.NEW_COMMIT} # v2.19.2\n",
            )

    def test_rewrites_a_digest_pin_that_renovate_moved_ahead_of_the_answers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            workflow = self.workflows(repository) / "ci.yml"
            workflow.write_text(
                "      uses: quokkify/project-toolkit/.github/workflows/java-ci.yml@"
                f"{self.OLD_COMMIT} # v2.20.0\n",
                encoding="utf-8",
            )

            fleet.bump_project_owned_toolkit_refs(
                repository, "v2.19.2", resolve_commit=lambda: self.NEW_COMMIT
            )

            self.assertEqual(
                workflow.read_text(encoding="utf-8"),
                "      uses: quokkify/project-toolkit/.github/workflows/java-ci.yml@"
                f"{self.NEW_COMMIT} # v2.19.2\n",
            )

    def test_still_rewrites_plain_tag_references(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            workflow = self.workflows(repository) / "ci.yaml"
            workflow.write_text(
                "      uses: quokkify/project-toolkit/.github/workflows/node-ci.yml@v2.19.1\n",
                encoding="utf-8",
            )

            changed = fleet.bump_project_owned_toolkit_refs(
                repository, "v2.19.2", resolve_commit=lambda: self.NEW_COMMIT
            )

            self.assertEqual(changed, [".github/workflows/ci.yaml"])
            self.assertEqual(
                workflow.read_text(encoding="utf-8"),
                "      uses: quokkify/project-toolkit/.github/workflows/node-ci.yml@v2.19.2\n",
            )

    def test_leaves_a_digest_pin_without_a_release_comment_alone(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            workflow = self.workflows(repository) / "ci.yml"
            original = (
                "      uses: quokkify/project-toolkit/actions/setup-node@"
                f"{self.OLD_COMMIT}\n"
            )
            workflow.write_text(original, encoding="utf-8")

            changed = fleet.bump_project_owned_toolkit_refs(
                repository, "v2.19.2", resolve_commit=lambda: self.NEW_COMMIT
            )

            self.assertEqual(changed, [])
            self.assertEqual(workflow.read_text(encoding="utf-8"), original)

    def test_leaves_a_foreign_action_alone(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            workflow = self.workflows(repository) / "ci.yml"
            original = (
                "      uses: actions/checkout@"
                f"{self.OLD_COMMIT} # v2.19.1\n"
            )
            workflow.write_text(original, encoding="utf-8")

            changed = fleet.bump_project_owned_toolkit_refs(
                repository, "v2.19.2", resolve_commit=lambda: self.NEW_COMMIT
            )

            self.assertEqual(changed, [])
            self.assertEqual(workflow.read_text(encoding="utf-8"), original)

    def test_is_idempotent_when_every_reference_already_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            workflow = self.workflows(repository) / "ci.yml"
            original = (
                "      uses: quokkify/project-toolkit/actions/setup-java-gradle@"
                f"{self.NEW_COMMIT} # v2.19.2\n"
            )
            workflow.write_text(original, encoding="utf-8")

            changed = fleet.bump_project_owned_toolkit_refs(
                repository, "v2.19.2", resolve_commit=lambda: self.NEW_COMMIT
            )

            self.assertEqual(changed, [])
            self.assertEqual(workflow.read_text(encoding="utf-8"), original)

    def test_keeps_digest_pins_untouched_without_a_resolved_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            workflow = self.workflows(repository) / "ci.yml"
            original = (
                "      uses: quokkify/project-toolkit/actions/setup-python@"
                f"{self.OLD_COMMIT} # v2.19.1\n"
            )
            workflow.write_text(original, encoding="utf-8")

            changed = fleet.bump_project_owned_toolkit_refs(repository, "v2.19.2")

            self.assertEqual(changed, [])
            self.assertEqual(workflow.read_text(encoding="utf-8"), original)


class TemplateInventoryTests(TestCase):
    def write_baseline(self, repository: Path) -> None:
        for relative_path in fleet.BASELINE_PATHS:
            path = repository / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("generated\n", encoding="utf-8")

    def test_reports_configured_features_and_materialized_outputs(self) -> None:
        raw_answers = (
            "_commit: v2.8.2\n"
            "components:\n"
            "  - type: python\n"
            "    path: backend\n"
            "  - type: node\n"
            "    path: frontend\n"
            "docker: true\n"
            "release_please: true\n"
            "renovate: false\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            self.write_baseline(repository)
            release = repository / fleet.FEATURE_PATHS["release_please"]
            release.parent.mkdir(parents=True, exist_ok=True)
            release.write_text("generated\n", encoding="utf-8")
            renovate = repository / fleet.FEATURE_PATHS["renovate"]
            renovate.parent.mkdir(parents=True, exist_ok=True)
            renovate.write_text("custom\n", encoding="utf-8")

            inventory = fleet.inventory_from_answers(raw_answers, repository)

        self.assertEqual(inventory.commit, "v2.8.2")
        self.assertIsNone(inventory.target_commit)
        self.assertEqual(inventory.components, ("python:backend", "node:frontend"))
        self.assertEqual(inventory.baseline, "2/2")
        self.assertEqual(inventory.missing_baseline, ())
        self.assertEqual(inventory.docker, "enabled")
        self.assertEqual(inventory.codeql, "unknown")
        self.assertEqual(inventory.allure_report, "unknown")
        self.assertEqual(inventory.release_please, "enabled")
        self.assertEqual(inventory.renovate, "custom")
        self.assertFalse(fleet.inventory_has_mismatch(inventory))

    def test_codeql_is_an_optional_output_rather_than_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            self.write_baseline(repository)

            disabled = fleet.inventory_from_answers(
                "components: []\ncodeql: false\n", repository
            )

            codeql = repository / fleet.FEATURE_PATHS["codeql"]
            codeql.parent.mkdir(parents=True, exist_ok=True)
            codeql.write_text("name: CodeQL\n", encoding="utf-8")
            enabled = fleet.inventory_from_answers(
                "components: []\ncodeql: true\n", repository
            )
            kept_after_opting_out = fleet.inventory_from_answers(
                "components: []\ncodeql: false\n", repository
            )

            codeql.unlink()
            missing = fleet.inventory_from_answers(
                "components: []\ncodeql: true\n", repository
            )

        self.assertEqual(disabled.codeql, "disabled")
        self.assertEqual(disabled.baseline, "2/2")
        self.assertNotIn(fleet.FEATURE_PATHS["codeql"], disabled.missing_baseline)
        self.assertFalse(fleet.inventory_has_mismatch(disabled))

        self.assertEqual(enabled.codeql, "enabled")
        self.assertFalse(fleet.inventory_has_mismatch(enabled))

        self.assertEqual(kept_after_opting_out.codeql, "custom")

        self.assertEqual(missing.codeql, "missing")
        self.assertTrue(fleet.inventory_has_mismatch(missing))

    def test_distinguishes_missing_disabled_and_unknown_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            inventory = fleet.inventory_from_answers(
                "components: []\nrelease_please: true\nrenovate: false\n",
                repository,
            )

        self.assertEqual(inventory.commit, "unknown")
        self.assertEqual(inventory.components, ("none",))
        self.assertEqual(inventory.docker, "unknown")
        self.assertEqual(inventory.allure_report, "unknown")
        self.assertEqual(inventory.release_please, "missing")
        self.assertEqual(inventory.renovate, "disabled")
        self.assertTrue(fleet.inventory_has_mismatch(inventory))

    def test_allure_requires_generated_workflow_and_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            workflow = repository / fleet.FEATURE_PATHS["allure_report"]
            config = repository / fleet.ALLURE_CONFIG_PATH
            workflow.parent.mkdir(parents=True)
            workflow.write_text("name: Allure report\n", encoding="utf-8")

            incomplete = fleet.inventory_from_answers(
                "components: []\nallure_report: true\n",
                repository,
            )
            custom = fleet.inventory_from_answers(
                "components: []\nallure_report: false\n",
                repository,
            )
            config.parent.mkdir(parents=True)
            config.write_text("export default {};\n", encoding="utf-8")
            still_incomplete = fleet.inventory_from_answers(
                "components: []\nallure_report: true\n",
                repository,
            )
            extractor = repository / fleet.ALLURE_EXTRACTOR_PATH
            extractor.write_text("# trusted extractor\n", encoding="utf-8")
            enabled = fleet.inventory_from_answers(
                "components: []\nallure_report: true\n",
                repository,
            )

        self.assertEqual(incomplete.allure_report, "missing")
        self.assertTrue(fleet.inventory_has_mismatch(incomplete))
        self.assertEqual(custom.allure_report, "custom")
        self.assertEqual(still_incomplete.allure_report, "missing")
        self.assertEqual(enabled.allure_report, "enabled")

    def test_allure_accepts_complete_custom_helper_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            workflow = repository / fleet.FEATURE_PATHS["allure_report"]
            config = repository / "tools/allure/allurerc.mjs"
            extractor = repository / "tools/allure/safe_extract.py"
            workflow.parent.mkdir(parents=True)
            config.parent.mkdir(parents=True)
            workflow.write_text(
                "name: Allure report\n\n"
                "steps:\n"
                "  - run: python tools/allure/safe_extract.py\n"
                "    with:\n"
                "      config-file: tools/allure/allurerc.mjs\n",
                encoding="utf-8",
            )
            config.write_text("export default {};\n", encoding="utf-8")
            extractor.write_text("# trusted extractor\n", encoding="utf-8")
            for path in fleet.BASELINE_PATHS:
                baseline = repository / path
                baseline.parent.mkdir(parents=True, exist_ok=True)
                baseline.write_text("name: baseline\n", encoding="utf-8")

            inventory = fleet.inventory_from_answers(
                "components: []\nallure_report: true\n",
                repository,
            )

        self.assertEqual(inventory.allure_report, "custom")
        self.assertFalse(fleet.inventory_has_mismatch(inventory))

    def test_symlinked_template_outputs_are_reported_as_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            target = repository / "custom.yml"
            target.write_text("custom\n", encoding="utf-8")
            baseline = repository / fleet.BASELINE_PATHS[0]
            baseline.parent.mkdir(parents=True, exist_ok=True)
            baseline.symlink_to(target)
            release = repository / fleet.FEATURE_PATHS["release_please"]
            release.parent.mkdir(parents=True, exist_ok=True)
            release.symlink_to(target)

            inventory = fleet.inventory_from_answers(
                "components: []\nrelease_please: true\nrenovate: false\n",
                repository,
            )

        self.assertEqual(inventory.release_please, "missing")
        self.assertIn(".github/workflows/validate.yml", inventory.missing_baseline)

    def test_symlinked_parent_directory_does_not_materialize_outputs(self) -> None:
        raw_answers = (
            "_commit: v2.8.2\n"
            "_src_path: gh:quokkify/project-toolkit\n"
            "release_please: true\n"
            "renovate: true\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repository"
            outside = Path(temporary) / "outside"
            (outside / "workflows").mkdir(parents=True)
            (outside / "workflows" / "validate.yml").write_text("name: Validate\n")
            (outside / "workflows" / "gitleaks.yml").write_text("name: Gitleaks\n")
            (outside / "workflows" / "codeql.yml").write_text("name: CodeQL\n")
            (outside / "workflows" / "release.yml").write_text("name: Release\n")
            (outside / "renovate.json").write_text("{}\n")
            repository.mkdir()
            (repository / ".github").symlink_to(outside, target_is_directory=True)

            inventory = fleet.inventory_from_answers(raw_answers, repository)

        self.assertEqual(inventory.baseline, "0/2")
        self.assertEqual(inventory.release_please, "missing")
        self.assertEqual(inventory.renovate, "missing")
        self.assertEqual(set(inventory.missing_baseline), set(fleet.BASELINE_PATHS))

    def test_console_markdown_and_json_reports_share_the_inventory(self) -> None:
        inventory = fleet.TemplateInventory(
            commit="v2.8.2",
            target_commit="v2.9.0",
            components=("python:.",),
            baseline="2/2",
            missing_baseline=(),
            docker="disabled",
            codeql="enabled",
            allure_report="enabled",
            release_please="enabled",
            renovate="missing",
        )
        result = fleet.Result(
            "quokkify/example",
            "would-update",
            ".github/renovate.json",
            inventory,
        )
        counts = {"would-update": 1}

        console = "\n".join(fleet.console_lines(result))
        markdown = fleet.markdown_report([result], counts)
        report = fleet.json.loads(fleet.json_report([result], counts))

        self.assertIn("template=v2.8.2->v2.9.0 components=python:.", console)
        self.assertIn("renovate=missing", console)
        self.assertIn("| quokkify/example | 🟡 Drift | v2.8.2 → v2.9.0 | python:.", markdown)
        self.assertIn("Missing enabled template output: `.github/renovate.json`", markdown)
        self.assertEqual(report["schema_version"], 3)
        self.assertEqual(report["configuration_mismatches"], 1)
        self.assertEqual(report["repositories"][0]["template"]["renovate"], "missing")
        self.assertEqual(report["repositories"][0]["template"]["allure_report"], "enabled")
        self.assertEqual(report["repositories"][0]["template"]["target_commit"], "v2.9.0")

    def test_report_renderers_escape_control_characters_and_backslash_pipes(self) -> None:
        inventory = fleet.TemplateInventory(
            commit="v2.8.2\r",
            target_commit=None,
            components=("python:C:\\repo\\|row\r\x1b\u0085\u009b",),
            baseline="2/2",
            missing_baseline=(),
            docker="disabled",
            codeql="disabled",
            allure_report="disabled",
            release_please="disabled",
            renovate="enabled",
        )
        result = fleet.Result("quokkify/example", "up-to-date", inventory=inventory)

        console = "\n".join(fleet.console_lines(result))
        markdown = fleet.markdown_report([result], {"up-to-date": 1})

        for rendered in (console, markdown):
            self.assertNotIn("\r", rendered)
            self.assertNotIn("\x1b", rendered)
            self.assertIn("\\x0d", rendered)
            self.assertIn("\\x1b", rendered)
            self.assertNotIn("\u0085", rendered)
            self.assertNotIn("\u009b", rendered)
            self.assertIn("\\x85", rendered)
            self.assertIn("\\x9b", rendered)
        self.assertEqual(len([line for line in markdown.splitlines() if line.startswith("|")]), 3)


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

    @mock.patch.object(fleet, "update_template")
    @mock.patch.object(
        fleet,
        "clone_repository",
        side_effect=cloned_answers("_src_path: gh:someone/other-template\n"),
    )
    @mock.patch.object(
        fleet,
        "fetch_answers",
        return_value="_src_path: gh:quokkify/project-toolkit\n",
    )
    def test_revalidates_template_source_from_cloned_revision(
        self,
        _: mock.Mock,
        __: mock.Mock,
        update_mock: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(fleet.FleetUpdateError, "changed to a different template"):
                fleet.process_repository(
                    fleet.Repository("quokkify/example", "main"),
                    expected_template="quokkify/project-toolkit",
                    branch=fleet.DEFAULT_BRANCH,
                    dry_run=True,
                    template_ref=None,
                    env={},
                    workspace=Path(temporary),
                )
        update_mock.assert_not_called()

    @mock.patch.object(fleet, "update_template", side_effect=fleet.FleetUpdateError("conflict"))
    @mock.patch.object(
        fleet,
        "clone_repository",
        side_effect=cloned_answers(
            "_commit: v2.8.2\n"
            "_src_path: gh:quokkify/project-toolkit\n"
            "components: []\n"
        ),
    )
    @mock.patch.object(
        fleet,
        "fetch_answers",
        return_value="_src_path: gh:quokkify/project-toolkit\n",
    )
    def test_preserves_inventory_when_copier_update_fails(
        self,
        _: mock.Mock,
        __: mock.Mock,
        ___: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(fleet.RepositoryProcessError, "conflict") as raised:
                fleet.process_repository(
                    fleet.Repository("quokkify/example", "main"),
                    expected_template="quokkify/project-toolkit",
                    branch=fleet.DEFAULT_BRANCH,
                    dry_run=True,
                    template_ref=None,
                    env={},
                    workspace=Path(temporary),
                )
        self.assertEqual(raised.exception.inventory.commit, "v2.8.2")
        self.assertEqual(raised.exception.inventory.components, ("none",))

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
        clone_mock.side_effect = cloned_answers(
            "_commit: v2.8.2\n_src_path: gh:quokkify/project-toolkit\n"
        )
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
        clone_mock.side_effect = cloned_answers(
            "_commit: v2.8.2\n_src_path: gh:quokkify/project-toolkit\n"
        )
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
        clone_mock.side_effect = cloned_answers(
            "_commit: v2.8.2\n_src_path: gh:quokkify/project-toolkit\n"
        )
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

    @mock.patch.object(fleet, "discover_repositories", return_value=[])
    @mock.patch.object(fleet.shutil, "which", return_value="/usr/bin/tool")
    @mock.patch.dict(
        "os.environ",
        {
            "GITHUB_TOKEN": "repository-scoped-token",
            "GH_TOKEN": "ambient-codeowner-token",
            "PATH": "/opt/toolchain/bin",
        },
        clear=False,
    )
    def test_command_lookup_uses_process_path_only(
        self,
        which_mock: mock.Mock,
        _: mock.Mock,
    ) -> None:
        self.assertEqual(fleet.main(["--dry-run"]), 0)
        self.assertEqual(
            [call.args[0] for call in which_mock.call_args_list],
            ["copier", "gh", "git"],
        )
        self.assertTrue(
            all(call.kwargs.get("path") == "/opt/toolchain/bin" for call in which_mock.call_args_list)
        )

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
        self.assertEqual(fleet.main(["--dry-run", "--template-ref", "v2.10.1"]), 3)
        process_mock.assert_called_once()

    @mock.patch.object(fleet, "process_repository")
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
    def test_failed_repository_keeps_inventory_in_json_report(
        self,
        _: mock.Mock,
        __: mock.Mock,
        process_mock: mock.Mock,
    ) -> None:
        inventory = fleet.TemplateInventory(
            commit="v2.8.2",
            target_commit=None,
            components=("none",),
            baseline="2/2",
            missing_baseline=(),
            docker="disabled",
            codeql="disabled",
            allure_report="disabled",
            release_please="disabled",
            renovate="enabled",
        )
        process_mock.side_effect = fleet.RepositoryProcessError("conflict", inventory)
        with tempfile.TemporaryDirectory() as temporary:
            report_path = Path(temporary) / "audit.json"
            status = fleet.main(
                [
                    "--dry-run",
                    "--template-ref",
                    "v2.10.1",
                    "--json-report",
                    str(report_path),
                ]
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(status, 1)
        self.assertEqual(report["repositories"][0]["status"], "failed")
        self.assertEqual(report["repositories"][0]["template"]["commit"], "v2.8.2")

    @mock.patch.dict(
        "os.environ",
        {"GH_TOKEN": "", "GITHUB_TOKEN": ""},
        clear=False,
    )
    def test_write_mode_requires_codeowner_session_token(self) -> None:
        self.assertEqual(fleet.main(["--write", "--repo", "quokkify/example"]), 2)


if __name__ == "__main__":
    main()
