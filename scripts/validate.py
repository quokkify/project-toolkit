#!/usr/bin/env python3
"""Validate toolkit policy, templates, and executable language fixtures."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from validate_python_fixture import validate_python_fixture

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []
PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument(
    "--static",
    action="store_true",
    help="run shared policy, template, and static checks without language fixtures",
)
ARGS = PARSER.parse_args() if __name__ == "__main__" else PARSER.parse_args([])


def check(condition: bool, message: str) -> None:
    """Record a validation error when a condition is false."""
    if not condition:
        ERRORS.append(message)


def run(cmd: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    """Run a command with visible, repository-relative provenance."""
    print(
        "+",
        " ".join(cmd),
        f"(cwd={cwd.relative_to(ROOT) if cwd.is_relative_to(ROOT) else cwd})",
    )
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def release_workflow_errors(path: Path) -> list[str]:
    """Validate the repository-level Release Please driver workflow contract."""
    errors: list[str] = []
    rel = path.relative_to(ROOT)

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(f"{rel}: {message}")

    try:
        workflow = yaml.safe_load(path.read_text())
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        return [f"{rel}: YAML parse failed: {exc}"]
    if not isinstance(workflow, dict):
        return [f"{rel}: workflow root must be a mapping"]

    triggers = workflow.get("on", workflow.get(True))
    require(isinstance(triggers, dict), "must define push and workflow_dispatch triggers")
    if isinstance(triggers, dict):
        require(
            set(triggers) == {"push", "workflow_dispatch"},
            "must define only push and workflow_dispatch triggers",
        )
        require(
            triggers.get("push") == {"branches": ["main"]},
            "push trigger must be limited to branches: [main]",
        )
        require("workflow_dispatch" in triggers, "must include workflow_dispatch")

    require(
        workflow.get("permissions")
        == {"contents": "write", "pull-requests": "write"},
        "permissions must be exactly contents:write and pull-requests:write",
    )
    require(
        workflow.get("concurrency")
        == {
            "group": "release-${{ github.workflow }}-${{ github.repository }}",
            "cancel-in-progress": False,
        },
        "concurrency must use the repository-scoped release group and must not cancel in-progress runs",
    )

    jobs = workflow.get("jobs")
    require(isinstance(jobs, dict), "jobs block must be a mapping")
    require(
        isinstance(jobs, dict) and set(jobs) == {"release"},
        "must define only the release caller job",
    )
    caller_jobs = (
        [job for job in jobs.values() if isinstance(job, dict) and "uses" in job]
        if isinstance(jobs, dict)
        else []
    )
    require(len(caller_jobs) == 1, "must define exactly one reusable workflow caller job")
    if not caller_jobs:
        return errors

    job = caller_jobs[0]
    require(
        job.get("uses") == "./.github/workflows/release-please.yml",
        "caller job must use ./.github/workflows/release-please.yml",
    )
    require(
        "steps" not in job and "runs-on" not in job,
        "caller job must not define steps or runs-on",
    )
    require(
        job.get("with")
        == {
            "mode": "manifest",
            "config-file": ".github/release-please/config.json",
            "manifest-file": ".github/release-please/manifest.json",
        },
        "caller job must pass manifest mode and current config/manifest paths",
    )
    return errors


def is_semver(value: object) -> bool:
    """Return whether value is SemVer 2.0.0, using only linear-time parsing."""
    if not isinstance(value, str) or not value:
        return False

    version_and_prerelease, separator, build = value.partition("+")
    if separator and (
        not build
        or "+" in build
        or any(
            not identifier
            or any(character not in ALPHANUMERIC_HYPHEN for character in identifier)
            for identifier in build.split(".")
        )
    ):
        return False

    core, separator, prerelease = version_and_prerelease.partition("-")
    if separator:
        if not prerelease:
            return False
        for identifier in prerelease.split("."):
            if not identifier or any(
                character not in ALPHANUMERIC_HYPHEN for character in identifier
            ):
                return False
            if is_ascii_digits(identifier) and len(identifier) > 1 and identifier[0] == "0":
                return False

    core_parts = core.split(".")
    return len(core_parts) == 3 and all(
        is_ascii_digits(part) and (part == "0" or part[0] != "0")
        for part in core_parts
    )


ALPHANUMERIC_HYPHEN = frozenset(
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-"
)


def is_ascii_digits(value: str) -> bool:
    return bool(value) and all("0" <= character <= "9" for character in value)


def release_manifest_errors(manifest: object) -> list[str]:
    """Return errors for the single-package Release Please manifest contract."""
    if not isinstance(manifest, dict) or set(manifest) != {"."}:
        return ["manifest must contain exactly the root package key '.'"]
    version = manifest["."]
    if not is_semver(version):
        return ["root package version must be a well-formed SemVer string"]
    return []


def validate_toolkit_workflow_errors(
    path: Path, workflow_override: object | None = None
) -> list[str]:
    """Validate the runner-selection DAG and isolated repository micro-jobs."""
    errors: list[str] = []
    rel = path.relative_to(ROOT)

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(f"{rel}: {message}")

    if workflow_override is None:
        try:
            workflow = yaml.safe_load(path.read_text())
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            return [f"{rel}: YAML parse failed: {exc}"]
    else:
        workflow = workflow_override
    if not isinstance(workflow, dict):
        return [f"{rel}: workflow root must be a mapping"]
    jobs = workflow.get("jobs")
    require(isinstance(jobs, dict), "jobs block must be a mapping")
    if not isinstance(jobs, dict):
        return errors
    require(
        set(jobs)
        == {
            "detect-runner",
            "lint",
            "gitleaks",
            "python",
            "node",
            "java",
            "validation-complete",
        },
        "must define detect-runner, lint, gitleaks, language, and aggregate jobs",
    )
    selector = jobs.get("detect-runner")
    require(isinstance(selector, dict), "detect-runner job must be a mapping")
    if isinstance(selector, dict):
        require(
            selector.get("uses") == "./.github/workflows/reusable-detect-runner.yml",
            "detect-runner must call the local reusable selector",
        )
        require(
            selector.get("secrets")
            == {"RUNNER_DISCOVERY_TOKEN": "${{ secrets.RUNNER_DISCOVERY_TOKEN }}"},
            "detect-runner must receive only the runner discovery token",
        )
        selector_inputs = selector.get("with", {})
        require(
            isinstance(selector_inputs, dict)
            and set(selector_inputs)
            == {"strategy", "same_repo", "trusted_author", "is_renovate_bot"},
            "detect-runner must pass the complete trust context",
        )
    expected = {
        "lint": {
            "setups": {"actions/setup-python", "actions/setup-node"},
            "command": "python scripts/validate.py --static",
            "needs": {"detect-runner"},
        },
        "gitleaks": {
            "setups": set(),
            "command": None,
            "needs": {"detect-runner"},
        },
        "python": {
            "setups": {"actions/setup-python"},
            "command": "python scripts/validate_python_fixture.py",
            "needs": {"detect-runner", "lint"},
        },
        "node": {
            "setups": {"actions/setup-node"},
            "command": "node scripts/validate_node_fixture.mjs",
            "needs": {"detect-runner", "lint"},
        },
        "java": {
            "setups": {"actions/setup-java"},
            "command": "bash scripts/validate_java_fixture.sh",
            "needs": {"detect-runner", "lint"},
        },
    }
    for name, contract in expected.items():
        job = jobs.get(name)
        if not isinstance(job, dict):
            require(False, f"{name} job must be a mapping")
            continue
        steps = job.get("steps")
        if not isinstance(steps, list):
            require(False, f"{name} job must define steps")
            continue
        needs = job.get("needs")
        needs_set = (
            {needs}
            if isinstance(needs, str)
            else set(needs)
            if isinstance(needs, list)
            else set()
        )
        require(needs_set == contract["needs"], f"{name} job has incorrect dependencies")
        require(
            job.get("runs-on") == "${{ fromJson(needs.detect-runner.outputs.runs_on) }}",
            f"{name} job must use the detected runner",
        )
        require(
            "github.event_name != 'pull_request_target'" in str(job.get("if", "")),
            f"{name} must reject pull_request_target",
        )
        require("secrets" not in job, f"{name} job must not inherit secrets")
        setup_actions: set[str] = set()
        commands: list[str] = []
        checkout_found = False
        for step in steps:
            if not isinstance(step, dict):
                continue
            use = step.get("uses")
            if isinstance(use, str):
                action = use.rpartition("@")[0]
                if action == "actions/checkout":
                    checkout_found = True
                    action_inputs = step.get("with")
                    require(
                        isinstance(action_inputs, dict)
                        and action_inputs.get("persist-credentials") is False,
                        f"{name} checkout must set persist-credentials: false",
                    )
                if action.startswith("actions/setup-"):
                    setup_actions.add(action)
            command = step.get("run")
            if isinstance(command, str):
                commands.append(command)
        require(checkout_found, f"{name} job must check out the repository")
        require(
            setup_actions == contract["setups"],
            f"{name} job has unexpected toolchain setup actions: {sorted(setup_actions)}",
        )
        if contract["command"] is not None:
            require(
                contract["command"] in commands,
                f"{name} job must run only its focused validation entrypoint",
            )
        if name == "java":
            java_steps = [
                step
                for step in steps
                if isinstance(step, dict)
                and step.get("run") == "bash scripts/validate_java_fixture.sh"
            ]
            require(
                len(java_steps) == 1
                and java_steps[0].get("env") == {"REQUIRE_MAVEN": "1"},
                "java CI validation must require Maven",
            )
        other_commands = {
            value["command"]
            for key, value in expected.items()
            if key != name and value["command"] is not None
        }
        require(
            not other_commands.intersection(commands),
            f"{name} job invokes another job's validation entrypoint",
        )
    gitleaks = jobs.get("gitleaks")
    if isinstance(gitleaks, dict):
        steps = gitleaks.get("steps", [])
        checkout_steps = [
            step
            for step in steps
            if isinstance(step, dict)
            and str(step.get("uses", "")).startswith("actions/checkout@")
        ]
        require(len(checkout_steps) == 1, "gitleaks must define exactly one checkout step")
        if checkout_steps:
            checkout_inputs = checkout_steps[0].get("with", {})
            require(
                isinstance(checkout_inputs, dict) and checkout_inputs.get("fetch-depth") == 0,
                "gitleaks checkout must fetch full history",
            )
        install_steps = [
            step
            for step in steps
            if isinstance(step, dict) and step.get("name") == "Install checksum-verified Gitleaks"
        ]
        require(len(install_steps) == 1, "gitleaks must define one checksum-verified install")
        if install_steps:
            install = install_steps[0]
            install_env = install.get("env", {})
            version = install_env.get("GITLEAKS_VERSION") if isinstance(install_env, dict) else None
            checksum = install_env.get("GITLEAKS_SHA256") if isinstance(install_env, dict) else None
            require(
                is_semver(version),
                "gitleaks release version must be pinned to exact SemVer",
            )
            require(
                isinstance(checksum, str) and re.fullmatch(r"[0-9a-f]{64}", checksum) is not None,
                "gitleaks release archive must use a pinned SHA-256 checksum",
            )
            install_script = str(install.get("run", ""))
            for marker in (
                "gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${archive}",
                'printf \'%s  %s\\n\' "$GITLEAKS_SHA256" "$archive" | sha256sum -c -',
                'install -m 0755 gitleaks "$HOME/.local/bin/gitleaks"',
                'echo "$HOME/.local/bin" >> "$GITHUB_PATH"',
            ):
                require(marker in install_script, f"gitleaks install is missing marker: {marker}")
        scan_steps = [
            step
            for step in steps
            if isinstance(step, dict) and step.get("name") == "Scan Git history and current tree"
        ]
        require(len(scan_steps) == 1, "gitleaks must define one history and tree scan")
        if scan_steps:
            scan_script = str(scan_steps[0].get("run", ""))
            for command in (
                "gitleaks git --redact --no-banner .",
                "gitleaks dir --redact --no-banner .",
            ):
                require(command in scan_script, f"gitleaks scan must run redacted command: {command}")
            require("--report-path" not in scan_script, "gitleaks must not persist a findings report")
        require(
            not any(
                isinstance(step, dict)
                and str(step.get("uses", "")).startswith("actions/upload-artifact@")
                for step in steps
            ),
            "gitleaks must not upload potentially secret-bearing artifacts",
        )
    aggregate = jobs.get("validation-complete")
    require(
        isinstance(aggregate, dict),
        "validation-complete aggregate must be a mapping",
    )
    if isinstance(aggregate, dict):
        needs = aggregate.get("needs")
        require(
            isinstance(needs, list)
            and set(needs) == {"detect-runner", "lint", "gitleaks", "python", "node", "java"},
            "validate aggregate must depend on every required stage",
        )
        require(
            aggregate.get("if")
            == "${{ always() && github.event_name != 'pull_request_target' }}",
            "validate aggregate must always evaluate and reject pull_request_target",
        )
        require(
            aggregate.get("runs-on") == "ubuntu-latest",
            "validate aggregate must use a fixed fallback runner",
        )
        aggregate_text = json.dumps(aggregate)
        for stage in ("detect-runner", "lint", "gitleaks", "python", "node", "java"):
            require(
                f"needs.{stage}.result" in aggregate_text,
                f"validate aggregate must fail closed on {stage}",
            )
        require("exit 1" in aggregate_text, "validate aggregate must fail with a non-zero status")
    return errors


def runner_selection_allows_self_hosted(
    strategy: str,
    *,
    same_repo: bool = False,
    trusted_author: bool = False,
    is_renovate_bot: bool = False,
) -> bool:
    """Model the reusable selector's trust gate for negative policy probes."""
    if strategy == "push_any":
        return True
    if strategy == "pr_trusted":
        return same_repo and (trusted_author or is_renovate_bot)
    return False


