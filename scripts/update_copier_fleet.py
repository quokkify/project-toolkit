#!/usr/bin/env python3
"""Update every Copier-managed repository in a GitHub organization.

The updater intentionally accepts only project-toolkit template sources. In
write mode it owns one deterministic branch per repository and creates or
refreshes a pull request. Dry-run mode performs the same Copier rendering
without pushing anything.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Sequence

import yaml

ANSWERS_FILE = ".copier-answers.yml"
DEFAULT_BRANCH = "automation/copier-template-update"
DEFAULT_TEMPLATE_REPOSITORY = "quokkify/project-toolkit"
PR_TITLE = "chore: update shared project template"


class FleetUpdateError(RuntimeError):
    """A repository or fleet operation could not be completed safely."""


class RepositoryProcessError(FleetUpdateError):
    """A managed repository failed after its inventory was collected."""

    def __init__(self, message: str, inventory: "TemplateInventory") -> None:
        super().__init__(message)
        self.inventory = inventory


@dataclass(frozen=True)
class Repository:
    name_with_owner: str
    default_branch: str


@dataclass(frozen=True)
class Result:
    repository: str
    status: str
    detail: str = ""
    inventory: "TemplateInventory | None" = None


@dataclass(frozen=True)
class TemplateInventory:
    commit: str
    target_commit: str | None
    components: tuple[str, ...]
    baseline: str
    missing_baseline: tuple[str, ...]
    docker: str
    release_please: str
    renovate: str


BASELINE_PATHS = (
    ".github/workflows/validate.yml",
    ".github/workflows/codeql.yml",
    ".github/workflows/gitleaks.yml",
)
FEATURE_PATHS = {
    "release_please": ".github/workflows/release.yml",
    "renovate": ".github/renovate.json",
}
FEATURE_LABELS = {
    "enabled": "on",
    "disabled": "off",
    "missing": "missing",
    "custom": "custom",
    "unknown": "unknown",
}
MARKDOWN_FEATURE_LABELS = {
    "enabled": "✅ On",
    "disabled": "— Off",
    "missing": "⚠️ Missing",
    "custom": "🛠️ Custom",
    "unknown": "❔ Unknown",
}


def is_regular_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def sanitize_text(value: str) -> str:
    return "".join(
        character if " " <= character != "\x7f" else f"\\x{ord(character):02x}"
        for character in value
    )


def run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and completed.returncode:
        rendered = " ".join(command)
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise FleetUpdateError(f"{rendered} failed ({completed.returncode}): {detail}")
    return completed


def gh_json(arguments: Sequence[str], *, env: dict[str, str]) -> Any:
    completed = run(["gh", *arguments], env=env)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise FleetUpdateError(f"gh returned invalid JSON for {' '.join(arguments)}") from exc


def discover_repositories(
    org: str,
    *,
    env: dict[str, str],
    public_only: bool = False,
) -> list[Repository]:
    arguments = [
        "repo",
        "list",
        org,
        "--limit",
        "1000",
        "--json",
        "nameWithOwner,defaultBranchRef,isArchived,isFork",
    ]
    if public_only:
        arguments.extend(["--visibility", "public"])
    items = gh_json(arguments, env=env)
    if len(items) >= 1000:
        raise FleetUpdateError(
            f"repository discovery reached the 1000-repository safety limit for {org}; "
            "refuse to run with a potentially truncated fleet"
        )
    repositories: list[Repository] = []
    for item in items:
        if item.get("isArchived") or item.get("isFork"):
            continue
        default_ref = item.get("defaultBranchRef")
        full_name = item.get("nameWithOwner")
        if isinstance(default_ref, dict) and isinstance(default_ref.get("name"), str) and isinstance(full_name, str):
            repositories.append(Repository(full_name, default_ref["name"]))
    return sorted(repositories, key=lambda repository: repository.name_with_owner.casefold())


def fetch_answers(repository: str, *, env: dict[str, str]) -> str | None:
    completed = run(
        [
            "gh",
            "api",
            f"repos/{repository}/contents/{ANSWERS_FILE}",
            "-H",
            "Accept: application/vnd.github.raw+json",
        ],
        env=env,
        check=False,
    )
    if completed.returncode == 0:
        return completed.stdout
    if "404" in completed.stderr or "Not Found" in completed.stderr:
        return None
    detail = completed.stderr.strip() or completed.stdout.strip()
    raise FleetUpdateError(f"cannot read {repository}/{ANSWERS_FILE}: {detail}")


def normalize_template_source(source: str) -> str | None:
    value = source.strip().removesuffix("/").removesuffix(".git")
    prefixes = (
        "gh:",
        "https://github.com/",
        "http://github.com/",
        "git@github.com:",
        "ssh://git@github.com/",
    )
    for prefix in prefixes:
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        owner, repository = value.split("/", 1)
        if owner not in {".", ".."} and repository not in {".", ".."}:
            return value.casefold()
    return None


def parse_answers(raw_answers: str) -> dict[str, Any]:
    try:
        answers = yaml.safe_load(raw_answers)
    except yaml.YAMLError as exc:
        raise FleetUpdateError(f"invalid {ANSWERS_FILE}: {exc}") from exc
    if not isinstance(answers, dict):
        raise FleetUpdateError(f"{ANSWERS_FILE} must contain a YAML mapping")
    return answers


def parse_template_source(raw_answers: str) -> str:
    answers = parse_answers(raw_answers)
    if not isinstance(answers.get("_src_path"), str):
        raise FleetUpdateError(f"{ANSWERS_FILE} does not contain a string _src_path")
    return answers["_src_path"]


def feature_state(answers: dict[str, Any], key: str, repository_path: Path) -> str:
    configured = answers.get(key)
    if not isinstance(configured, bool):
        return "unknown"
    expected_path = FEATURE_PATHS[key]
    present = is_regular_file(repository_path / expected_path)
    if configured:
        return "enabled" if present else "missing"
    return "custom" if present else "disabled"


def inventory_from_answers(raw_answers: str, repository_path: Path) -> TemplateInventory:
    answers = parse_answers(raw_answers)
    commit = answers.get("_commit")
    if not isinstance(commit, str) or not commit.strip():
        commit = "unknown"

    raw_components = answers.get("components")
    components: list[str] = []
    components_valid = True
    if isinstance(raw_components, list):
        for component in raw_components:
            if not isinstance(component, dict):
                components_valid = False
                break
            component_type = component.get("type")
            component_path = component.get("path")
            if not isinstance(component_type, str) or not isinstance(component_path, str):
                components_valid = False
                break
            components.append(f"{component_type}:{component_path}")
    else:
        components_valid = False
    if not components_valid:
        components = ["unknown"]
    elif not components:
        components = ["none"]

    missing_baseline = tuple(
        path for path in BASELINE_PATHS if not is_regular_file(repository_path / path)
    )
    present_baseline = len(BASELINE_PATHS) - len(missing_baseline)
    docker = answers.get("docker")
    docker_state = "enabled" if docker is True else "disabled" if docker is False else "unknown"
    return TemplateInventory(
        commit=commit.strip(),
        target_commit=None,
        components=tuple(components),
        baseline=f"{present_baseline}/{len(BASELINE_PATHS)}",
        missing_baseline=missing_baseline,
        docker=docker_state,
        release_please=feature_state(answers, "release_please", repository_path),
        renovate=feature_state(answers, "renovate", repository_path),
    )


def inventory_has_mismatch(inventory: TemplateInventory | None) -> bool:
    if inventory is None:
        return False
    return (
        inventory.baseline != f"{len(BASELINE_PATHS)}/{len(BASELINE_PATHS)}"
        or inventory.release_please == "missing"
        or inventory.renovate == "missing"
    )


def console_lines(result: Result) -> list[str]:
    suffix = f": {sanitize_text(result.detail)}" if result.detail else ""
    lines = [f"[{result.status}] {sanitize_text(result.repository)}{suffix}"]
    if result.inventory:
        inventory = result.inventory
        template_version = inventory.commit
        if inventory.target_commit and inventory.target_commit != inventory.commit:
            template_version += f"->{inventory.target_commit}"
        lines.append(
            "  "
            f"template={sanitize_text(template_version)} "
            f"components={sanitize_text(','.join(inventory.components))} "
            f"baseline={inventory.baseline} "
            f"docker={FEATURE_LABELS[inventory.docker]} "
            f"release-please={FEATURE_LABELS[inventory.release_please]} "
            f"renovate={FEATURE_LABELS[inventory.renovate]}"
        )
    return lines


def feature_summary(results: Sequence[Result]) -> tuple[str, str]:
    inventories = [result.inventory for result in results if result.inventory]
    denominator = len(inventories)
    enabled = {
        "docker": sum(inventory.docker == "enabled" for inventory in inventories),
        "release-please": sum(inventory.release_please == "enabled" for inventory in inventories),
        "renovate": sum(inventory.renovate == "enabled" for inventory in inventories),
    }
    component_counts: dict[str, int] = {}
    for inventory in inventories:
        seen = {
            sanitize_text(component.split(":", 1)[0])
            for component in inventory.components
            if component not in {"none", "unknown"}
        }
        for component_type in seen:
            component_counts[component_type] = component_counts.get(component_type, 0) + 1
    features = "features: " + ", ".join(
        f"{name}={count}/{denominator}" for name, count in enabled.items()
    )
    components = "components: " + (
        ", ".join(f"{name}={count}" for name, count in sorted(component_counts.items()))
        if component_counts
        else "none"
    )
    return features, components


def markdown_escape(value: str) -> str:
    return sanitize_text(value).replace("\\", "\\\\").replace("|", "\\|")


def markdown_report(results: Sequence[Result], counts: dict[str, int]) -> str:
    current = counts.get("up-to-date", 0)
    drift = counts.get("would-update", 0)
    excluded = counts.get("excluded", 0)
    mismatches = sum(inventory_has_mismatch(result.inventory) for result in results)
    lines = [
        "## Copier fleet audit",
        "",
        f"Fleet: {len(results)} repositories",
        "",
        f"✅ {current} up-to-date · 🟡 {drift} drift · ⚠️ {mismatches} configuration mismatch · ⏭️ {excluded} excluded",
        "",
        "| Repository | Sync | Template | Components | Baseline | Docker | Release Please | Renovate |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    status_labels = {
        "up-to-date": "✅ Current",
        "would-update": "🟡 Drift",
        "pull-request": "🔀 Pull request",
        "not-managed": "— Not managed",
        "foreign-template": "↗️ Foreign template",
        "excluded": "⏭️ Excluded",
        "failed": "❌ Failed",
    }
    for result in results:
        inventory = result.inventory
        if inventory:
            template_version = inventory.commit
            if inventory.target_commit and inventory.target_commit != inventory.commit:
                template_version += f" → {inventory.target_commit}"
            cells = (
                template_version,
                ", ".join(inventory.components),
                inventory.baseline,
                MARKDOWN_FEATURE_LABELS[inventory.docker],
                MARKDOWN_FEATURE_LABELS[inventory.release_please],
                MARKDOWN_FEATURE_LABELS[inventory.renovate],
            )
        else:
            cells = ("—", "—", "—", "—", "—", "—")
        lines.append(
            "| "
            + " | ".join(
                markdown_escape(value)
                for value in (
                    result.repository,
                    status_labels.get(result.status, result.status),
                    *cells,
                )
            )
            + " |"
        )

    problem_results = [
        result
        for result in results
        if result.status in {"would-update", "failed"} or inventory_has_mismatch(result.inventory)
    ]
    if problem_results:
        lines.extend(["", "### Details", ""])
        for result in problem_results:
            lines.append(f"#### `{markdown_escape(result.repository)}`")
            if result.detail:
                lines.append(f"- {markdown_escape(result.detail)}")
            inventory = result.inventory
            if inventory and inventory.baseline != f"{len(BASELINE_PATHS)}/{len(BASELINE_PATHS)}":
                lines.append(f"- Baseline files present: {inventory.baseline}")
                lines.extend(f"  - Missing: `{path}`" for path in inventory.missing_baseline)
            if inventory and inventory.release_please == "missing":
                lines.append(f"- Missing enabled template output: `{FEATURE_PATHS['release_please']}`")
            if inventory and inventory.renovate == "missing":
                lines.append(f"- Missing enabled template output: `{FEATURE_PATHS['renovate']}`")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def json_report(results: Sequence[Result], counts: dict[str, int]) -> str:
    repositories = []
    for result in results:
        item: dict[str, Any] = {
            "repository": result.repository,
            "status": result.status,
            "detail": result.detail,
        }
        if result.inventory:
            item["template"] = {
                "commit": result.inventory.commit,
                "target_commit": result.inventory.target_commit,
                "components": list(result.inventory.components),
                "baseline": {
                    "present": int(result.inventory.baseline.split("/", 1)[0]),
                    "expected": len(BASELINE_PATHS),
                    "missing": list(result.inventory.missing_baseline),
                },
                "docker": result.inventory.docker,
                "release_please": result.inventory.release_please,
                "renovate": result.inventory.renovate,
            }
        repositories.append(item)
    payload = {
        "schema_version": 1,
        "summary": counts,
        "configuration_mismatches": sum(inventory_has_mismatch(result.inventory) for result in results),
        "repositories": repositories,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def canonical_template_source(source: str) -> str:
    """Return a Copier and Renovate compatible HTTPS Git URL."""
    normalized = normalize_template_source(source)
    if normalized is None:
        raise FleetUpdateError(f"unsupported template source: {source}")
    return f"https://github.com/{normalized}.git"


def canonicalize_answers_source(repository_path: Path, expected_template: str) -> bool:
    """Replace Copier's GitHub shorthand without reserializing the answers file."""
    answers_path = repository_path / ANSWERS_FILE
    if answers_path.is_symlink():
        raise FleetUpdateError(f"{ANSWERS_FILE} must not be a symlink")
    content = answers_path.read_text(encoding="utf-8")
    current = parse_template_source(content)
    if normalize_template_source(current) != normalize_template_source(expected_template):
        raise FleetUpdateError(f"{ANSWERS_FILE} is managed by a different template")
    canonical = canonical_template_source(expected_template)
    if current == canonical:
        return False
    updated, substitutions = re.subn(
        r"^_src_path:.*$",
        f"_src_path: {canonical}",
        content,
        flags=re.MULTILINE,
    )
    if substitutions != 1:
        raise FleetUpdateError(f"{ANSWERS_FILE} must contain exactly one _src_path entry")
    answers_path.write_text(updated, encoding="utf-8")
    return True


