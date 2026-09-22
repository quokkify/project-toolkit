#!/usr/bin/env python3
"""Safely reconcile one managed GitHub repository ruleset.

The command is deliberately separate from Copier generation. It defaults to
``evaluate`` and never changes GitHub in dry-run/evaluate mode.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ReconcileError(RuntimeError):
    """A safe, actionable reconciliation failure."""


@dataclass
class GitHubClient:
    token: str
    api_base: str = "https://api.github.com"

    def request(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> Any:
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            self.api_base.rstrip("/") + path,
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                **({"Content-Type": "application/json"} if body else {}),
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ReconcileError(f"GitHub API {method} {path} failed: {exc}") from exc
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ReconcileError(f"GitHub API {method} {path} returned malformed JSON") from exc


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReconcileError(f"GitHub API returned malformed {label}: expected an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ReconcileError(f"GitHub API returned malformed {label}: expected a list")
    return value


def managed_name(owner: str, repo: str) -> str:
    return f"project-toolkit/security/{owner}/{repo}"


def build_desired(name: str, branch: str, checks: list[str], mode: str, codeql_threshold: int | None) -> dict[str, Any]:
    if not name or not branch or not checks or any(not item.strip() for item in checks):
        raise ReconcileError("ruleset name, branch, and at least one non-empty check are required")
    rules: list[dict[str, Any]] = [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {
            "type": "pull_request",
            "parameters": {
                "required_approving_review_count": 1,
                "dismiss_stale_reviews_on_push": True,
                "require_code_owner_review": False,
                "require_last_push_approval": True,
            },
        },
        {
            "type": "required_status_checks",
            "parameters": {
                "required_status_checks": [{"context": check} for check in sorted(set(checks))],
                "strict_required_status_checks_policy": True,
            },
        },
    ]
    if codeql_threshold is not None:
        if codeql_threshold < 0:
            raise ReconcileError("--codeql-alert-threshold must be non-negative")
        rules.append({
            "type": "required_code_scanning",
            "parameters": {
                "code_scanning_tools": [{
                    "tool": "CodeQL",
                    "alerts_threshold": codeql_threshold,
                    "security_alerts_threshold": codeql_threshold,
                }]
            },
        })
    return {
        "name": name,
        "target": "branch",
        "enforcement": mode,
        "conditions": {"ref_name": {"include": [branch], "exclude": []}},
        "rules": rules,
    }


def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _normalize(value[key]) for key in sorted(value) if key not in {"id", "node_id", "created_at", "updated_at", "etag"}}
    if isinstance(value, list):
        return sorted((_normalize(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    return value


def _rule_types(rules: list[Any]) -> set[str]:
    types: set[str] = set()
    for rule in rules:
        mapping = _require_mapping(rule, "ruleset rule")
        rule_type = mapping.get("type")
        if not isinstance(rule_type, str):
            raise ReconcileError("GitHub API returned a ruleset rule without a string type")
        types.add(rule_type)
    return types


def _find_existing(rulesets: list[Any], name: str) -> Mapping[str, Any] | None:
    matches = []
    for item in rulesets:
        mapping = _require_mapping(item, "ruleset")
        if mapping.get("name") == name:
            matches.append(mapping)
    if len(matches) > 1:
        raise ReconcileError(f"multiple managed rulesets named {name!r}; refusing to choose one")
    return matches[0] if matches else None


def check_contexts(client: GitHubClient, repo: str, revision: str) -> set[str]:
    data = _require_mapping(client.request("GET", f"/repos/{repo}/commits/{revision}/check-runs?per_page=100"), "check-runs response")
    runs = _require_list(data.get("check_runs"), "check_runs")
    contexts: set[str] = {
        run["name"] for run in runs
        if isinstance(run, Mapping) and isinstance(run.get("name"), str)
    }
    statuses = _require_list(client.request("GET", f"/repos/{repo}/commits/{revision}/statuses?per_page=100"), "statuses response")
    contexts.update(
        status["context"] for status in statuses
        if isinstance(status, Mapping) and isinstance(status.get("context"), str)
    )
    return contexts


def reconcile(client: GitHubClient, repo: str, branch: str, checks: list[str], revision: str | None, mode: str, dry_run: bool, codeql_threshold: int | None = None) -> dict[str, Any]:
    owner, _, repository = repo.partition("/")
    if not owner or not repository or repo.count("/") != 1:
        raise ReconcileError("--repo must be OWNER/REPOSITORY")
    name = managed_name(owner, repository)
    desired = build_desired(name, branch, checks, mode, codeql_threshold)
    if revision:
        published = check_contexts(client, repo, revision)
        missing = sorted(set(checks) - published)
        if missing:
            raise ReconcileError(f"required check context(s) not published for {revision}: {', '.join(missing)}; refusing mutation")
    rulesets = _require_list(client.request("GET", f"/repos/{repo}/rulesets?includes_parents=true"), "rulesets response")
    existing = _find_existing(rulesets, name)
    action = "create" if existing is None else "update"
    if existing is not None:
        existing_rules = _require_list(existing.get("rules"), "managed rules")
        desired_types = _rule_types(desired["rules"])
        # Preserve policy owned by an operator inside the managed ruleset, while
        # replacing only the rule types controlled by this command.
        desired["rules"] = desired["rules"] + [rule for rule in existing_rules if isinstance(rule, Mapping) and rule.get("type") not in desired_types]
    result: dict[str, Any] = {"action": action, "mode": mode, "dry_run": dry_run, "name": name, "desired": desired}
    if dry_run or mode == "evaluate":
        result["actual"] = existing
        result["matches"] = existing is not None and _normalize(existing) == _normalize(desired)
        return result
    identifier = existing.get("id") if existing else None
    if existing is not None and not isinstance(identifier, int):
        raise ReconcileError("managed ruleset response has no numeric id; refusing update")
    path = f"/repos/{repo}/rulesets/{identifier}" if identifier is not None else f"/repos/{repo}/rulesets"
    actual = client.request("PUT" if identifier is not None else "POST", path, desired)
    actual_mapping = _require_mapping(actual, "ruleset mutation response")
    readback_id = actual_mapping.get("id")
    if not isinstance(readback_id, int):
        raise ReconcileError("ruleset mutation response has no numeric id")
    readback = _require_mapping(client.request("GET", f"/repos/{repo}/rulesets/{readback_id}"), "ruleset readback")
    if _normalize(readback) != _normalize(desired):
        raise ReconcileError("ruleset readback mismatch; refusing to report success")
    result["actual"] = readback
    result["matches"] = True
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--repo", required=True, help="GitHub repository OWNER/REPOSITORY")
    command.add_argument("--branch", default="main")
    command.add_argument("--check", action="append", required=True, dest="checks", help="Exact published check context; repeatable")
    command.add_argument("--revision", help="Commit SHA used to preflight published check contexts")
    command.add_argument("--mode", choices=("evaluate", "active"), default="evaluate")
    command.add_argument("--active", action="store_true", help="Explicitly promote the managed ruleset to active")
    command.add_argument("--dry-run", action="store_true")
    command.add_argument("--codeql-alert-threshold", type=int)
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    mode = "active" if args.active else args.mode
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ReconcileError("set GH_TOKEN or GITHUB_TOKEN; credentials are never accepted as CLI arguments")
    try:
        output = reconcile(GitHubClient(token), args.repo, args.branch, args.checks, args.revision, mode, args.dry_run, args.codeql_alert_threshold)
    except ReconcileError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
