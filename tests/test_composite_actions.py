from __future__ import annotations

import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def action(name: str) -> dict:
    return yaml.safe_load((ROOT / f"actions/{name}/action.yml").read_text())


class SetupActionTests(unittest.TestCase):
    def test_boolean_validation_is_first_and_fails_closed(self) -> None:
        cases = {
            "setup-python": {"CACHE_DEPENDENCIES": "maybe", "INSTALL_DEPENDENCIES": "true", "PACKAGE_MANAGER": "auto", "POETRY_VERSION": "2.1.4", "UV_VERSION": "0.8.15"},
            "setup-node": {"CACHE_DEPENDENCIES": "true", "INSTALL_DEPENDENCIES": "TRUE", "PACKAGE_MANAGER": "auto"},
            "setup-java-gradle": {"CACHE_DEPENDENCIES": "true", "VALIDATE_WRAPPERS": "yes"},
        }
        for name, values in cases.items():
            with self.subTest(name=name):
                first = action(name)["runs"]["steps"][0]
                self.assertIn("Validate", first["name"])
                self.assertNotIn("uses", first)
                if name == "setup-java-gradle":
                    self.assertEqual(first["env"]["VALIDATE_WRAPPERS"], "${{ inputs.validate-wrappers }}")
                result = subprocess.run(
                    ["bash", "-c", first["run"]],
                    env={**os.environ, **values},
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 2, result.stderr)

    def test_gradle_wrapper_validation_defaults_on_and_can_be_disabled(self) -> None:
        steps = action("setup-java-gradle")["runs"]["steps"]
        validation = next(step for step in steps if step.get("name") == "Validate Gradle wrappers")
        self.assertRegex(validation["uses"], r"\Agradle/actions/wrapper-validation@[0-9a-f]{40}\Z")
        self.assertEqual(validation["if"], "${{ inputs.validate-wrappers == 'true' }}")
        self.assertIn("'true'", validation["if"])
        self.assertNotIn("'false'", validation["if"])
        inputs = action("setup-java-gradle")["inputs"]
        self.assertEqual(inputs["validate-wrappers"]["default"], "true")
        self.assertLess(steps.index(validation), next(i for i, step in enumerate(steps) if step.get("name") == "Set up Java"))

    def test_python_auto_detects_single_nondefault_requirements_file(self) -> None:
        install = action("setup-python")["runs"]["steps"][-1]
        with tempfile.TemporaryDirectory(prefix="python-action-test-") as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            (root / "requirements-dev.txt").write_text("pytest==8.3.5\n")
            log = root / "commands.log"
            python = bin_dir / "python"
            python.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$COMMAND_LOG\"\n")
            python.chmod(python.stat().st_mode | stat.S_IXUSR)
            env = {
                **os.environ,
                "COMMAND_LOG": str(log),
                "INSTALL_COMMAND": "",
                "PACKAGE_MANAGER": "pip",
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "POETRY_VERSION": "2.1.4",
                "REQUIREMENTS_FILE": "",
                "UV_VERSION": "0.8.15",
                "WORKING_DIRECTORY": str(root),
            }
            result = subprocess.run(["bash", "-c", install["run"]], env=env, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("-m pip install -r requirements-dev.txt", log.read_text())

    def test_yarn_classic_uses_frozen_lockfile(self) -> None:
        install = action("setup-node")["runs"]["steps"][-1]
        with tempfile.TemporaryDirectory(prefix="node-action-test-") as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            (root / "package.json").write_text("{}\n")
            (root / "yarn.lock").write_text("# yarn lockfile v1\n")
            log = root / "commands.log"
            for name in ("corepack", "yarn"):
                command = bin_dir / name
                command.write_text("#!/usr/bin/env bash\nprintf '%s %s\\n' \"$(basename \"$0\")\" \"$*\" >> \"$COMMAND_LOG\"\n")
                command.chmod(command.stat().st_mode | stat.S_IXUSR)
            env = {
                **os.environ,
                "COMMAND_LOG": str(log),
                "INSTALL_COMMAND": "",
                "PACKAGE_MANAGER": "yarn",
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "WORKING_DIRECTORY": str(root),
            }
            result = subprocess.run(["bash", "-c", install["run"]], env=env, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = log.read_text()
            self.assertIn("corepack prepare yarn@1.22.22 --activate", calls)
            self.assertIn("yarn install --frozen-lockfile", calls)

    def test_nested_gradle_wrapper_output_is_workspace_relative(self) -> None:
        resolve = action("setup-java-gradle")["runs"]["steps"][-1]
        with tempfile.TemporaryDirectory(prefix="gradle-action-test-") as tmp:
            root = Path(tmp)
            (root / "backend").mkdir()
            (root / "backend/gradlew").write_text("#!/bin/sh\n")
            output = root / "output"
            result = subprocess.run(
                ["bash", "-c", resolve["run"]],
                cwd=root,
                env={**os.environ, "GITHUB_OUTPUT": str(output), "WORKING_DIRECTORY": "backend"},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_text(), "gradle-command=backend/gradlew\n")


class JUnitStepSummaryTests(unittest.TestCase):
    script = ROOT / "actions/junit-step-summary/junit_step_summary.py"

    def run_summary(
        self,
        workspace: Path,
        *,
        patterns: str = "results/**/*.xml",
        fail_on_missing: str = "false",
        working_directory: str = ".",
        max_files: str = "200",
        max_file_bytes: str = "10485760",
        max_total_bytes: str = "52428800",
        max_scan_entries: str = "100000",
        max_depth: str = "64",
        legacy_cwd: str = "",
        legacy_variant: str = "",
    ) -> tuple[subprocess.CompletedProcess[str], str, str]:
        summary = workspace / "github-summary.md"
        output = workspace / "github-output.txt"
        env = {
            **os.environ,
            "FAIL_ON_MISSING": fail_on_missing,
            "GITHUB_OUTPUT": str(output),
            "GITHUB_STEP_SUMMARY": str(summary),
            "GITHUB_WORKSPACE": str(workspace),
            "JUNIT_PATHS": patterns,
            "LEGACY_CWD": legacy_cwd,
            "LEGACY_VARIANT": legacy_variant,
            "MAX_FILE_BYTES": max_file_bytes,
            "MAX_FILES": max_files,
            "MAX_DEPTH": max_depth,
            "MAX_SCAN_ENTRIES": max_scan_entries,
            "MAX_TOTAL_BYTES": max_total_bytes,
            "TITLE": "Portable test summary",
            "WORKING_DIRECTORY": working_directory,
        }
        result = subprocess.run(
            [sys.executable, str(self.script)],
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        return (
            result,
            summary.read_text() if summary.exists() else "",
            output.read_text() if output.exists() else "",
        )

    def test_aggregates_testcases_and_summary_only_documents(self) -> None:
        with tempfile.TemporaryDirectory(prefix="junit-summary-test-") as tmp:
            workspace = Path(tmp)
            results = workspace / "results"
            results.mkdir()
            (results / "cases.xml").write_text(
                """<testsuite name="cases">
                <testcase name="pass" time="1" />
                <testcase name="failure" time="2"><failure /></testcase>
                <testcase name="error" time="3"><error /></testcase>
                <testcase name="skip" time="4"><skipped /></testcase>
                </testsuite>"""
            )
            (results / "summary.xml").write_text(
                '<testsuites tests="2" failures="0" errors="0" skipped="1" time="0.5" />'
            )
            result, summary, output = self.run_summary(workspace)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("### Portable test summary (failures)", summary)
            self.assertIn("| 2 | 6 | 2 | 1 | 1 | 2 | 10.5s |", summary)
            self.assertIn("files=2\n", output)
            self.assertIn("tests=6\n", output)
            self.assertIn("passed=2\n", output)
            self.assertIn("failures=1\n", output)
            self.assertIn("errors=1\n", output)
            self.assertIn("skipped=2\n", output)
            self.assertIn("duration=10.5\n", output)
            self.assertIn("has-failures=true\n", output)

            result, _, output = self.run_summary(workspace, patterns="./results/**/*.xml")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("files=2\n", output)

    def test_aggregates_namespaced_nested_suites_without_testcases(self) -> None:
        with tempfile.TemporaryDirectory(prefix="junit-summary-nested-") as tmp:
            workspace = Path(tmp)
            results = workspace / "results"
            results.mkdir()
            (results / "nested.xml").write_text(
                """<testsuites xmlns="urn:junit">
                <testsuite name="outer">
                  <testsuite name="one" tests="2" failures="1" errors="0" skipped="0" time="1.25" />
                  <testsuite name="two" tests="3" failures="0" errors="1" disabled="1" time="2.75" />
                </testsuite>
                </testsuites>"""
            )
            result, summary, output = self.run_summary(workspace)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("| 1 | 5 | 2 | 1 | 1 | 1 | 4s |", summary)
            self.assertIn("has-failures=true\n", output)

    def test_missing_files_are_optional_or_fail_closed_by_input(self) -> None:
        with tempfile.TemporaryDirectory(prefix="junit-summary-missing-") as tmp:
            workspace = Path(tmp)
            result, summary, output = self.run_summary(workspace)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("| 0 | 0 | 0 | 0 | 0 | 0 | 0s |", summary)
            self.assertIn("files=0\n", output)
            result, summary, output = self.run_summary(workspace, fail_on_missing="true")
            self.assertEqual(result.returncode, 2)
            self.assertIn("no regular JUnit XML files matched", result.stderr)

    def test_rejects_traversal_entities_oversize_and_file_count_overflow(self) -> None:
        with tempfile.TemporaryDirectory(prefix="junit-summary-guards-") as tmp:
            workspace = Path(tmp)
            results = workspace / "results"
            results.mkdir()
            (results / "entity.xml").write_text(
                '<!DOCTYPE testsuite [<!ENTITY x "expanded">]><testsuite tests="0" />'
            )
            result, _, _ = self.run_summary(workspace, patterns="../outside.xml")
            self.assertEqual(result.returncode, 2)
            self.assertIn("without traversal", result.stderr)
            result, _, _ = self.run_summary(workspace)
            self.assertEqual(result.returncode, 2)
            self.assertIn("DTD and entity declarations", result.stderr)
            (results / "entity.xml").write_bytes(
                (
                    '<?xml version="1.0" encoding="UTF-16"?>'
                    '<!DOCTYPE testsuite [<!ENTITY x "expanded">]>'
                    '<testsuite tests="0" />'
                ).encode("utf-16")
            )
            result, _, _ = self.run_summary(workspace)
            self.assertEqual(result.returncode, 2)
            self.assertIn("DTD and entity declarations", result.stderr)
            (results / "entity.xml").write_text('<testsuite tests="0" />')
            result, _, _ = self.run_summary(workspace, max_file_bytes="10")
            self.assertEqual(result.returncode, 2)
            self.assertIn("exceeds max-file-bytes", result.stderr)
            (results / "second.xml").write_text('<testsuite tests="0" />')
            result, _, _ = self.run_summary(workspace, max_files="1")
            self.assertEqual(result.returncode, 2)
            self.assertIn("more than max-files=1", result.stderr)

    def test_rejects_extreme_duration_exponents_and_prefers_suite_totals(self) -> None:
        with tempfile.TemporaryDirectory(prefix="junit-summary-duration-") as tmp:
            workspace = Path(tmp)
            results = workspace / "results"
            results.mkdir()
            report = results / "junit.xml"
            report.write_text('<testsuite tests="1" failures="0" time="1e100000000" />')
            result, _, _ = self.run_summary(workspace)
            self.assertEqual(result.returncode, 2)
            self.assertIn("at most", result.stderr)

            report.write_text(
                """<testsuite tests="5" failures="1" errors="0" skipped="1" time="7">
                <testcase name="only-physical-case" time="999" />
                </testsuite>"""
            )
            result, summary, output = self.run_summary(workspace)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("| 1 | 5 | 3 | 1 | 0 | 1 | 7s |", summary)
            self.assertIn("duration=7\n", output)

    def test_bounds_scan_total_bytes_and_ignores_symlinks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="junit-summary-scan-") as tmp:
            workspace = Path(tmp)
            results = workspace / "results"
            results.mkdir()
            (results / "one.xml").write_text('<testsuite tests="0" />')
            (results / "two.xml").write_text('<testsuite tests="0" />')
            (results / "loop").symlink_to(".", target_is_directory=True)

            result, _, _ = self.run_summary(workspace, max_scan_entries="2")
            self.assertEqual(result.returncode, 2)
            self.assertIn("max-scan-entries=2", result.stderr)
            result, _, _ = self.run_summary(workspace, max_total_bytes="30")
            self.assertEqual(result.returncode, 2)
            self.assertIn("max-total-bytes=30", result.stderr)

        with tempfile.TemporaryDirectory(prefix="junit-summary-symlink-") as tmp:
            workspace = Path(tmp)
            results = workspace / "results"
            results.mkdir()
            outside = workspace / "outside.xml"
            outside.write_text('<testsuite tests="1" />')
            (results / "linked.xml").symlink_to(outside)
            result, _, _ = self.run_summary(workspace, fail_on_missing="true")
            self.assertEqual(result.returncode, 2)
            self.assertIn("no regular JUnit XML files matched", result.stderr)

    def test_prunes_irrelevant_trees_and_bounds_directory_depth(self) -> None:
        with tempfile.TemporaryDirectory(prefix="junit-summary-prefix-") as tmp:
            workspace = Path(tmp)
            results = workspace / "test-results"
            results.mkdir()
            (results / "junit.xml").write_text('<testsuite tests="1" />')
            irrelevant = workspace / "node_modules"
            irrelevant.mkdir()
            current = irrelevant
            for index in range(80):
                current = current / f"package-{index}"
                current.mkdir()
                (current / "metadata.json").write_text("{}")

            result, summary, output = self.run_summary(
                workspace,
                patterns="test-results/**/*.xml",
                max_scan_entries="2",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("| 1 | 1 | 1 | 0 | 0 | 0 | 0s |", summary)
            self.assertIn("files=1\n", output)

            nonmatching = results / "irrelevant"
            nonmatching.mkdir()
            for index in range(5):
                nonmatching = nonmatching / f"deep-{index}"
                nonmatching.mkdir()
            result, summary, output = self.run_summary(
                workspace,
                patterns="test-results/*.xml",
                max_depth="2",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("files=1\n", output)

            recursive = workspace / "recursive" / "nested"
            recursive.mkdir(parents=True)
            (recursive / "report.xml").write_text('<testsuite tests="1" />')
            result, _, output = self.run_summary(
                workspace,
                patterns="test-results/*.xml\nrecursive/**/*.xml",
                max_scan_entries="4",
                max_depth="3",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("files=2\n", output)

            covered = workspace / "covered" / "unit"
            covered.mkdir(parents=True)
            (covered / "report.xml").write_text('<testsuite tests="1" />')
            result, _, output = self.run_summary(
                workspace,
                patterns="covered/**/*.xml\ncovered/unit/*.xml",
                max_scan_entries="2",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("files=1\n", output)

            nested = results
            for index in range(5):
                nested = nested / f"level-{index}"
                nested.mkdir()
            (nested / "deep.xml").write_text('<testsuite tests="0" />')
            result, _, _ = self.run_summary(
                workspace,
                patterns="test-results/**/*.xml",
                max_depth="3",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("max-depth=3", result.stderr)

    def test_supports_deprecated_csp_contract_without_silent_zero_results(self) -> None:
        with tempfile.TemporaryDirectory(prefix="junit-summary-legacy-") as tmp:
            workspace = Path(tmp)
            results = workspace / "frontend/test-results"
            results.mkdir(parents=True)
            (results / "junit.xml").write_text(
                '<testsuite tests="3" failures="1" errors="0" skipped="0" time="2.5" />'
            )
            result, summary, output = self.run_summary(
                workspace,
                patterns="test-results/**/*.xml",
                legacy_cwd="frontend",
                legacy_variant="frontend-single",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("| 1 | 3 | 2 | 1 | 0 | 0 | 2.5s |", summary)
            self.assertIn("files=1\n", output)

    def test_bounds_pattern_contract_and_suite_nesting(self) -> None:
        with tempfile.TemporaryDirectory(prefix="junit-summary-structure-") as tmp:
            workspace = Path(tmp)
            results = workspace / "results"
            results.mkdir()
            nested = '<testsuite tests="0" />'
            for _ in range(130):
                nested = f"<testsuite>{nested}</testsuite>"
            (results / "nested.xml").write_text(nested)

            result, _, _ = self.run_summary(workspace)
            self.assertEqual(result.returncode, 2)
            self.assertIn("testsuite nesting exceeds 128", result.stderr)
            result, _, _ = self.run_summary(
                workspace,
                patterns="\n".join(f"results/report-{index}.xml" for index in range(65)),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("more than 64 entries", result.stderr)
            result, _, _ = self.run_summary(workspace, patterns="a" * 1025)
            self.assertEqual(result.returncode, 2)
            self.assertIn("1024 characters", result.stderr)
            for pattern in ("foo**bar/report.xml", "foo/**bar/report.xml"):
                result, _, _ = self.run_summary(workspace, patterns=pattern)
                self.assertEqual(result.returncode, 2)
                self.assertIn("complete path segment", result.stderr)

    def test_action_metadata_is_self_contained_and_exposes_numeric_outputs(self) -> None:
        data = action("junit-step-summary")
        step = data["runs"]["steps"][0]
        self.assertEqual(step["id"], "summary")
        self.assertIn("${GITHUB_ACTION_PATH}/junit_step_summary.py", step["run"])
        self.assertNotIn("github.workspace", step["run"])
        self.assertEqual(data["inputs"]["fail-on-missing"]["default"], "false")
        self.assertIn("deprecationMessage", data["inputs"]["cwd"])
        self.assertIn("deprecationMessage", data["inputs"]["variant"])
        self.assertEqual(data["inputs"]["max-total-bytes"]["default"], "52428800")
        self.assertEqual(data["inputs"]["max-scan-entries"]["default"], "100000")
        self.assertEqual(data["inputs"]["max-depth"]["default"], "64")
        self.assertEqual(
            set(data["outputs"]),
            {"files", "tests", "passed", "failures", "errors", "skipped", "duration", "has-failures"},
        )


class ComposeActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = action("compose-up")
        cls.steps = {step["name"]: step for step in cls.data["runs"]["steps"]}

    def run_validation(self, **overrides: str) -> tuple[subprocess.CompletedProcess[str], str]:
        with tempfile.TemporaryDirectory(prefix="compose-action-test-") as tmp:
            root = Path(tmp)
            env_file = root / "github-env"
            values = {
                "AFTER_HEALTH_HOOK": "hooks/check.sh", "BEFORE_COMPOSE_HOOK": "hooks/prepare.sh",
                "BUILD": "false", "COMPLETED_SERVICES": "migrate", "COMPOSE_FILES": "docker-compose.yml\ncompose.prod.yml",
                "DOWN_ON_TIMEOUT": "false", "SERVICES": "web,worker", "SHOW_LOGS_ON_FAILURE": "true",
                "PROFILES": "storage, redis",
                "TIMEOUT_SECONDS": "120", "URL_TIMEOUT_SECONDS": "5", "WAIT_FOR_HEALTH": "true",
                "WAIT_URLS": "http://127.0.0.1:8080/health", "WORKING_DIRECTORY": "deploy",
                "RUNNER_OS": "Linux", "GITHUB_ENV": str(env_file),
            }
            values.update(overrides)
            result = subprocess.run(["bash", "-c", self.steps["Validate Compose inputs"]["run"]], env={**os.environ, **values}, text=True, capture_output=True, check=False)
            return result, env_file.read_text() if env_file.exists() else ""

    def test_static_wrapper_is_pinned_and_has_one_standalone_call(self) -> None:
        text = (ROOT / "actions/compose-up/action.yml").read_text()
        self.assertEqual(text.count("uses: quokkify/compose-health-check-action@"), 1)
        self.assertIn("@1bd4a5793d977cdd8a14cca7bbfe3544b49bb3e0 # v2.4.0", text)
        self.assertNotIn("compose-health-check-action v2.3.0", text)
        self.assertNotIn("docker compose up", text)
        self.assertNotIn("docker inspect", text)
        self.assertEqual(sum(step.get("uses", "").startswith("quokkify/compose-health-check-action@") for step in self.data["runs"]["steps"]), 1)
        standalone = self.steps["Start Compose with standalone health engine"]
        self.assertEqual(standalone["with"]["timeout"], "${{ env.COMPOSE_TIMEOUT_SECONDS }}")
        self.assertEqual(standalone["with"]["additional-compose-args"], "${{ inputs.build == 'true' && '--build' || '' }}")
        self.assertEqual(standalone["with"]["compose-profiles"], "${{ env.COMPOSE_PROFILES_NORMALIZED }}")
        self.assertEqual(standalone["with"]["before-compose-hook"], "${{ env.COMPOSE_BEFORE_HOOK_NORMALIZED }}")
        self.assertEqual(standalone["with"]["after-health-hook"], "${{ env.COMPOSE_AFTER_HOOK_NORMALIZED }}")
        self.assertNotIn("--project-directory", text)

    def test_validation_rejects_unsupported_legacy_flags_before_startup(self) -> None:
        for name, value, message in (("WAIT_FOR_HEALTH", "false", "wait-for-health=false"), ("SHOW_LOGS_ON_FAILURE", "false", "show-logs-on-failure=false")):
            result, env_file = self.run_validation(**{name: value})
            self.assertEqual(result.returncode, 2)
            self.assertIn(message, result.stderr)
            self.assertEqual(env_file, "")

    def test_validation_rejects_unsafe_urls_and_paths(self) -> None:
        for values, message in ((
            {"WAIT_URLS": "file:///etc/passwd"}, "absolute HTTP(S)"
        ), (
            {"WAIT_URLS": "http:///no-host"}, "absolute HTTP(S)"
        ), (
            {"WAIT_URLS": "http://127.0.0.1:bad/health"}, "absolute HTTP(S)"
        ), (
            {"WAIT_URLS": "http://[::1/health"}, "absolute HTTP(S)"
        ), (
            {"WAIT_URLS": "http://127.0.0.1:8080/a b"}, "without whitespace"
        ), (
            {"WAIT_URLS": "http://127.0.0.1:8080/a\tb"}, "without whitespace"
        ), (
            {"WAIT_URLS": "http://127.0.0.1:8080/a\rb"}, "without whitespace"
        ), (
            {"WAIT_URLS": "http://127.0.0.1:8080/a\vb"}, "without whitespace"
        ), (
            {"WAIT_URLS": "http://127.0.0.1:8080/a\x1bb"}, "control characters"
        ), (
            {"COMPOSE_FILES": "../secret.yml"}, "traversal"
        ), (
            {"BEFORE_COMPOSE_HOOK": "../prepare.sh"}, "traversal"
        ), (
            {"AFTER_HEALTH_HOOK": "/tmp/check.sh"}, "absolute forms"
        ), (
            {"WORKING_DIRECTORY": "/tmp"}, "absolute forms"
        ), (
            {"WORKING_DIRECTORY": "C:/tmp"}, "absolute forms"
        ), (
            {"COMPOSE_FILES": "C:\\tmp\\compose.yml"}, "drive letters"
        ), (
            {"WORKING_DIRECTORY": "deploy\nother"}, "without whitespace"
        ), (
            {"WORKING_DIRECTORY": "deploy\rother"}, "without whitespace"
        ), (
            {"WORKING_DIRECTORY": "deploy\tother"}, "without whitespace"
        ), (
            {"WORKING_DIRECTORY": "deploy\vother"}, "control characters"
        ), (
            {"WORKING_DIRECTORY": "deploy\fother"}, "control characters"
        ), (
            {"WORKING_DIRECTORY": "deploy\x1bother"}, "control characters"
        ), (
            {"COMPOSE_FILES": "docker-compose.yml\r"}, "without whitespace"
        ), (
            {"COMPOSE_FILES": "\tdocker-compose.yml"}, "without whitespace"
        )):
            result, env_file = self.run_validation(**values)
            self.assertEqual(result.returncode, 2)
            self.assertIn(message, result.stderr)
            self.assertEqual(env_file, "")

    def test_validation_exports_prefixed_files_union_and_bounds(self) -> None:
        result, env_file = self.run_validation()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("deploy/docker-compose.yml", env_file)
        self.assertIn("deploy/compose.prod.yml", env_file)
        self.assertIn("COMPOSE_SERVICES_NORMALIZED=web worker migrate", env_file)
        self.assertIn("COMPOSE_PROFILES_NORMALIZED=storage redis", env_file)
        self.assertIn("COMPOSE_BEFORE_HOOK_NORMALIZED=deploy/hooks/prepare.sh", env_file)
        self.assertIn("COMPOSE_AFTER_HOOK_NORMALIZED=deploy/hooks/check.sh", env_file)
        self.assertIn("COMPOSE_TIMEOUT_SECONDS=120", env_file)
        result, _ = self.run_validation(TIMEOUT_SECONDS="0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("1 through 86400", result.stderr)
        for name, value in (
            ("TIMEOUT_SECONDS", "18446744073709551617"),
            ("URL_TIMEOUT_SECONDS", "18446744073709551617"),
            ("TIMEOUT_SECONDS", "86401"),
            ("URL_TIMEOUT_SECONDS", "301"),
        ):
            result, env_file = self.run_validation(**{name: value})
            self.assertEqual(result.returncode, 2)
            self.assertEqual(env_file, "")
        result, env_file = self.run_validation(TIMEOUT_SECONDS="00001", URL_TIMEOUT_SECONDS="00002")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("COMPOSE_TIMEOUT_SECONDS=1", env_file)
        self.assertIn("COMPOSE_URL_TIMEOUT_SECONDS=2", env_file)
        started = time.monotonic()
        result, env_file = self.run_validation(TIMEOUT_SECONDS="0" * 5000 + "1")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(env_file, "")
        self.assertLess(time.monotonic() - started, 1.0)

    def test_default_inputs_pass_validation(self) -> None:
        result, env_file = self.run_validation(
            COMPOSE_FILES="docker-compose.yml", SERVICES="", COMPLETED_SERVICES="",
            PROFILES="", BEFORE_COMPOSE_HOOK="", AFTER_HEALTH_HOOK="",
            WAIT_URLS="", WORKING_DIRECTORY=".",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("COMPOSE_FILES_NORMALIZED<<", env_file)
        self.assertIn("docker-compose.yml", env_file)
        self.assertIn("COMPOSE_SERVICES_NORMALIZED=\n", env_file)
        self.assertIn("COMPOSE_PROFILES_NORMALIZED=\n", env_file)
        self.assertIn("COMPOSE_BEFORE_HOOK_NORMALIZED=\n", env_file)
        self.assertIn("COMPOSE_AFTER_HOOK_NORMALIZED=\n", env_file)

    def test_profile_validation_enforces_compose_grammar(self) -> None:
        for unsafe in ("a", "--profile", "../foreign", "$(id)", "web;id"):
            result, env_file = self.run_validation(PROFILES=unsafe)
            self.assertEqual(result.returncode, 2)
            self.assertIn("profile names must match", result.stderr)
            self.assertEqual(env_file, "")
        result, env_file = self.run_validation(PROFILES="a1,b_2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("COMPOSE_PROFILES_NORMALIZED=a1 b_2", env_file)

    def test_service_union_is_unique_and_completed_only_preserves_standalone_defaults(self) -> None:
        result, env_file = self.run_validation(SERVICES="web,\nworker web", COMPLETED_SERVICES="worker\nmigrate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("COMPOSE_SERVICES_NORMALIZED=web worker migrate", env_file)
        result, env_file = self.run_validation(SERVICES="", COMPLETED_SERVICES="migrate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("COMPOSE_SERVICES_NORMALIZED=\n", env_file)
        result, env_file = self.run_validation(SERVICES=" \t , ", COMPLETED_SERVICES="migrate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("COMPOSE_SERVICES_NORMALIZED=\n", env_file)
        for unsafe in ("web,*", "web ../foreign", "web $(id)"):
            result, env_file = self.run_validation(SERVICES=unsafe, COMPLETED_SERVICES="")
            self.assertEqual(result.returncode, 2)
            self.assertIn("service names must match", result.stderr)
            self.assertEqual(env_file, "")
        for unsafe in ("*", "../foreign", "$(id)", "/abs", "--flag"):
            result, env_file = self.run_validation(SERVICES="", COMPLETED_SERVICES=unsafe)
            self.assertEqual(result.returncode, 2)
            self.assertIn("service names must match", result.stderr)
            self.assertEqual(env_file, "")

    def test_pinned_standalone_command_contract_keeps_global_flags_before_up(self) -> None:
        # v2.4.0 appends additional-compose-args after `up -d`, so this fake
        # mirrors its exact command order and guards against passing global
        # Compose flags such as --project-directory through that input.
        _, env_file = self.run_validation(WORKING_DIRECTORY="deploy", BUILD="true")
        files = env_file.split("COMPOSE_FILES_NORMALIZED<<COMPOSE_FILES_EOF\n", 1)[1].split("\nCOMPOSE_FILES_EOF", 1)[0].splitlines()
        additional_args = "--build"
        services = next(line.split("=", 1)[1] for line in env_file.splitlines() if line.startswith("COMPOSE_SERVICES_NORMALIZED="))
        argv = ["docker", "compose"]
        for file in files:
            argv.extend(["-f", file])
        argv.extend(["up", "-d", *shlex.split(additional_args), *shlex.split(services)])
        self.assertEqual(
            argv,
            ["docker", "compose", "-f", "deploy/docker-compose.yml", "-f", "deploy/compose.prod.yml", "up", "-d", "--build", "web", "worker", "migrate"],
        )
        self.assertNotIn("--project-directory", argv)

    def test_url_readiness_uses_bounded_probe_and_option_terminator(self) -> None:
        step = self.steps["Wait for HTTP readiness"]
        with tempfile.TemporaryDirectory(prefix="compose-url-test-") as tmp:
            log = Path(tmp) / "curl.log"
            curl = Path(tmp) / "curl"
            curl.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$*\" >> \"$CURL_LOG\"\n"
                "while (( $# )); do\n"
                "  if [[ \"$1\" == --max-time ]]; then\n"
                "    shift\n"
                "    [[ \"${1:-}\" =~ ^[0-9]+$ ]] || exit 64\n"
                "  fi\n"
                "  shift\n"
                "done\n"
            )
            curl.chmod(curl.stat().st_mode | stat.S_IXUSR)
            env = {**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}", "CURL_LOG": str(log), "TIMEOUT_SECONDS": "5", "URL_TIMEOUT_SECONDS": "2", "WAIT_URLS": "http://127.0.0.1:8080/health"}
            result = subprocess.run(["bash", "-c", step["run"]], env=env, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("-- http://127.0.0.1:8080/health", log.read_text())

    def test_url_readiness_does_not_echo_secret_fragments(self) -> None:
        step = self.steps["Wait for HTTP readiness"]
        with tempfile.TemporaryDirectory(prefix="compose-url-secret-test-") as tmp:
            log = Path(tmp) / "curl.log"
            curl = Path(tmp) / "curl"
            curl.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$CURL_LOG\"\nexit 1\n")
            curl.chmod(curl.stat().st_mode | stat.S_IXUSR)
            wait_url = "http://127.0.0.1:8080/health?api_key=top_secret"
            env = {
                **os.environ,
                "PATH": f"{tmp}:{os.environ['PATH']}",
                "CURL_LOG": str(log),
                "TIMEOUT_SECONDS": "5",
                "URL_TIMEOUT_SECONDS": "1",
                "WAIT_URLS": wait_url,
            }
            result = subprocess.run(["bash", "-c", step["run"]], env=env, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("top_secret", result.stdout + result.stderr)
            self.assertIn("top_secret", log.read_text())

    def test_url_timeout_does_not_sleep_past_global_deadline(self) -> None:
        step = self.steps["Wait for HTTP readiness"]
        with tempfile.TemporaryDirectory(prefix="compose-url-timeout-test-") as tmp:
            curl = Path(tmp) / "curl"
            curl.write_text("#!/usr/bin/env bash\nexit 1\n")
            curl.chmod(curl.stat().st_mode | stat.S_IXUSR)
            env = {
                **os.environ, "PATH": f"{tmp}:{os.environ['PATH']}", "TIMEOUT_SECONDS": "1",
                "URL_TIMEOUT_SECONDS": "1", "WAIT_URLS": "http://127.0.0.1:8080/health",
            }
            started = time.monotonic()
            result = subprocess.run(["bash", "-c", step["run"]], env=env, text=True, capture_output=True, check=False)
            elapsed = time.monotonic() - started
            self.assertEqual(result.returncode, 2)
            self.assertLess(elapsed, 1.5, f"URL loop exceeded global timeout: {elapsed:.3f}s")

    def test_cleanup_is_scoped_and_has_no_volume_flag(self) -> None:
        step = self.steps["Optional Compose cleanup after failure"]
        text = step["run"]
        self.assertIn('docker compose "${compose_args[@]}" down', text)
        self.assertNotIn("-v", text)
        self.assertIn("env.COMPOSE_STARTED == 'true'", step["if"])
        self.assertIn("inputs.down-on-timeout == 'true'", step["if"])
        self.assertEqual(self.data["inputs"]["down-on-timeout"]["default"], "false")
        marker = self.steps["Mark Compose startup complete"]
        self.assertEqual(marker["if"], "${{ steps.compose-health.outcome == 'success' }}")
        self.assertIn("COMPOSE_STARTED=true", marker["run"])
        self.assertNotIn("COMPOSE_STARTED=true", self.steps["Validate Compose inputs"]["run"])

    def test_invalid_hook_cannot_enable_cleanup(self) -> None:
        result, env_file = self.run_validation(AFTER_HEALTH_HOOK="../outside.sh", DOWN_ON_TIMEOUT="true")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("COMPOSE_STARTED=true", env_file)

    def test_cleanup_uses_prefixed_files_from_repository_root(self) -> None:
        step = self.steps["Optional Compose cleanup after failure"]
        with tempfile.TemporaryDirectory(prefix="compose-cleanup-test-") as tmp:
            log = Path(tmp) / "docker.log"
            docker = Path(tmp) / "docker"
            docker.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$PWD|$*\" >> \"$DOCKER_LOG\"\n")
            docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
            env = {
                **os.environ, "PATH": f"{tmp}:{os.environ['PATH']}", "DOCKER_LOG": str(log),
                "COMPOSE_FILES": "deploy/docker-compose.yml\ndeploy/compose.prod.yml",
                "COMPOSE_PROFILES": "storage redis",
            }
            result = subprocess.run(["bash", "-c", step["run"]], env=env, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            command = log.read_text()
            self.assertIn("--file deploy/docker-compose.yml --file deploy/compose.prod.yml --profile storage --profile redis down", command)
            self.assertNotIn("deploy/deploy", command)


class AllureReportActionTests(unittest.TestCase):
    def test_action_contract_is_preserved_by_thin_wrapper(self) -> None:
        data = action("allure-report")
        self.assertEqual(
            set(data["inputs"]),
            {
                "github-token",
                "results-directory",
                "report-directory",
                "config-file",
                "categories-file",
                "allure-version",
                "module-environment-label",
                "source-artifacts-directory",
                "pr-number",
                "pages-url",
                "fork-pr",
                "source-run-id",
                "comment-file",
                "comment-marker",
                "comment-author-login",
                "pyramid-enabled",
                "pyramid-markdown-file",
                "pyramid-json-file",
                "pyramid-gates-json-file",
                "pyramid-source-run-id",
                "pyramid-head-sha",
                "pyramid-policy-path",
                "pyramid-artifact-name",
                "pyramid-retention-days",
                "publish-pages",
                "pages-destination-directory",
                "pages-branch",
                "pages-retention-count",
            },
        )
        self.assertTrue(data["inputs"]["github-token"]["required"])
        self.assertEqual(data["inputs"]["publish-pages"]["default"], "false")
        self.assertEqual(data["inputs"]["pyramid-enabled"]["default"], "false")
        self.assertEqual(data["inputs"]["module-environment-label"]["default"], "module")
        self.assertEqual(data["inputs"]["source-artifacts-directory"]["default"], "auto")
        self.assertEqual(
            data["inputs"]["pyramid-policy-path"]["default"],
            "docs/testing/test-pyramid.md",
        )
        self.assertEqual(
            data["inputs"]["comment-marker"]["default"],
            "<!-- project-toolkit-allure-ci -->",
        )

        steps = data["runs"]["steps"]
        self.assertEqual(len(steps), 1)
        delegate = steps[0]
        self.assertRegex(
            delegate["uses"],
            r"^quokkify/allure-report-action@[0-9a-f]{40}$",
        )
        self.assertEqual(set(delegate["with"]), set(data["inputs"]))
        self.assertEqual(
            delegate["with"],
            {name: f"${{{{ inputs.{name} }}}}" for name in data["inputs"]},
        )

    def test_wrapper_uses_sidecar_metadata_release_and_has_no_vendor_copy(self) -> None:
        action_path = ROOT / "actions/allure-report/action.yml"
        text = action_path.read_text()
        self.assertRegex(
            text,
            r"uses: quokkify/allure-report-action@[0-9a-f]{40} # v\d+\.\d+\.\d+",
        )
        self.assertIn(
            "uses: quokkify/allure-report-action@138f38432a14c332dfc23832b8028502631f4c5e # v0.3.0",
            text,
        )
        self.assertFalse((action_path.parent / "allure-ci.mjs").exists())

    def test_renovate_manages_the_executable_release_pin(self) -> None:
        config = yaml.safe_load((ROOT / ".github/renovate.json").read_text())
        manager = next(
            item
            for item in config["customManagers"]
            if item.get("depNameTemplate") == "quokkify/allure-report-action"
        )
        self.assertIn("/^actions/allure-report/action\\.yml$/", manager["managerFilePatterns"])
        action_text = (ROOT / "actions/allure-report/action.yml").read_text()
        matches = [
            re.search(
                pattern.replace("(?<currentDigest>", "(?P<currentDigest>").replace(
                    "(?<currentValue>", "(?P<currentValue>"
                ),
                action_text,
            )
            for pattern in manager["matchStrings"]
            if "currentDigest" in pattern
        ]
        self.assertEqual(len(matches), 1)
        match = matches[0]
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.group("currentDigest"), "138f38432a14c332dfc23832b8028502631f4c5e")
        self.assertEqual(match.group("currentValue"), "v0.3.0")


class AllureTrustedCommentPropagationTests(unittest.TestCase):
    def test_generated_workflow_forwards_compact_comment_artifact_unchanged(self) -> None:
        copier = shutil.which("copier")
        if copier is None:
            self.skipTest("copier is required for generated workflow regression coverage")
        with tempfile.TemporaryDirectory(prefix="allure-comment-workflow-") as temporary:
            source = Path(temporary) / "template-source"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            destination = Path(temporary) / "fixture"
            subprocess.run(
                [copier, "copy", "--trust", "--defaults", "--data-file",
                 str(ROOT / "tests/scenarios/allure-pages.yml"), str(source), str(destination)],
                check=True, capture_output=True, text=True,
            )
            workflow = (destination / ".github/workflows/allure-report.yml").read_text()

        self.assertIn("actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093", workflow)
        self.assertIn('readFileSync(".allure-generated/allure-pr-comment.md", "utf8")', workflow)
        self.assertIn("body.endsWith(marker)", workflow)
        self.assertIn("allure-pr-comment.md", workflow)
        self.assertNotIn('let body = `${marker}', workflow)
        self.assertNotIn("Download the Allure HTML artifact]", workflow)
        self.assertNotIn("Open the source validation run]", workflow)

    def test_generated_q4j_fixture_materializes_compact_body_in_trusted_poster(self) -> None:
        copier = shutil.which("copier")
        node = shutil.which("node")
        if copier is None or node is None:
            self.skipTest("copier and Node.js are required for generated workflow regression coverage")

        marker = "<!-- project-toolkit-allure-report -->"
        compact_body = "\n".join(
            [
                "## ✅ Allure Report — passed",
                "",
                "2 / 2 tests passed · 100% pass rate",
                "",
                "| Tests | Passed | Failed | Broken | Skipped | Report |",
                "| ---: | ---: | ---: | ---: | ---: | :--- |",
                "| 2 | 2 | 0 | 0 | 0 | [View report ↗](https://q4j.example/allure?run=42) |",
                "",
                "<details>",
                "<summary><strong>Tests by layer</strong></summary>",
                "",
                "| Layer | Tests | Passed | Failed | Broken | Skipped |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
                "| Unit | 2 | 2 | 0 | 0 | 0 |",
                "| All layers | 2 | 2 | 0 | 0 | 0 |",
                "",
                "</details>",
                "",
                '<sub>Generated by <a href="https://github.com/quokkify/allure-report-action">quokkify/allure-report-action</a> · <a href="https://github.com/quokkify/allure-report-action/releases/latest">v0.3.0</a></sub>',
                "",
                marker,
            ]
        )

        with tempfile.TemporaryDirectory(prefix="allure-q4j-comment-") as temporary:
            source = Path(temporary) / "template-source"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            destination = Path(temporary) / "q4j-fixture"
            subprocess.run(
                [
                    copier,
                    "copy",
                    "--trust",
                    "--defaults",
                    "--data-file",
                    str(ROOT / "tests/scenarios/allure-pages.yml"),
                    str(source),
                    str(destination),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            workflow = yaml.safe_load(
                (destination / ".github/workflows/allure-report.yml").read_text()
            )
            poster_step = next(
                step
                for step in workflow["jobs"]["comment"]["steps"]
                if step.get("name") == "Revalidate source freshness and update comment"
            )
            generated_artifact = destination / ".allure-generated"
            generated_artifact.mkdir()
            # This is the q4j-like producer side of the contract: the report
            # action's compact body is uploaded as an artifact, then consumed
            # by the lower-privilege trusted poster job below.
            (generated_artifact / "allure-pr-comment.md").write_text(compact_body)
            wrapper = """\
const fs = require("fs");
const posted = [];
const failures = [];
const context = {
  payload: { workflow_run: {
    id: 42, workflow_id: 7, event: "pull_request", head_sha: "q4j-head",
    head_repository: { full_name: "q4j/q4j" },
  } },
  repo: { owner: "q4j", repo: "q4j" },
};
const github = {
  rest: {
    pulls: { get: async () => ({ data: {
      state: "open", head: { sha: "q4j-head", repo: { full_name: "q4j/q4j" } },
    } }) },
    issues: { updateComment: async ({ body }) => posted.push(body),
      createComment: async ({ body }) => posted.push(body) },
    actions: { listWorkflowRuns: "listWorkflowRuns" },
  },
  paginate: async (method, params) => params.issue_number
    ? [{ user: { login: "github-actions[bot]" }, body: "old" }]
    : [{ id: 42 }],
};
const core = {
  warning: () => {},
  setFailed: (message) => failures.push(message),
};
(async () => {
""" + poster_step["with"]["script"] + """
  fs.writeFileSync("posted.json", JSON.stringify({ posted, failures }));
})().catch((error) => {
  fs.writeFileSync("posted.json", JSON.stringify({ posted, failures: [String(error)] }));
  process.exitCode = 1;
});
"""
            (destination / "poster.js").write_text(wrapper)
            result = subprocess.run(
                [node, "poster.js"],
                cwd=destination,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            handoff = yaml.safe_load((destination / "posted.json").read_text())

        self.assertEqual(handoff["failures"], [])
        self.assertEqual(handoff["posted"], [compact_body])
        body = handoff["posted"][0]
        self.assertIn("## ✅ Allure Report — passed", body)
        self.assertIn("2 / 2 tests passed", body)
        self.assertIn("| Tests | Passed | Failed | Broken | Skipped | Report |", body)
        self.assertIn("<details>", body)
        self.assertIn("Tests by layer", body)
        self.assertIn("View report", body)
        self.assertNotIn("diagram", body.lower())
        self.assertNotIn("duration", body.lower())
        self.assertEqual(body.count(marker), 1)
        self.assertEqual(body.splitlines()[-1], marker)


class ReusableTestArtifactContractTests(unittest.TestCase):
    def test_language_workflows_share_opt_in_artifact_contract(self) -> None:
        defaults = {
            "python": "python-test-artifacts",
            "node": "node-test-artifacts",
            "java": "java-test-artifacts",
        }
        for language, default_name in defaults.items():
            with self.subTest(language=language):
                workflow = yaml.safe_load(
                    (ROOT / f".github/workflows/{language}-ci.yml").read_text()
                )
                triggers = workflow.get("on", workflow.get(True))
                inputs = triggers["workflow_call"]["inputs"]
                self.assertEqual(inputs["upload-test-artifacts"]["default"], False)
                self.assertEqual(inputs["test-artifact-path"]["default"], "test-results")
                self.assertEqual(inputs["test-artifact-name"]["default"], default_name)
                steps = workflow["jobs"]["ci"]["steps"]
                upload = next(step for step in steps if step.get("name") == "Upload test artifacts")
                self.assertEqual(
                    upload["if"],
                    "${{ always() && inputs.upload-test-artifacts }}",
                )
                self.assertEqual(upload["with"]["name"], "${{ inputs.test-artifact-name }}")
                self.assertIn("inputs.test-artifact-path", upload["with"]["path"])
                self.assertEqual(upload["with"]["if-no-files-found"], "error")


class DeployGhPagesSubdirTests(unittest.TestCase):
    def test_action_contract_is_preserved_by_thin_wrapper(self) -> None:
        data = action("deploy-gh-pages-subdir")
        self.assertEqual(data["runs"]["using"], "composite")
        self.assertEqual(
            set(data["inputs"]),
            {"token", "publish-dir", "destination-dir", "branch", "retention-count"},
        )
        self.assertTrue(data["inputs"]["token"]["required"])
        self.assertTrue(data["inputs"]["publish-dir"]["required"])
        self.assertTrue(data["inputs"]["destination-dir"]["required"])
        self.assertEqual(data["inputs"]["branch"]["default"], "gh-pages")
        self.assertEqual(data["inputs"]["retention-count"]["default"], "0")

        steps = data["runs"]["steps"]
        delegates = [
            step
            for step in steps
            if step.get("uses", "").startswith("quokkify/gh-pages-subdir-action@")
        ]
        self.assertEqual(len(steps), 1)
        self.assertEqual(len(delegates), 1)
        self.assertEqual(
            delegates[0]["with"],
            {
                "token": "${{ inputs.token }}",
                "publish-dir": "${{ inputs.publish-dir }}",
                "destination-dir": "${{ inputs.destination-dir }}",
                "branch": "${{ inputs.branch }}",
                "retention-count": "${{ inputs.retention-count }}",
            },
        )

    def test_wrapper_uses_an_immutable_standalone_release_and_has_no_vendor_copy(self) -> None:
        action_path = ROOT / "actions/deploy-gh-pages-subdir/action.yml"
        text = action_path.read_text()
        match = re.search(
            r"uses: quokkify/gh-pages-subdir-action@([0-9a-f]{40}) # v(\d+\.\d+\.\d+)",
            text,
        )
        self.assertIsNotNone(match)
        self.assertEqual(
            text.count("uses: quokkify/gh-pages-subdir-action@"), 1
        )
        self.assertFalse(
            (ROOT / "actions/deploy-gh-pages-subdir/deploy-gh-pages-subdir.sh").exists()
        )


if __name__ == "__main__":
    unittest.main()
