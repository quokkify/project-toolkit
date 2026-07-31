from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "actions/compose-up/action.yml"


class ComposeActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        metadata = yaml.safe_load(ACTION.read_text())
        cls.script = metadata["runs"]["steps"][0]["run"]

    def run_action(self, *, timeout: str = "5", health: str = "healthy") -> tuple[subprocess.CompletedProcess[str], str]:
        with tempfile.TemporaryDirectory(prefix="compose-action-test-") as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            work_dir = root / "project"
            bin_dir.mkdir()
            work_dir.mkdir()
            (work_dir / "docker-compose.yml").write_text("services: {web: {image: scratch}}\n")
            log_path = root / "docker.log"

            docker = bin_dir / "docker"
            docker.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf '%s\\n' \"$*\" >> \"$LOG_FILE\"\n"
                "case \"$*\" in\n"
                "  *' config --services') echo web ;;\n"
                "  *' ps --quiet web') echo container-id ;;\n"
                "  'inspect --format {{.State.Running}} container-id') echo true ;;\n"
                "  'inspect --format {{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}} container-id') echo \"$FAKE_HEALTH\" ;;\n"
                "esac\n"
            )
            docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
            curl = bin_dir / "curl"
            curl.write_text("#!/usr/bin/env bash\nexit 0\n")
            curl.chmod(curl.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env.update(
                {
                    "BUILD": "false",
                    "COMPOSE_FILES": "docker-compose.yml",
                    "DOWN_ON_TIMEOUT": "true",
                    "FAKE_HEALTH": health,
                    "LOG_FILE": str(log_path),
                    "PATH": f"{bin_dir}:{env['PATH']}",
                    "SERVICES": "",
                    "SHOW_LOGS_ON_FAILURE": "true",
                    "TIMEOUT_SECONDS": timeout,
                    "WAIT_FOR_HEALTH": "true",
                    "WAIT_URLS": "http://127.0.0.1:8080/health",
                    "WORKING_DIRECTORY": str(work_dir),
                }
            )
            result = subprocess.run(
                ["bash", "-c", self.script],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            return result, log_path.read_text() if log_path.exists() else ""

    def test_successful_readiness(self) -> None:
        result, calls = self.run_action()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("up --detach", calls)
        self.assertNotIn(" down", calls)

    def test_rejects_zero_timeout_before_compose(self) -> None:
        result, calls = self.run_action(timeout="0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("positive integer", result.stderr)
        self.assertEqual(calls, "")

    def test_timeout_prints_diagnostics_and_runs_down(self) -> None:
        result, calls = self.run_action(timeout="1", health="starting")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Timed out", result.stderr)
        self.assertIn("logs --no-color --tail 100", calls)
        self.assertIn(" down", calls)


if __name__ == "__main__":
    unittest.main()
