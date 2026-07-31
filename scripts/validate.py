#!/usr/bin/env python3
"""Validate toolkit policy, templates, and executable language fixtures."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []


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
    "install-dependencies",
    "show-logs-on-failure",
    "wait-for-health",
}
EXPECTED_ACTIONS = {"compose-up", "setup-java-gradle", "setup-node", "setup-python"}


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
    "actions/: expected exactly the four documented pilot composite actions",
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
            "ylazakovich/project-toolkit/.github/workflows/"
        ) or target.startswith("ylazakovich/project-toolkit/actions/")
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
            ERRORS.append(
                f"{path.relative_to(ROOT)}: prohibited secret/personal-path pattern: {pattern}"
            )

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
    for scenario in ("python", "node", "java", "polyglot"):
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
        run([actionlint, str(dest / ".github/workflows/ci.yml")])
        check(
            (dest / ".copier-answers.yml").exists(),
            f"{scenario}: missing .copier-answers.yml",
        )
        if scenario == "node":
            check(
                not (dest / "renovate.json").exists(),
                "node scenario disabled Renovate but generated renovate.json",
            )
        if scenario == "polyglot":
            generated = (dest / ".github/workflows/ci.yml").read_text()
            for name in (
                "python-ci.yml",
                "node-ci.yml",
                "java-ci.yml",
                "docker-build.yml",
            ):
                check(name in generated, f"polyglot generated workflow missing {name}")
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

run([sys.executable, "tests/test_composite_actions.py"])

with tempfile.TemporaryDirectory(prefix="project-toolkit-fixtures-") as tmp:
    fixtures = Path(tmp)
    python = shutil.copytree(ROOT / "tests/fixtures/python", fixtures / "python")
    node = shutil.copytree(ROOT / "tests/fixtures/node", fixtures / "node")
    java = shutil.copytree(ROOT / "tests/fixtures/java", fixtures / "java")
    run([sys.executable, "-m", "compileall", "-q", "src"], python)
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], python)
    (python / "dist").mkdir()
    run(
        [sys.executable, "-m", "zipapp", "src", "-o", "dist/app.pyz", "-m", "app:main"],
        python,
    )
    run(["npm", "run", "lint"], node)
    run(["npm", "test"], node)
    run(["npm", "run", "build"], node)
    (java / "build/classes").mkdir(parents=True)
    (java / "build/test-classes").mkdir(parents=True)
    run(["javac", "-Xlint:all", "-d", "build/classes", "src/toolkit/App.java"], java)
    run(
        [
            "javac",
            "-Xlint:all",
            "-cp",
            "build/classes",
            "-d",
            "build/test-classes",
            "test/toolkit/AppTest.java",
        ],
        java,
    )
    run(["java", "-cp", "build/classes:build/test-classes", "toolkit.AppTest"], java)
    run(
        [
            "jar",
            "--create",
            "--file",
            "build/toolkit-java-fixture.jar",
            "-C",
            "build/classes",
            ".",
        ],
        java,
    )
    run(["mvn", "--batch-mode", "--no-transfer-progress", "test"], java)
if ERRORS:
    print("\n".join("ERROR: " + e for e in ERRORS), file=sys.stderr)
    raise SystemExit(1)
print("validation: OK")