def validation_aggregate_succeeds(results: dict[str, str]) -> bool:
    """Model the aggregate job's requirement that every stage succeeds."""
    required = {"detect-runner", "lint", "gitleaks", "python", "node", "java"}
    return set(results) == required and all(result == "success" for result in results.values())


def validate_toolkit_workflow_negative_probes(path: Path) -> list[str]:
    """Prove the workflow contract rejects Gitleaks bypass mutations."""
    try:
        workflow = yaml.safe_load(path.read_text())
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        return [f"{path.relative_to(ROOT)}: negative probe YAML parse failed: {exc}"]
    if not isinstance(workflow, dict):
        return [f"{path.relative_to(ROOT)}: negative probes require a mapping"]
    errors: list[str] = []

    def clone() -> dict:
        return json.loads(json.dumps(workflow))

    def step_by_name(mutated: dict, job_name: str, step_name: str) -> dict:
        jobs = mutated.get("jobs")
        job = jobs.get(job_name) if isinstance(jobs, dict) else None
        steps = job.get("steps") if isinstance(job, dict) else None
        if isinstance(steps, list):
            for step in steps:
                if isinstance(step, dict) and step.get("name") == step_name:
                    return step
        return {}

    def require_rejection(mutated: object, marker: str, label: str) -> None:
        probe_errors = validate_toolkit_workflow_errors(path, mutated)
        if not any(marker in error for error in probe_errors):
            errors.append(f"{path.relative_to(ROOT)}: negative probe accepted {label}")

    mutated = clone()
    del mutated["jobs"]["gitleaks"]
    require_rejection(mutated, "must define detect-runner, lint, gitleaks", "missing gitleaks job")

    mutated = clone()
    mutated["jobs"]["gitleaks"]["needs"] = []
    require_rejection(mutated, "gitleaks job has incorrect dependencies", "detector bypass")

    mutated = clone()
    mutated["jobs"]["gitleaks"]["runs-on"] = "ubuntu-latest"
    require_rejection(mutated, "gitleaks job must use the detected runner", "runner wiring bypass")

    mutated = clone()
    checkout = step_by_name(mutated, "gitleaks", "Check out full repository history")
    checkout.setdefault("with", {})["fetch-depth"] = 1
    require_rejection(mutated, "gitleaks checkout must fetch full history", "shallow checkout")

    mutated = clone()
    install = step_by_name(mutated, "gitleaks", "Install checksum-verified Gitleaks")
    install.setdefault("env", {})["GITLEAKS_VERSION"] = "latest"
    require_rejection(mutated, "version must be pinned", "unpinned release")

    mutated = clone()
    step_by_name(mutated, "gitleaks", "Install checksum-verified Gitleaks")["run"] = (
        "install gitleaks"
    )
    require_rejection(mutated, "sha256sum -c", "checksum bypass")

    mutated = clone()
    step_by_name(mutated, "gitleaks", "Scan Git history and current tree")["run"] = (
        "gitleaks git .\ngitleaks dir ."
    )
    require_rejection(mutated, "redacted command", "redaction bypass")

    mutated = clone()
    aggregate_needs = mutated["jobs"]["validation-complete"].get("needs")
    mutated["jobs"]["validation-complete"]["needs"] = [
        need for need in aggregate_needs if need != "gitleaks"
    ] if isinstance(aggregate_needs, list) else []
    require_rejection(mutated, "depend on every required stage", "aggregate dependency bypass")

    mutated = clone()
    aggregate_step = step_by_name(mutated, "validation-complete", "Validate stage results")
    aggregate_script = str(aggregate_step.get("run", ""))
    aggregate_step["run"] = "\n".join(
        line for line in aggregate_script.splitlines() if "needs.gitleaks.result" not in line
    )
    require_rejection(mutated, "fail closed on gitleaks", "aggregate result bypass")

    successful_results = {
        stage: "success"
        for stage in ("detect-runner", "lint", "gitleaks", "python", "node", "java")
    }
    if not validation_aggregate_succeeds(successful_results):
        errors.append(f"{path.relative_to(ROOT)}: aggregate positive probe rejected success")
    for failed_stage in successful_results:
        failed_results = dict(successful_results)
        failed_results[failed_stage] = "failure"
        if validation_aggregate_succeeds(failed_results):
            errors.append(
                f"{path.relative_to(ROOT)}: aggregate negative probe accepted {failed_stage}"
            )
    return errors