def clone_repository(repository: Repository, destination: Path, *, env: dict[str, str]) -> None:
    run(
        [
            "gh",
            "repo",
            "clone",
            repository.name_with_owner,
            str(destination),
            "--",
            "--depth=1",
            f"--branch={repository.default_branch}",
            "--single-branch",
        ],
        env=env,
    )


def changed_paths(repository_path: Path) -> list[str]:
    output = run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=repository_path,
    ).stdout
    paths: list[str] = []
    entries = output.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        status = entry[:2]
        path = entry[3:]
        if status[0] in {"R", "C"}:
            if index >= len(entries) or not entries[index]:
                raise FleetUpdateError("git returned an incomplete rename/copy status entry")
            # In porcelain v1 -z output the destination is the first path and
            # the source follows as the extra NUL-delimited field.
            index += 1
        paths.append(path)
    return sorted(set(paths))


def restore_answers_format_if_semantically_equal(
    answers_path: Path,
    original_text: str,
) -> None:
    if answers_path.is_symlink():
        raise FleetUpdateError(f"{ANSWERS_FILE} must not be a symlink")
    if not answers_path.is_file():
        raise FleetUpdateError(f"{ANSWERS_FILE} must be a regular file")

    updated_text = answers_path.read_text(encoding="utf-8")
    original_answers = parse_answers(original_text)
    updated_answers = parse_answers(updated_text)
    if original_answers == updated_answers and original_text != updated_text:
        answers_path.write_text(original_text, encoding="utf-8")


