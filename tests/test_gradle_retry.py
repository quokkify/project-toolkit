from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "actions/gradle-retry/gradle-retry.sh"


class GradleRetryTests(unittest.TestCase):
    def run_case(self, mode: str, *, max_attempts: str = "3", persistent: bool = False) -> tuple[subprocess.CompletedProcess[str], int]:
        with tempfile.TemporaryDirectory(prefix="gradle-retry-test-") as temporary:
            root = Path(temporary)
            fake = root / "fake-gradle"
            count = root / "count"
            fake.write_text(
                "#!/usr/bin/env bash\n"
                "n=0; [[ -f \"$COUNT_FILE\" ]] && n=$(<\"$COUNT_FILE\")\n"
                "n=$((n + 1)); printf '%s' \"$n\" > \"$COUNT_FILE\"\n"
                "case \"$MODE\" in\n"
                "  ordinary) echo 'compilation failed'; exit 9;;\n"
                "  dsl) echo 'Could not find method implementation() for arguments'; exit 11;;\n"
                "  not-found) if [[ \"$*\" == *--refresh-dependencies* ]]; then [[ \"${PERSISTENT:-0}\" == 1 ]] && { echo 'Could not find org.example:missing:1.0.'; echo 'Searched in the following locations:'; exit 7; }; echo success; exit 0; fi; echo 'Could not find org.example:missing:1.0.'; echo 'Searched in the following locations:'; exit 7;;\n"
                "  rate-limit) [[ $n -lt 2 ]] && { echo 'Could not GET repository, status code 429'; exit 8; }; echo success; exit 0;;\n"
                "esac\n"
            )
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            env = {
                **os.environ,
                "COUNT_FILE": str(count),
                "GRADLE_RETRY_COMMAND": f"{fake} --task test",
                "GRADLE_RETRY_INITIAL_DELAY_SECONDS": "1",
                "GRADLE_RETRY_MAX_ATTEMPTS": max_attempts,
                "MODE": mode,
            }
            if mode == "not-found" and persistent:
                env["PERSISTENT"] = "1"
            result = subprocess.run(["bash", str(SCRIPT)], env=env, text=True, capture_output=True, check=False)
            return result, int(count.read_text())

    def test_successful_run_does_not_refresh(self) -> None:
        result, calls = self.run_case("success")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(calls, 1)
        self.assertNotIn("refresh-dependencies", result.stdout)

    def test_ordinary_failure_is_not_retried(self) -> None:
        result, calls = self.run_case("ordinary")
        self.assertEqual(result.returncode, 9)
        self.assertEqual(calls, 1)

    def test_dsl_not_found_is_not_retried_or_refreshed(self) -> None:
        result, calls = self.run_case("dsl")
        self.assertEqual(result.returncode, 11)
        self.assertEqual(calls, 1)
        self.assertNotIn("refresh-dependencies", result.stdout)

    def test_not_found_gets_exactly_one_refresh_retry(self) -> None:
        result, calls = self.run_case("not-found")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(calls, 2)
        self.assertIn("--refresh-dependencies", result.stdout)

    def test_persistent_not_found_fails_after_refresh(self) -> None:
        result, calls = self.run_case("not-found", persistent=True)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(calls, 2)

    def test_429_keeps_bounded_backoff_retry(self) -> None:
        result, calls = self.run_case("rate-limit", max_attempts="2")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(calls, 2)
        self.assertNotIn("refresh-dependencies", result.stdout)


if __name__ == "__main__":
    unittest.main()