def reusable_runner_workflow_errors(path: Path) -> list[str]:
    """Validate fail-closed runner discovery and its reusable outputs."""
    errors: list[str] = []
    rel = path.relative_to(ROOT)

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(f"{rel}: {message}")

    try:
        workflow = yaml.safe_load(path.read_text())
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        return [f"{rel}: YAML parse failed: {exc}"]
    if not isinstance(workflow, dict):
        return [f"{rel}: workflow root must be a mapping"]
    triggers = workflow.get("on", workflow.get(True))
    call = triggers.get("workflow_call") if isinstance(triggers, dict) else None
    require(isinstance(call, dict), "must expose workflow_call")
    if isinstance(call, dict):
        call_inputs = call.get("inputs")
        require(
            isinstance(call_inputs, dict)
            and set(call_inputs)
            == {"strategy", "same_repo", "trusted_author", "is_renovate_bot"},
            "workflow_call inputs must expose the complete trust context",
        )
        require(
            call.get("secrets")
            == {
                "RUNNER_DISCOVERY_TOKEN": {
                    "description": "Token used only to list repository self-hosted runners",
                    "required": False,
                }
            },
            "workflow_call must declare only the optional runner discovery token",
        )
        require(
            set(call.get("outputs", {})) == {"runs_on", "is_self_hosted"},
            "workflow_call outputs must expose runner labels and hosting mode",
        )
    require(
        workflow.get("permissions") == {"contents": "read", "actions": "none"},
        "permissions must be exactly contents:read and actions:none",
    )
    jobs = workflow.get("jobs", {})
    require(
        isinstance(jobs, dict) and set(jobs) == {"detect-runner"},
        "must define one selector job",
    )
    job = jobs.get("detect-runner", {}) if isinstance(jobs, dict) else {}
    if not isinstance(job, dict):
        job = {}
    require(job.get("runs-on") == "ubuntu-latest", "selector must bootstrap on ubuntu-latest")
    steps = job.get("steps", []) if isinstance(job, dict) else []
    script_steps = [step for step in steps if isinstance(step, dict) and step.get("id") == "select"]
    require(len(script_steps) == 1, "must define exactly one select step")
    if script_steps:
        step = script_steps[0]
        use = step.get("uses", "")
        require(
            re.fullmatch(r"actions/github-script@[0-9a-f]{40}", use) is not None,
            "github-script must be pinned to a full SHA",
        )
        require(
            step.get("env")
            == {
                "DISCOVERY_TOKEN_AVAILABLE": "${{ secrets.RUNNER_DISCOVERY_TOKEN != '' }}",
                "STRATEGY": "${{ inputs.strategy }}",
                "SAME_REPO": "${{ inputs.same_repo }}",
                "TRUSTED_AUTHOR": "${{ inputs.trusted_author }}",
                "IS_RENOVATE_BOT": "${{ inputs.is_renovate_bot }}",
            },
            "selector must pass trust inputs through the environment",
        )
        script = str(step.get("with", {}).get("script", ""))
        for marker in (
            "strategy === 'push_any'",
            "strategy === 'pr_trusted'",
            "process.env.STRATEGY",
            "process.env.SAME_REPO",
            "process.env.TRUSTED_AUTHOR",
            "process.env.IS_RENOVATE_BOT",
            "listSelfHostedRunnersForRepo",
            "runner.status === 'online'",
            "process.env.DISCOVERY_TOKEN_AVAILABLE !== 'true'",
            "Runner discovery token is not configured",
            "setHosted();",
            "catch (error)",
        ):
            require(marker in script, f"selector script is missing fail-closed marker: {marker}")
    probes = {
        "fork trusted author": runner_selection_allows_self_hosted(
            "pr_trusted", same_repo=False, trusted_author=True
        ),
        "same-repo untrusted author": runner_selection_allows_self_hosted(
            "pr_trusted", same_repo=True
        ),
        "unknown strategy": runner_selection_allows_self_hosted("unknown"),
    }
    for label, selected in probes.items():
        require(not selected, f"negative runner-selection probe allowed {label}")
    require(
        runner_selection_allows_self_hosted(
            "pr_trusted", same_repo=True, trusted_author=True
        ),
        "trusted same-repository PR probe must allow discovery",
    )
    require(
        runner_selection_allows_self_hosted(
            "pr_trusted", same_repo=True, is_renovate_bot=True
        ),
        "same-repository Renovate probe must allow discovery",
    )
    require(
        runner_selection_allows_self_hosted("push_any"),
        "push strategy probe must allow discovery",
    )
    return errors