def update_template(
    repository_path: Path,
    *,
    template_source: str,
    template_ref: str | None,
    env: dict[str, str],
) -> list[str]:
    answers_path = repository_path / ANSWERS_FILE
    if answers_path.is_symlink():
        raise FleetUpdateError(f"{ANSWERS_FILE} must not be a symlink")
    if not answers_path.is_file():
        raise FleetUpdateError(f"{ANSWERS_FILE} must be a regular file")
    original_answers_text = answers_path.read_text(encoding="utf-8")

    command = [
        "copier",
        "update",
        "--trust",
        "--defaults",
        "--conflict=rej",
        "--skip-tasks",
    ]
    if template_ref:
        command.extend(["--vcs-ref", template_ref])
    command.append(".")
    run(command, cwd=repository_path, env=env)
    restore_answers_format_if_semantically_equal(answers_path, original_answers_text)
    canonicalize_answers_source(repository_path, template_source)
    rejected = sorted(repository_path.rglob("*.rej"))
    if rejected:
        names = ", ".join(str(path.relative_to(repository_path)) for path in rejected)
        raise FleetUpdateError(f"Copier produced conflict files: {names}")
    return changed_paths(repository_path)


def push_automation_branch(
    repository: Repository,
    repository_path: Path,
    *,
    branch: str,
    env: dict[str, str],
) -> None:
    run(["git", "switch", "-C", branch], cwd=repository_path, env=env)
    run(["git", "config", "user.name", "quokkify-copier[bot]"], cwd=repository_path)
    run(
        ["git", "config", "user.email", "quokkify-copier[bot]@users.noreply.github.com"],
        cwd=repository_path,
    )
    run(["git", "add", "--all"], cwd=repository_path)
    run(["git", "diff", "--cached", "--check"], cwd=repository_path)
    run(["git", "commit", "-m", PR_TITLE], cwd=repository_path)

    remote = run(
        ["git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}"],
        cwd=repository_path,
        env=env,
    ).stdout.strip()
    push = ["git", "push"]
    if remote:
        remote_sha = remote.split()[0]
        push.append(f"--force-with-lease=refs/heads/{branch}:{remote_sha}")
    push.extend(["origin", f"HEAD:refs/heads/{branch}"])
    run(push, cwd=repository_path, env=env)


