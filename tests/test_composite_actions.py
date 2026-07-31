from __future__ import annotations

import os
import stat
import subprocess
import tempfile
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
            "setup-java-gradle": {"CACHE_DEPENDENCIES": "yes"},
        }
        for name, values in cases.items():
            with self.subTest(name=name):
                first = action(name)["runs"]["steps"][0]
                self.assertIn("Validate", first["name"])
                self.assertNotIn("uses", first)
                result = subprocess.run(
                    ["bash", "-c", first["run"]],
                    env={**os.environ, **values},
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 2, result.stderr)

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


class ComposeActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = action("compose-up")["runs"]["steps"][0]["run"]

    def run_action(
        self,
        *,
        timeout: str = "5",
        health: str = "healthy",
        wait_urls: str = "http://127.0.0.1:8080/health",
        completed_services: str = "",
        completed_status: str = "exited",
        completed_exit: str = "0",
    ) -> tuple[subprocess.CompletedProcess[str], str, str]:
        with tempfile.TemporaryDirectory(prefix="compose-action-test-") as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            work_dir = root / "project"
            bin_dir.mkdir()
            work_dir.mkdir()
            (work_dir / "docker-compose.yml").write_text("services: {web: {image: scratch}}\n")
            docker_log = root / "docker.log"
            curl_log = root / "curl.log"

            docker = bin_dir / "docker"
            docker.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf '%s\\n' \"$*\" >> \"$DOCKER_LOG\"\n"
                "case \"$*\" in\n"
                "  *' config --services') printf 'web\\nmigrate\\n' ;;\n"
                "  *' ps --all --quiet web') echo web-id ;;\n"
                "  *' ps --all --quiet migrate') echo migrate-id ;;\n"
                "  'inspect --format {{.State.Running}} web-id') echo true ;;\n"
                "  'inspect --format {{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}} web-id') echo \"$FAKE_HEALTH\" ;;\n"
                "  'inspect --format {{.State.Status}} migrate-id') echo \"$COMPLETED_STATUS\" ;;\n"
                "  'inspect --format {{.State.ExitCode}} migrate-id') echo \"$COMPLETED_EXIT\" ;;\n"
                "esac\n"
            )
            docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
            curl = bin_dir / "curl"
            curl.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$CURL_LOG\"\nexit 0\n")
            curl.chmod(curl.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env.update(
                {
                    "BUILD": "false",
                    "COMPLETED_EXIT": completed_exit,
                    "COMPLETED_SERVICES": completed_services,
                    "COMPLETED_STATUS": completed_status,
                    "COMPOSE_FILES": "docker-compose.yml",
                    "DOCKER_LOG": str(docker_log),
                    "DOWN_ON_TIMEOUT": "true",
                    "FAKE_HEALTH": health,
                    "CURL_LOG": str(curl_log),
                    "PATH": f"{bin_dir}:{env['PATH']}",
                    "RUNNER_OS": "Linux",
                    "SERVICES": "web",
                    "SHOW_LOGS_ON_FAILURE": "true",
                    "TIMEOUT_SECONDS": timeout,
                    "WAIT_FOR_HEALTH": "true",
                    "WAIT_URLS": wait_urls,
                    "WORKING_DIRECTORY": str(work_dir),
                }
            )
            result = subprocess.run(["bash", "-c", self.script], env=env, text=True, capture_output=True, check=False)
            return (
                result,
                docker_log.read_text() if docker_log.exists() else "",
                curl_log.read_text() if curl_log.exists() else "",
            )

    def test_successful_readiness_and_url_option_terminator(self) -> None:
        result, docker_calls, curl_calls = self.run_action()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("up --detach", docker_calls)
        self.assertIn("-- http://127.0.0.1:8080/health", curl_calls)

    def test_completed_service_must_exit_zero(self) -> None:
        result, _, _ = self.run_action(completed_services="migrate")
        self.assertEqual(result.returncode, 0, result.stderr)
        result, docker_calls, _ = self.run_action(completed_services="migrate", completed_exit="7")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Completed service failed", result.stderr)
        self.assertIn(" down", docker_calls)

    def test_rejects_unsafe_urls_before_compose(self) -> None:
        for url in ("--help", "file:///etc/passwd", "not-a-url"):
            with self.subTest(url=url):
                result, docker_calls, curl_calls = self.run_action(wait_urls=url)
                self.assertEqual(result.returncode, 2)
                self.assertIn("absolute HTTP(S)", result.stderr)
                self.assertEqual(docker_calls, "")
                self.assertEqual(curl_calls, "")

    def test_timeout_bounds(self) -> None:
        for value in ("0", "01", "86401", "999999999999999999999999"):
            with self.subTest(value=value):
                result, docker_calls, _ = self.run_action(timeout=value)
                self.assertEqual(result.returncode, 2)
                self.assertIn("1 through 86400", result.stderr)
                self.assertEqual(docker_calls, "")

    def test_timeout_prints_diagnostics_and_runs_down(self) -> None:
        result, docker_calls, _ = self.run_action(timeout="1", health="starting")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Timed out", result.stderr)
        self.assertIn("logs --no-color --tail 100", docker_calls)
        self.assertIn(" down", docker_calls)


if __name__ == "__main__":
    unittest.main()