def codeql_runner_workflow_errors(path: Path) -> list[str]:
    """Validate that CodeQL remains separate and uses the trusted runner selector."""
    rel = path.relative_to(ROOT)
    try:
        workflow = yaml.safe_load(path.read_text())
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        return [f"{rel}: YAML parse failed: {exc}"]
    if not isinstance(workflow, dict):
        return [f"{rel}: workflow root must be a mapping"]
    jobs = workflow.get("jobs", {})
    if not isinstance(jobs, dict) or set(jobs) != {"detect-runner", "analyze"}:
        return [f"{rel}: must define exactly detect-runner and analyze jobs"]
    errors: list[str] = []
    selector = jobs["detect-runner"]
    analyze = jobs["analyze"]
    if not isinstance(selector, dict) or not isinstance(analyze, dict):
        return [f"{rel}: detect-runner and analyze jobs must be mappings"]
    if selector.get("uses") != "./.github/workflows/reusable-detect-runner.yml":
        errors.append(f"{rel}: detect-runner must call the local reusable selector")
    if selector.get("secrets") != {
        "RUNNER_DISCOVERY_TOKEN": "${{ secrets.RUNNER_DISCOVERY_TOKEN }}"
    }:
        errors.append(f"{rel}: detect-runner must receive only the runner discovery token")
    if analyze.get("needs") != "detect-runner":
        errors.append(f"{rel}: analyze must depend on detect-runner")
    if analyze.get("runs-on") != "${{ fromJson(needs.detect-runner.outputs.runs_on) }}":
        errors.append(f"{rel}: analyze must use the detected runner")
    analyze_strategy = analyze.get("strategy")
    matrix = analyze_strategy.get("matrix", {}) if isinstance(analyze_strategy, dict) else {}
    include = matrix.get("include", []) if isinstance(matrix, dict) else []
    expected_languages = {
        ("python", "none"),
        ("javascript-typescript", "none"),
        ("java-kotlin", "none"),
    }
    configured_languages = {
        (entry.get("language"), entry.get("build-mode"))
        for entry in include
        if isinstance(entry, dict)
    }
    if configured_languages != expected_languages:
        errors.append(f"{rel}: every CodeQL language must use explicit build-mode none")
    steps = analyze.get("steps", [])
    init_steps = [
        step
        for step in steps
        if isinstance(step, dict)
        and str(step.get("uses", "")).startswith("github/codeql-action/init@")
    ]
    if len(init_steps) != 1 or init_steps[0].get("with", {}).get("build-mode") != (
        "${{ matrix.build-mode }}"
    ):
        errors.append(f"{rel}: CodeQL init must receive the explicit matrix build mode")
    return errors


RENOVATE_SCHEMA = "https://docs.renovatebot.com/renovate-schema.json"
RENOVATE_PRESET_PATHS = {
    "default": "presets/base",
    "python": "presets/python/default",
    "javascript": "presets/npm/default",
    "java": "presets/gradle/default",
    "docker": "presets/docker/default",
    "github-actions": "presets/github-actions/default",
}


def renovate_extends(repository: str, presets: list[str]) -> list[str]:
    """Return exact Renovate extends entries for selected preset names."""
    return [f"github>{repository}//{RENOVATE_PRESET_PATHS[preset]}" for preset in presets]