def ensure_pull_request(
    repository: Repository,
    *,
    branch: str,
    changed: Sequence[str],
    env: dict[str, str],
) -> str:
    existing = gh_json(
        [
            "pr",
            "list",
            "--repo",
            repository.name_with_owner,
            "--state",
            "open",
            "--head",
            branch,
            "--json",
            "url",
        ],
        env=env,
    )
    if existing:
        return existing[0]["url"]

    body = (
        "## Summary\n\n"
        "Automated `copier update` from the shared "
        "[`quokkify/project-toolkit`](https://github.com/quokkify/project-toolkit) template.\n\n"
        "This keeps the organization baseline (validation, CodeQL, Gitleaks, "
        "Release Please, and Renovate) synchronized while leaving merge approval to maintainers.\n\n"
        "## Generated changes\n\n"
        + "\n".join(f"- `{path}`" for path in changed)
        + "\n\n## Verification\n\n"
        "- `copier update --trust --defaults --conflict=rej --skip-tasks`\n"
        "- `git diff --cached --check`\n\n"
        "Do not edit the automation branch directly; make project-specific changes after merging "
        "or adjust the Copier answers/template.\n"
    )
    completed = run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            repository.name_with_owner,
            "--base",
            repository.default_branch,
            "--head",
            branch,
            "--title",
            PR_TITLE,
            "--body",
            body,
        ],
        env=env,
    )
    return completed.stdout.strip()


