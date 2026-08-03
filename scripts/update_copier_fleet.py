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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml

ANSWERS_FILE = ".copier-answers.yml"
DEFAULT_BRANCH = "automation/copier-template-update"
DEFAULT_TEMPLATE_REPOSITORY = "quokkify/project-toolkit"
PR_TITLE = "chore: update shared project template"


class FleetUpdateError(RuntimeError):
    """A repository or fleet operation could not be completed safely."""


@dataclass(frozen=True)
class Repository:
    name_with_owner: str
    default_branch: str


@dataclass(frozen=True)
class Result:
    repository: str
    status: str
    detail: str = ""


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


def discover_repositories(org: str, *, env: dict[str, str]) -> list[Repository]:
    items = gh_json(
        [
            "repo",
            "list",
            org,
            "--limit",
            "1000",
            "--json",
            "nameWithOwner,isArchived,isFork,defaultBranchRef",
        ],
        env=env,
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


def parse_template_source(raw_answers: str) -> str:
    try:
        answers = yaml.safe_load(raw_answers)
    except yaml.YAMLError as exc:
        raise FleetUpdateError(f"invalid {ANSWERS_FILE}: {exc}") from exc
    if not isinstance(answers, dict) or not isinstance(answers.get("_src_path"), str):
        raise FleetUpdateError(f"{ANSWERS_FILE} does not contain a string _src_path")
    return answers["_src_path"]


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


def update_template(
    repository_path: Path,
    *,
    template_ref: str | None,
    env: dict[str, str],
) -> list[str]:
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
    if source != expected_template.casefold():
        return Result(repository.name_with_owner, "foreign-template", source or "unrecognized source")

    destination = workspace / repository.name_with_owner.replace("/", "--")
    clone_repository(repository, destination, env=env)
    paths = update_template(destination, template_ref=template_ref, env=env)
    if not paths:
        return Result(repository.name_with_owner, "up-to-date")
    if dry_run:
        return Result(repository.name_with_owner, "would-update", ", ".join(paths))

    push_automation_branch(repository, destination, branch=branch, env=env)
    url = ensure_pull_request(repository, branch=branch, changed=paths, env=env)
    return Result(repository.name_with_owner, "pull-request", url)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", default="quokkify")
    parser.add_argument("--template-repository", default=DEFAULT_TEMPLATE_REPOSITORY)
    parser.add_argument("--template-ref", help="Optional Copier VCS ref; scheduled runs normally use the latest release tag.")
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--repo", action="append", default=[], help="Process one owner/repository; repeatable.")
    parser.add_argument("--exclude", action="append", default=[], help="Skip one owner/repository; repeatable.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--write", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    env = os.environ.copy()
    fleet_token = env.get("COPIER_FLEET_TOKEN", "").strip()
    if args.write and not fleet_token:
        print("COPIER_FLEET_TOKEN is required in --write mode", file=sys.stderr)
        return 2
    if fleet_token:
        env["GH_TOKEN"] = fleet_token
    elif not env.get("GH_TOKEN") and env.get("GITHUB_TOKEN"):
        env["GH_TOKEN"] = env["GITHUB_TOKEN"]
    if not env.get("GH_TOKEN"):
        print("GH_TOKEN, GITHUB_TOKEN, or COPIER_FLEET_TOKEN is required", file=sys.stderr)
        return 2
    for command in ("copier", "gh", "git"):
        if shutil.which(command, path=env.get("PATH")) is None:
            print(f"required command is unavailable: {command}", file=sys.stderr)
            return 2

    if args.repo:
        repositories = []
        for name in args.repo:
            metadata = gh_json(
                ["repo", "view", name, "--json", "nameWithOwner,defaultBranchRef,isArchived,isFork"],
                env=env,
            )
            if metadata.get("isArchived") or metadata.get("isFork"):
                continue
            repositories.append(
                Repository(metadata["nameWithOwner"], metadata["defaultBranchRef"]["name"])
            )
    else:
        repositories = discover_repositories(args.org, env=env)

    excluded = {name.casefold() for name in args.exclude}
    results: list[Result] = []
    failures = 0
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
            except Exception as exc:  # continue the fleet, then fail the run loudly
                failures += 1
                result = Result(repository.name_with_owner, "failed", str(exc))
            results.append(result)
            suffix = f": {result.detail}" if result.detail else ""
            print(f"[{result.status}] {result.repository}{suffix}", flush=True)

    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    print("summary: " + ", ".join(f"{status}={count}" for status, count in sorted(counts.items())))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