def assert_generated_renovate_config(path: Path, expected_extends: list[str], label: str) -> None:
    """Validate the generated Renovate file shape and exact shared preset refs."""
    try:
        data = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        ERRORS.append(f"{label}: renovate.json is not valid JSON: {exc}")
        return
    check(data.get("$schema") == RENOVATE_SCHEMA, f"{label}: renovate schema mismatch")
    check(
        data.get("extends") == expected_extends,
        f"{label}: renovate extends mismatch: {data.get('extends')!r}",
    )


for path in sorted([*ROOT.rglob("*.yml"), *ROOT.rglob("*.yaml")]):
    if ".git" in path.parts or "templates/project/template" in path.as_posix():
        continue
    try:
        yaml.safe_load(path.read_text())
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        ERRORS.append(f"{path.relative_to(ROOT)}: YAML: {exc}")


BOOLEAN_INPUTS = {
    "build",
    "cache-dependencies",
    "down-on-timeout",
    "fail-on-missing",
    "fork-pr",
    "install-dependencies",
    "publish-pages",
    "pyramid-enabled",
    "show-logs-on-failure",
    "wait-for-health",
}
EXPECTED_ACTIONS = {
    "allure-report",
    "compose-up",
    "deploy-gh-pages-subdir",
    "junit-step-summary",
    "setup-java-gradle",
    "setup-node",
    "setup-python",
}