def process_repository(
    repository: Repository,
    *,
    expected_template: str,
    branch: str,
    dry_run: bool,
    template_ref: str | None,
    env: dict[str, str],
    workspace: Path,
) -> Result:
    raw_answers = fetch_answers(repository.name_with_owner, env=env)
    if raw_answers is None:
        return Result(repository.name_with_owner, "not-managed")

    source = normalize_template_source(parse_template_source(raw_answers))
    normalized_expected = normalize_template_source(expected_template)
    if normalized_expected is None or source != normalized_expected:
        return Result(repository.name_with_owner, "foreign-template", source or "unrecognized source")

    destination = workspace / repository.name_with_owner.replace("/", "--")
    clone_repository(repository, destination, env=env)
    cloned_answers_path = destination / ANSWERS_FILE
    if not is_regular_file(cloned_answers_path):
        raise FleetUpdateError(f"cloned {ANSWERS_FILE} must be a regular file")
    cloned_answers = cloned_answers_path.read_text(encoding="utf-8")
    cloned_source = normalize_template_source(parse_template_source(cloned_answers))
    if cloned_source != normalized_expected:
        raise FleetUpdateError("cloned repository changed to a different template during audit")
    inventory = inventory_from_answers(cloned_answers, destination)
    try:
        paths = update_template(
            destination,
            template_source=expected_template,
            template_ref=template_ref,
            env=env,
        )
        updated_answers_path = destination / ANSWERS_FILE
        if is_regular_file(updated_answers_path):
            updated_answers = parse_answers(updated_answers_path.read_text(encoding="utf-8"))
            updated_commit = updated_answers.get("_commit")
            if isinstance(updated_commit, str) and updated_commit.strip():
                inventory = replace(inventory, target_commit=updated_commit.strip())
        if not paths:
            return Result(repository.name_with_owner, "up-to-date", inventory=inventory)
        if dry_run:
            return Result(repository.name_with_owner, "would-update", ", ".join(paths), inventory)

        push_automation_branch(repository, destination, branch=branch, env=env)
        url = ensure_pull_request(repository, branch=branch, changed=paths, env=env)
        return Result(repository.name_with_owner, "pull-request", url, inventory)
    except Exception as exc:
        raise RepositoryProcessError(str(exc), inventory) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", default="quokkify")
    parser.add_argument("--template-repository", default=DEFAULT_TEMPLATE_REPOSITORY)
    parser.add_argument("--template-ref", help="Optional Copier VCS ref; scheduled runs normally use the latest release tag.")
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--markdown-report", type=Path, help="Write a Markdown fleet report to this path.")
    parser.add_argument("--json-report", type=Path, help="Write a machine-readable JSON fleet report to this path.")
    parser.add_argument("--repo", action="append", default=[], help="Process one owner/repository; repeatable.")
    parser.add_argument("--exclude", action="append", default=[], help="Skip one owner/repository; repeatable.")
    parser.add_argument(
        "--public-only",
        action="store_true",
        help="Limit organization discovery to the public fleet visible to repository-scoped Actions tokens.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    env = os.environ.copy()
    if args.write:
        if not env.get("GH_TOKEN", "").strip():
            print("GH_TOKEN is required in --write mode; use the CODEOWNER's short-lived local/API session", file=sys.stderr)
            return 2
        env["GH_TOKEN"] = env["GH_TOKEN"].strip()
    elif env.get("GITHUB_TOKEN", "").strip():
        env["GH_TOKEN"] = env["GITHUB_TOKEN"].strip()
    if not env.get("GH_TOKEN"):
        print("GH_TOKEN or GITHUB_TOKEN is required", file=sys.stderr)
        return 2
    for command in ("copier", "gh", "git"):
        if shutil.which(command, path=env.get("PATH")) is None:
            print(f"required command is unavailable: {command}", file=sys.stderr)
            return 2

    repositories: list[Repository] = []
    results: list[Result] = []
    failures = 0
    if args.repo:
        for requested_name in args.repo:
            normalized_name = normalize_template_source(requested_name)
            if normalized_name is None or requested_name.casefold() != normalized_name:
                result = Result(requested_name, "failed", "--repo must be exactly owner/repository")
                failures += 1
                results.append(result)
                continue
            try:
                metadata = gh_json(
                    [
                        "repo",
                        "view",
                        requested_name,
                        "--json",
                        "nameWithOwner,defaultBranchRef,isArchived,isFork",
                    ],
                    env=env,
                )
                default_ref = metadata.get("defaultBranchRef")
                full_name = metadata.get("nameWithOwner")
                if metadata.get("isArchived") or metadata.get("isFork"):
                    result = Result(requested_name, "excluded", "archived or fork")
                    results.append(result)
                    continue
                if (
                    not isinstance(full_name, str)
                    or not isinstance(default_ref, dict)
                    or not isinstance(default_ref.get("name"), str)
                ):
                    raise FleetUpdateError("repository metadata has no usable default branch")
                repositories.append(Repository(full_name, default_ref["name"]))
            except FleetUpdateError as exc:
                failures += 1
                result = Result(requested_name, "failed", str(exc))
                results.append(result)
    else:
        try:
            repositories = discover_repositories(
                args.org,
                env=env,
                public_only=args.public_only,
            )
        except FleetUpdateError as exc:
            print(f"fleet discovery failed: {exc}", file=sys.stderr)
            return 1

    excluded = {name.casefold() for name in args.exclude}
    with tempfile.TemporaryDirectory(prefix="copier-fleet-") as temporary:
        workspace = Path(temporary)
        for repository in repositories:
            if repository.name_with_owner.casefold() in excluded:
                results.append(Result(repository.name_with_owner, "excluded"))
                continue
            try:
                result = process_repository(
                    repository,
                    expected_template=args.template_repository,
                    branch=args.branch,
                    dry_run=args.dry_run,
                    template_ref=args.template_ref,
                    env=env,
                    workspace=workspace,
                )
            except RepositoryProcessError as exc:
                failures += 1
                result = Result(
                    repository.name_with_owner,
                    "failed",
                    str(exc),
                    exc.inventory,
                )
            except Exception as exc:  # continue the fleet, then fail the run loudly
                failures += 1
                result = Result(repository.name_with_owner, "failed", str(exc))
            results.append(result)

    for result in results:
        for line in console_lines(result):
            print(line, flush=True)
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    print("summary: " + ", ".join(f"{status}={count}" for status, count in sorted(counts.items())))
    for line in feature_summary(results):
        print(line)
    if args.markdown_report:
        args.markdown_report.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_report.write_text(markdown_report(results, counts), encoding="utf-8")
    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(json_report(results, counts), encoding="utf-8")
    if failures:
        return 1
    if args.dry_run and counts.get("would-update", 0):
        print("template drift detected; run write mode from a CODEOWNER session", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
