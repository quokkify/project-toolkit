from __future__ import annotations

import os
import shlex
import stat
import subprocess
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
        self.assertEqual(validation["uses"], "gradle/actions/wrapper-validation@3f131e8634966bd73d06cc69884922b02e6faf92")
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
                "BUILD": "false", "COMPLETED_SERVICES": "migrate", "COMPOSE_FILES": "docker-compose.yml\ncompose.prod.yml",
                "DOWN_ON_TIMEOUT": "false", "SERVICES": "web,worker", "SHOW_LOGS_ON_FAILURE": "true",
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
        self.assertIn("@c11a8fa409adc13a0b7c401728d680872903af99 # v2.3.0", text)
        self.assertNotIn("docker compose up", text)
        self.assertNotIn("docker inspect", text)
        self.assertEqual(sum(step.get("uses", "").startswith("quokkify/compose-health-check-action@") for step in self.data["runs"]["steps"]), 1)
        standalone = self.steps["Start Compose with standalone health engine"]
        self.assertEqual(standalone["with"]["timeout"], "${{ env.COMPOSE_TIMEOUT_SECONDS }}")
        self.assertEqual(standalone["with"]["additional-compose-args"], "${{ inputs.build == 'true' && '--build' || '' }}")
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
            WAIT_URLS="", WORKING_DIRECTORY=".",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("COMPOSE_FILES_NORMALIZED<<", env_file)
        self.assertIn("docker-compose.yml", env_file)
        self.assertIn("COMPOSE_SERVICES_NORMALIZED=\n", env_file)

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
        # v2.3.0 appends additional-compose-args after `up -d`, so this fake
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
            }
            result = subprocess.run(["bash", "-c", step["run"]], env=env, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            command = log.read_text()
            self.assertIn("--file deploy/docker-compose.yml --file deploy/compose.prod.yml down", command)
            self.assertNotIn("deploy/deploy", command)


if __name__ == "__main__":
    unittest.main()