def validate_action_metadata(data: object, label: str) -> list[str]:
    """Return fail-closed metadata errors for one composite action."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return [f"{label}: action metadata must be a mapping"]
    allowed_top = {"name", "description", "author", "branding", "inputs", "outputs", "runs"}
    for key in sorted(set(data) - allowed_top):
        errors.append(f"{label}: unknown top-level key {key}")
    if not data.get("name") or not data.get("description"):
        errors.append(f"{label}: action requires name and description")
    for forbidden in ("permissions", "secrets"):
        if forbidden in data:
            errors.append(f"{label}: composite action must not declare {forbidden}")

    inputs = data.get("inputs", {})
    if not isinstance(inputs, dict):
        errors.append(f"{label}: inputs must be a mapping")
        inputs = {}
    for name, spec in inputs.items():
        if not isinstance(spec, dict) or not spec.get("description"):
            errors.append(f"{label}: input {name} requires a description")
            continue
        unknown = set(spec) - {"description", "required", "default", "deprecationMessage"}
        if unknown:
            errors.append(f"{label}: input {name} has unknown keys: {sorted(unknown)}")
        if "required" in spec and not isinstance(spec["required"], bool):
            errors.append(f"{label}: input {name} required must be boolean")
        if name in BOOLEAN_INPUTS and spec.get("default") not in ("true", "false"):
            errors.append(f"{label}: boolean input {name} requires a true/false string default")

    outputs = data.get("outputs", {})
    if not isinstance(outputs, dict):
        errors.append(f"{label}: outputs must be a mapping")
    else:
        for name, spec in outputs.items():
            if not isinstance(spec, dict) or not spec.get("description") or not spec.get("value"):
                errors.append(f"{label}: output {name} requires description and value")
                continue
            unknown = set(spec) - {"description", "value"}
            if unknown:
                errors.append(f"{label}: output {name} has unknown keys: {sorted(unknown)}")

    runs = data.get("runs", {})
    if not isinstance(runs, dict) or runs.get("using") != "composite":
        errors.append(f"{label}: action must use composite runner")
        return errors
    for key in sorted(set(runs) - {"using", "steps"}):
        errors.append(f"{label}: runs has unknown key {key}")
    steps = runs.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append(f"{label}: action requires non-empty runs.steps")
        return errors
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict) or ("uses" in step) == ("run" in step):
            errors.append(f"{label}: step {index} must declare exactly one of uses or run")
        elif "run" in step and not step.get("shell"):
            errors.append(f"{label}: run step {index} requires an explicit shell")
        if isinstance(step, dict):
            allowed_step = {"name", "id", "if", "uses", "with", "run", "shell", "env", "working-directory"}
            unknown = set(step) - allowed_step
            if unknown:
                errors.append(f"{label}: step {index} has unknown keys: {sorted(unknown)}")
    return errors


action_paths = sorted((ROOT / "actions").glob("*/action.yml"))
check(
    {path.parent.name for path in action_paths} == EXPECTED_ACTIONS,
    "actions/: expected exactly the six documented composite actions",
)
for action_path in action_paths:
    data = yaml.safe_load(action_path.read_text())
    label = str(action_path.relative_to(ROOT))
    ERRORS.extend(validate_action_metadata(data, label))
    if isinstance(data, dict) and isinstance(data.get("runs"), dict):
        steps = data["runs"].get("steps", [])
        if isinstance(steps, list):
            for index, step in enumerate(steps, 1):
                if isinstance(step, dict) and isinstance(step.get("run"), str):
                    syntax = subprocess.run(
                        ["bash", "-n"],
                        input=step["run"],
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    check(
                        syntax.returncode == 0,
                        f"{label}: run step {index} has invalid bash syntax: {syntax.stderr.strip()}",
                    )


def validate_gh_pages_subdir_manager_regex() -> list[str]:
    """Regression probes for the gh-pages-subdir-action regex matcher."""
    errors: list[str] = []

    try:
        renovate = json.loads((ROOT / ".github/renovate.json").read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f".github/renovate.json regex probe requires valid JSON: {exc}"]

    manager = next(
        (
            m
            for m in renovate.get("customManagers", [])
            if m.get("depNameTemplate") == "quokkify/gh-pages-subdir-action"
        ),
        None,
    )
    if manager is None:
        return ["renovate.json missing quokkify/gh-pages-subdir-action custom manager"]

    match_strings = manager.get("matchStrings")
    if not isinstance(match_strings, list) or not match_strings:
        return ["renovate.json missing matchStrings for gh-pages-subdir-action manager"]
    pattern = match_strings[0]

    try:
        # Renovate regex uses JavaScript-style named groups (?<currentValue>).
        # Python supports (?P<name>), so normalize before compiling probe fixtures.
        matcher = re.compile(pattern.replace("(?<currentValue>", "(?P<currentValue>"))
    except re.error as exc:
        return [f"renovate.json invalid gh-pages-subdir-action regex: {exc}"]

    positive = {
        "plain-text": "`gh-pages-subdir-action` `v2.6.0`",
        "markdown-link": "[quokkify/gh-pages-subdir-action](https://github.com/quokkify/gh-pages-subdir-action) `v2.6.0`",
        "comment-context": "delegates to gh-pages-subdir-action v2.6.0",
    }
    for label, text in positive.items():
        match = matcher.search(text)
        if not match or match.group("currentValue") != "v2.6.0":
            errors.append(f"gh-pages-subdir regex probe failed to match {label}: {text}")

    for label, text in {
        "missing-separator": "gh-pages-subdir-actionv2.6.0",
        "version-suffix": "gh-pages-subdir-action v2.6.0-beta",
        "ownerless-prefix": "myquokkify/gh-pages-subdir-action v2.6.0",
        "ownerful-prefix": "foo/gh-pages-subdir-action v2.6.0",
        "suffix-no-space": "gh-pages-subdir-action-extra v2.6.0",
        "inline-use": "random quokkify/project-toolkit/actions/deploy-gh-pages-subdir@v2.6.0",
    }.items():
        if matcher.search(text):
            errors.append(f"gh-pages-subdir regex probe over-matched {label}: {text}")

    return errors


# Validate gh-pages-subdir-action Renovate regex against fixtures to avoid drift.
ERRORS.extend(validate_gh_pages_subdir_manager_regex())

# Negative contract probes prove that permission/secret leakage, malformed booleans,
# and ambiguous run steps are rejected by the validator itself.
negative_probe = {
    "name": "invalid",
    "description": "invalid",
    "permissions": {"contents": "write"},
    "secrets": {"token": {}},
    "inputs": {"build": {"description": "bad", "default": "yes"}},
    "runs": {"using": "composite", "steps": [{"run": "true"}]},
}
negative_errors = validate_action_metadata(negative_probe, "negative-probe")
for expected in ("permissions", "secrets", "true/false", "explicit shell"):
    check(
        any(expected in error for error in negative_errors),
        f"action validator negative probe did not reject {expected}",
    )

def setup_policy_errors(example: object, texts: dict[str, str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(example, dict) or example.get("permissions") != {"contents": "read"}:
        errors.append("examples/setup-actions.yml permissions must be exactly contents: read")
    for label, text in texts.items():
        if re.search(r"\$\{\{\s*secrets\.", text, re.IGNORECASE):
            errors.append(f"{label}: setup actions must not read secret contexts")
    return errors


setup_example = yaml.safe_load((ROOT / "examples/setup-actions.yml").read_text())
action_texts = {str(path.relative_to(ROOT)): path.read_text() for path in action_paths}
ERRORS.extend(setup_policy_errors(setup_example, action_texts))
mutated_example = dict(setup_example)
mutated_example["permissions"] = "write-all"
check(
    bool(setup_policy_errors(mutated_example, action_texts)),
    "setup policy negative probe did not reject widened permissions",
)
mutated_actions = dict(action_texts)
mutated_actions["actions/setup-python/action.yml"] += "\n${{ secrets.GITHUB_TOKEN }}\n"
check(
    any("secret contexts" in error for error in setup_policy_errors(setup_example, mutated_actions)),
    "setup policy negative probe did not reject secret context",
)

for path in sorted(ROOT.rglob("*.json")):
    if "templates/project/template" in path.as_posix():
        continue
    try:
        json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        ERRORS.append(f"{path.relative_to(ROOT)}: JSON: {exc}")
for path in sorted(ROOT.rglob("*.json5")):
    try:
        json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        ERRORS.append(f"{path.relative_to(ROOT)}: JSON5 subset: {exc}")

uses_re = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)
sha_re = re.compile(r"^[0-9a-f]{40}$")
for path in sorted([*ROOT.rglob("*.yml"), *ROOT.rglob("*.yaml")]):
    for use in uses_re.findall(path.read_text()):
        if use.startswith("./"):
            continue
        target, sep, ref = use.rpartition("@")
        check(bool(sep), f"{path.relative_to(ROOT)}: action without ref: {use}")
        is_toolkit_reference = target.startswith(
            "quokkify/project-toolkit/.github/workflows/"
        ) or target.startswith("quokkify/project-toolkit/actions/")
        if is_toolkit_reference:
            check(
                bool(re.fullmatch(r"v\d+\.\d+\.\d+", ref)),
                f"{path.relative_to(ROOT)}: toolkit action/workflow must use exact SemVer: {use}",
            )
        else:
            check(
                bool(sha_re.fullmatch(ref)),
                f"{path.relative_to(ROOT)}: external action is not SHA-pinned: {use}",
            )

link_re = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
for path in sorted(ROOT.rglob("*.md")):
    for link in link_re.findall(path.read_text()):
        if re.match(r"^(https?://|mailto:|#)", link):
            continue
        target = (path.parent / link.split("#", 1)[0]).resolve()
        check(
            target.exists() and (target == ROOT or ROOT in target.parents),
            f"{path.relative_to(ROOT)}: broken/escaping local link: {link}",
        )

poly = (ROOT / "examples/polyglot-ci.yml").read_text()
for job in ("python:", "node:", "java:", "integration:"):
    check(
        re.search(rf"^  {re.escape(job)}$", poly, re.MULTILINE) is not None,
        f"polyglot example missing independent {job[:-1]} job",
    )
check(
    "needs: [changes, python, node, java]" in poly,
    "polyglot integration job must depend on component checks",
)

docker = yaml.safe_load((ROOT / ".github/workflows/docker-build.yml").read_text())
on_key = next((k for k in docker if str(k).lower() in ("on", "true")), None)
call = docker[on_key]["workflow_call"]
check(call["inputs"]["push"]["default"] is False, "Docker push default must be false")
release = yaml.safe_load((ROOT / ".github/workflows/release-please.yml").read_text())
check(
    release.get("permissions") == {"contents": "write", "pull-requests": "write"},
    "Release workflow permissions must be exactly contents:write and pull-requests:write",
)
release_manifest = json.loads((ROOT / ".github/release-please/manifest.json").read_text())
check(
    not release_manifest_errors(release_manifest),
    "Release Please manifest must contain exactly one root package with a SemVer version",
)
for valid_manifest in ({".": "0.0.0"}, {".": "0.1.0"}, {".": "1.2.3-rc.1+build.5"}):
    check(
        not release_manifest_errors(valid_manifest),
        f"valid release manifest must be accepted: {valid_manifest}",
    )
for invalid_manifest in (
    {".": "01.0.0"},
    {".": "0.1"},
    {".": "1.0.0-01"},
    {".": 1},
    {".": "0.1.0", "extra": "0.1.0"},
):
    check(
        bool(release_manifest_errors(invalid_manifest)),
        f"invalid release manifest must be rejected: {invalid_manifest}",
    )
check(
    bool(release_manifest_errors({".": "0.0.0-0." + "--." * 10_000})),
    "pathological SemVer input must be rejected without regex backtracking",
)
release_config = json.loads((ROOT / ".github/release-please/config.json").read_text())
check(
    release_config.get("release-type") == "simple"
    and release_config.get("include-component-in-tag") is False
    and release_config.get("packages", {}).get(".", {}).get("package-name")
    == "project-toolkit",
    "Release Please config must preserve the simple project-toolkit SemVer contract",
)
ERRORS.extend(release_workflow_errors(ROOT / ".github/workflows/release.yml"))
ERRORS.extend(
    validate_toolkit_workflow_errors(ROOT / ".github/workflows/validate-toolkit.yml")
)
ERRORS.extend(
    validate_toolkit_workflow_negative_probes(ROOT / ".github/workflows/validate-toolkit.yml")
)
ERRORS.extend(
    reusable_runner_workflow_errors(ROOT / ".github/workflows/reusable-detect-runner.yml")
)
ERRORS.extend(codeql_runner_workflow_errors(ROOT / ".github/workflows/codeql.yml"))
for fixture in sorted((ROOT / "tests/fixtures/release-workflows").glob("invalid-*.yml")):
    check(
        bool(release_workflow_errors(fixture)),
        f"{fixture.relative_to(ROOT)} must fail release driver validation",
    )

secret_patterns = [
    r"ghp_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    "/ho" + r"me/[^/\s]+",
    r"BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY",
]
for path in sorted(p for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts):
    try:
        text = path.read_text()
    except UnicodeDecodeError:
        continue
    for pattern in secret_patterns:
        if re.search(pattern, text):
            ERRORS.append(f"{path.relative_to(ROOT)}: prohibited secret/personal-path pattern")

if ERRORS:
    print("\n".join("ERROR: " + e for e in ERRORS), file=sys.stderr)
    raise SystemExit(1)

copier = shutil.which("copier")
check(copier is not None, "copier executable is required")
actionlint = shutil.which("actionlint")
check(actionlint is not None, "actionlint executable is required")
if ERRORS:
    print("\n".join("ERROR: " + e for e in ERRORS), file=sys.stderr)
    raise SystemExit(1)
assert copier is not None and actionlint is not None
with tempfile.TemporaryDirectory(prefix="project-toolkit-validation-") as tmp:
    tmp_path = Path(tmp)
    template_source = shutil.copytree(
        ROOT,
        tmp_path / "template-source",
        ignore=shutil.ignore_patterns(
            ".git", ".worktrees", ".ruff_cache", ".venv", "__pycache__", "*.pyc", "build", "dist", "node_modules"
        ),
    )
    run(["git", "init", "-q"], template_source)
    run(["git", "config", "user.email", "fixture@example.invalid"], template_source)
    run(["git", "config", "user.name", "Fixture"], template_source)
    run(["git", "config", "commit.gpgsign", "false"], template_source)
    run(["git", "config", "core.hooksPath", "/dev/null"], template_source)
    run(["git", "add", "."], template_source)
    run(["git", "commit", "--no-verify", "-qm", "candidate template"], template_source)
    expected_scenario_presets = {
        "python": ["default", "github-actions", "python"],
        "node": ["default", "github-actions", "javascript"],
        "java": ["default", "github-actions", "java"],
        "polyglot": ["default", "github-actions", "python", "javascript", "java"],
        "docker": ["default", "github-actions", "python", "docker"],
    }
    for scenario, expected_presets in expected_scenario_presets.items():
        dest = tmp_path / scenario
        run(
            [
                copier,
                "copy",
                "--trust",
                "--defaults",
                "--vcs-ref",
                "HEAD",
                "--data-file",
                str(template_source / f"tests/scenarios/{scenario}.yml"),
                str(template_source),
                str(dest),
            ]
        )
        for workflow_name in ("validate.yml", "codeql.yml", "gitleaks.yml"):
            run([actionlint, str(dest / f".github/workflows/{workflow_name}")])
        check(
            (dest / ".copier-answers.yml").exists(),
            f"{scenario}: missing .copier-answers.yml",
        )
        assert_generated_renovate_config(
            dest / "renovate.json",
            renovate_extends("quokkify/renovate-presets", expected_presets),
            scenario,
        )
        if scenario == "polyglot":
            generated = (dest / ".github/workflows/validate.yml").read_text()
            for name in (
                "python-ci.yml",
                "node-ci.yml",
                "java-ci.yml",
            ):
                check(name in generated, f"polyglot generated workflow missing {name}")
            check(
                "docker-build.yml" not in generated,
                "polyglot generated workflow unexpectedly includes Docker",
            )
        if scenario == "python":
            run(["git", "init", "-q"], dest)
            run(["git", "config", "user.email", "fixture@example.invalid"], dest)
            run(["git", "config", "user.name", "Fixture"], dest)
            run(["git", "config", "commit.gpgsign", "false"], dest)
            run(["git", "config", "core.hooksPath", "/dev/null"], dest)
            run(["git", "add", "."], dest)
            run(["git", "commit", "--no-verify", "-qm", "fixture"], dest)
            run([copier, "update", "--trust", "--defaults"], dest)
            status = subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=dest, text=True
            )
            check(status == "", f"copier update was not idempotent: {status}")
            answers = yaml.safe_load((dest / ".copier-answers.yml").read_text())
            check(
                answers.get("renovate_config_repository")
                == "quokkify/renovate-presets",
                "copier update did not persist renovate_config_repository",
            )
            check(
                answers.get("renovate_presets") == ["default", "github-actions", "python"],
                "copier update did not persist inferred renovate_presets",
            )

    config_only_data = tmp_path / "config-only.yml"
    config_only_data.write_text(
        yaml.safe_dump(
            {
                "project_name": "fixture-config-only",
                "toolkit_version": "v1.0.0",
                "components": [],
                "docker": False,
                "release_please": True,
                "renovate": True,
                "renovate_config_repository": "quokkify/renovate-presets",
                "renovate_presets": ["default", "github-actions"],
            }
        )
    )
    config_only_dest = tmp_path / "config-only"
    run(
        [
            copier,
            "copy",
            "--trust",
            "--defaults",
            "--vcs-ref",
            "HEAD",
            "--data-file",
            str(config_only_data),
            str(template_source),
            str(config_only_dest),
        ]
    )
    check(
        (config_only_dest / ".github/workflows/validate.yml").exists(),
        "config-only project lost shared template-contract validation",
    )
    config_only_validate = (config_only_dest / ".github/workflows/validate.yml").read_text()
    for workflow_name in ("python-ci.yml", "node-ci.yml", "java-ci.yml", "docker-build.yml"):
        check(
            workflow_name not in config_only_validate,
            f"config-only project unexpectedly generated {workflow_name}",
        )
    for workflow_name in ("validate.yml", "codeql.yml", "gitleaks.yml"):
        run([actionlint, str(config_only_dest / f".github/workflows/{workflow_name}")])
    check(
        (config_only_dest / ".github/workflows/release.yml").exists(),
        "config-only project lost Release Please workflow",
    )
    assert_generated_renovate_config(
        config_only_dest / "renovate.json",
        renovate_extends("quokkify/renovate-presets", ["default", "github-actions"]),
        "config-only",
    )

    no_renovate_data = tmp_path / "no-renovate.yml"
    no_renovate_data.write_text(
        yaml.safe_dump(
            {
                "project_name": "fixture-no-renovate",
                "toolkit_version": "v1.0.0",
                "components": [{"type": "node", "path": "."}],
                "docker": False,
                "release_please": False,
                "renovate": False,
            }
        )
    )
    no_renovate_dest = tmp_path / "no-renovate"
    run(
        [
            copier,
            "copy",
            "--trust",
            "--defaults",
            "--vcs-ref",
            "HEAD",
            "--data-file",
            str(no_renovate_data),
            str(template_source),
            str(no_renovate_dest),
        ]
    )
    check(
        not (no_renovate_dest / "renovate.json").exists(),
        "renovate=false generated renovate.json",
    )

    custom_all_data = tmp_path / "custom-renovate-all.yml"
    custom_all_data.write_text(
        yaml.safe_dump(
            {
                "renovate_config_repository": "acme/shared-renovate",
                "renovate_presets": list(RENOVATE_PRESET_PATHS),
            }
        )
    )
    custom_dest = tmp_path / "custom-renovate-all"
    run(
        [
            copier,
            "copy",
            "--trust",
            "--defaults",
            "--vcs-ref",
            "HEAD",
            "--data-file",
            str(custom_all_data),
            str(template_source),
            str(custom_dest),
        ]
    )
    assert_generated_renovate_config(
        custom_dest / "renovate.json",
        renovate_extends("acme/shared-renovate", list(RENOVATE_PRESET_PATHS)),
        "custom-renovate-all",
    )

    dotted_repo_data = tmp_path / "custom-renovate-dotted-repo.yml"
    dotted_repo_data.write_text(
        yaml.safe_dump(
            {
                "renovate_config_repository": "octocat/octocat.github.io",
                "renovate_presets": ["default"],
            }
        )
    )
    dotted_repo_dest = tmp_path / "custom-renovate-dotted-repo"
    run(
        [
            copier,
            "copy",
            "--trust",
            "--defaults",
            "--vcs-ref",
            "HEAD",
            "--data-file",
            str(dotted_repo_data),
            str(template_source),
            str(dotted_repo_dest),
        ]
    )
    assert_generated_renovate_config(
        dotted_repo_dest / "renovate.json",
        renovate_extends("octocat/octocat.github.io", ["default"]),
        "custom-renovate-dotted-repo",
    )

    custom_selected_data = tmp_path / "custom-renovate-selected.yml"
    custom_selected_data.write_text(
        yaml.safe_dump(
            {
                "renovate_config_repository": "acme/shared-renovate",
                "renovate_presets": ["default", "javascript", "github-actions"],
            }
        )
    )
    custom_selected_dest = tmp_path / "custom-renovate-selected"
    run(
        [
            copier,
            "copy",
            "--trust",
            "--defaults",
            "--vcs-ref",
            "HEAD",
            "--data-file",
            str(custom_selected_data),
            str(template_source),
            str(custom_selected_dest),
        ]
    )
    assert_generated_renovate_config(
        custom_selected_dest / "renovate.json",
        renovate_extends("acme/shared-renovate", ["default", "javascript", "github-actions"]),
        "custom-renovate-selected",
    )

    for invalid_value in (
        "https://github.com/acme/shared-renovate",
        "github>acme/shared-renovate",
        "ac.me/shared-renovate",
        "acme/shared-renovate//presets/base",
        "acme/shared-renovate#main",
        "acme /shared-renovate",
        "acme/../shared-renovate",
        "{{ acme }}/shared-renovate",
    ):
        invalid_label = re.sub(r"[^A-Za-z0-9]+", "-", invalid_value).strip("-")
        bad_dest = tmp_path / ("invalid-renovate-" + invalid_label)
        result = subprocess.run(
            [
                copier,
                "copy",
                "--trust",
                "--defaults",
                "--vcs-ref",
                "HEAD",
                "--data",
                f"renovate_config_repository={invalid_value}",
                str(template_source),
                str(bad_dest),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        check(
            result.returncode != 0,
            f"invalid renovate_config_repository accepted: {invalid_value}",
        )

    invalid_preset_values: tuple[tuple[str, object], ...] = (
        ("unknown", ["default", "ruby"]),
        ("duplicate", ["default", "python", "python"]),
        ("empty", []),
        ("scalar-string", "default"),
        ("scalar-number", 1),
        ("map", {"default": True}),
    )
    for invalid_label, invalid_value in invalid_preset_values:
        invalid_data = tmp_path / f"invalid-renovate-presets-{invalid_label}.yml"
        invalid_data.write_text(yaml.safe_dump({"renovate_presets": invalid_value}))
        bad_dest = tmp_path / f"invalid-renovate-presets-{invalid_label}"
        result = subprocess.run(
            [
                copier,
                "copy",
                "--trust",
                "--defaults",
                "--vcs-ref",
                "HEAD",
                "--data-file",
                str(invalid_data),
                str(template_source),
                str(bad_dest),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        check(
            result.returncode != 0,
            f"invalid renovate_presets accepted: {invalid_label}={invalid_value!r}",
        )

run([sys.executable, "tests/test_composite_actions.py"])
run(["bash", "-n", "scripts/rollout_project_toolkit.sh"])

if not ARGS.static:
    fixture_commands = (
        ("Python", validate_python_fixture),
        ("Node.js", lambda: run(["node", "scripts/validate_node_fixture.mjs"])),
        ("Java", lambda: run(["bash", "scripts/validate_java_fixture.sh"])),
    )
    for language, validate_fixture in fixture_commands:
        try:
            validate_fixture()
        except (OSError, subprocess.CalledProcessError) as exc:
            ERRORS.append(f"{language} fixture validation failed: {exc}")
if ERRORS:
    print("\n".join("ERROR: " + e for e in ERRORS), file=sys.stderr)
    raise SystemExit(1)
print("static validation: OK" if ARGS.static else "validation: OK")
