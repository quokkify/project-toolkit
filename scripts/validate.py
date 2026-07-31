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


def _release_workflow_errors(path: Path) -> list[str]:
    """Validate repository-level Release Please caller workflow contract."""

    errors: list[str] = []
    rel = path.relative_to(ROOT)

    def _check(condition: bool, message: str) -> None:
        if not condition:
            errors.append(f"{rel}: {message}")

    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        return [f"{rel}: YAML parse failed: {exc}"]

    if not isinstance(data, dict):
        return [f"{rel}: workflow root is not a mapping"]

    on_block = data.get("on")
    if on_block is None and True in data:
        on_block = data.get(True)
    _check(isinstance(on_block, dict), "missing or invalid 'on' block")
    if isinstance(on_block, dict):
        push = on_block.get("push")
        dispatch = "workflow_dispatch" in on_block
        _check(isinstance(push, dict), "missing or invalid push trigger")
        if isinstance(push, dict):
            branches = push.get("branches")
            _check(
                branches == ["main"],
                "push trigger must be limited to branches: [main]",
            )
        _check(dispatch, "missing workflow_dispatch trigger")

    permissions = data.get("permissions")
    _check(
        permissions == {"contents": "write", "pull-requests": "write"},
        "permissions must be exactly contents: write and pull-requests: write",
    )

    concurrency = data.get("concurrency")
    _check(isinstance(concurrency, dict), "missing or invalid concurrency block")
    if isinstance(concurrency, dict):
        _check(
            isinstance(concurrency.get("group"), str)
            and bool(concurrency.get("group")),
            "concurrency.group must be set",
        )
        _check(
            concurrency.get("cancel-in-progress") is False,
            "concurrency.cancel-in-progress must be false",
        )

    jobs = data.get("jobs")
    _check(isinstance(jobs, dict), "jobs block is missing")
    if not isinstance(jobs, dict):
        return errors

    reusable_jobs = [
        (name, job)
        for name, job in jobs.items()
        if isinstance(job, dict) and "uses" in job
    ]
    _check(len(reusable_jobs) == 1, "must define exactly one reusable workflow caller job")

    if not reusable_jobs:
        return errors

    name, job = reusable_jobs[0]
    _check(
        job.get("uses") == "./.github/workflows/release-please.yml",
        f"release job '{name}' must call ./.github/workflows/release-please.yml",
    )
    _check("steps" not in job, f"release job '{name}' must use a workflow_call job, not steps")
    with_block = job.get("with")
    _check(isinstance(with_block, dict), f"release job '{name}' missing with: block")
    if isinstance(with_block, dict):
        _check(with_block.get("mode") == "manifest", f"release job '{name}' must use mode: manifest")
        _check(
            with_block.get("config-file") == ".github/release-please/config.json",
            f"release job '{name}' must pass config-file: .github/release-please/config.json",
        )
        _check(
            with_block.get("manifest-file") == ".github/release-please/manifest.json",
            f"release job '{name}' must pass manifest-file: .github/release-please/manifest.json",
        )

    return errors


for path in sorted([*ROOT.rglob("*.yml"), *ROOT.rglob("*.yaml")]):
    if ".git" in path.parts or ".worktrees" in path.parts or "templates/project/template" in path.as_posix():
        continue
    try:
        yaml.safe_load(path.read_text())
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        ERRORS.append(f"{path.relative_to(ROOT)}: YAML: {exc}")


for action_path in sorted((ROOT / ".github/actions").glob("*/action.yml")):
    data = yaml.safe_load(action_path.read_text())
    check(bool(data), f"{action_path.relative_to(ROOT)}: action file is empty")
    if not data:
        continue
    check(data.get("runs", {}).get("using") == "composite",
          f"{action_path.relative_to(ROOT)}: action must use composite runner")
    check(
        data.get("runs", {}).get("steps") is not None,
        f"{action_path.relative_to(ROOT)}: action is missing runs.steps",
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
    if ".worktrees" in path.parts:
        continue
    for use in uses_re.findall(path.read_text()):
        if use.startswith("./"):
            continue
        target, sep, ref = use.rpartition("@")
        check(bool(sep), f"{path.relative_to(ROOT)}: action without ref: {use}")
        is_toolkit_reference = target.startswith(
            "ylazakovich/project-toolkit/.github/workflows/"
        ) or target.startswith("ylazakovich/project-toolkit/.github/actions/")
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
for err in _release_workflow_errors(ROOT / ".github/workflows/release.yml"):
    ERRORS.append(err)

for fixture in (
    ROOT / "tests/fixtures/release-workflows/invalid-permissions.yml",
    ROOT / "tests/fixtures/release-workflows/invalid-mode.yml",
    ROOT / "tests/fixtures/release-workflows/invalid-trigger.yml",
    ROOT / "tests/fixtures/release-workflows/invalid-call-shape.yml",
):
    check(bool(_release_workflow_errors(fixture)), f"fixture should fail validation: {fixture.relative_to(ROOT)}")

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
    template_source = tmp_path / "template-source"
    shutil.copytree(
        ROOT,
        template_source,
        ignore=shutil.ignore_patterns(
            ".git",
            ".worktrees",
            "build",
            "dist",
            ".pytest_cache",
            "project-toolkit-validation-*",
            "project-toolkit-fixtures-*",
        ),
    )
    for scenario in ("python", "node", "java", "polyglot"):
        dest = tmp_path / scenario
        run(
            [
                copier,
                "copy",
                "--trust",
                "--defaults",
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
            run(["git", "add", "."], dest)
            run(["git", "commit", "-qm", "fixture"], dest)
            status = subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=dest, text=True
            )
            check(status == "", f"copier update was not idempotent: {status}")

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
    for build_dir in (java / "build/classes", java / "build/test-classes"):
        if build_dir.exists():
            shutil.rmtree(build_dir)
        build_dir.mkdir(parents=True)
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
