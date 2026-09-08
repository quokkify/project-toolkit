"""Enrich Release Please Markdown from optional pull-request body sections.

This module deliberately has no GitHub or shell integration. The release workflow
can feed it the PRs Release Please selected, keeping selection/versioning owned by
Release Please while making the Markdown transformation deterministic and testable.
"""
from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

RICH_HEADINGS = {
    "release notes": "Release notes",
    "highlight": "Highlights",
    "usage example": "Usage Examples",
    "migration": "Migration",
    "breaking change": "Breaking Changes",
}
MARKER = "<!-- project-toolkit:rich-release-notes pr={number} -->"
_VERSION = re.compile(r"^##(?:\s+|\s*\[)(.+?)(?:\]|\s*)$", re.IGNORECASE)


def _without_comments(lines: Iterable[str]) -> str:
    text = "\n".join(lines).strip()
    # Comments are authoring guidance, not release content. Do not remove code
    # fences or HTML which may be intentional content in an example.
    text = re.sub(r"<!--[\s\S]*?-->", "", text)
    return text.strip()


def extract_rich_sections(body: str) -> dict[str, str]:
    """Extract supported level-2 sections from a PR body.

    Only exact ``## Heading`` lines are recognized. Unknown headings terminate a
    section, duplicate supported headings are ignored after the first, and all
    source lines are retained (including CRLF-normalized fence content).
    """
    result: dict[str, str] = {}
    current: str | None = None
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for line in lines:
        match = re.match(r"^##[ \t]+([^#].*?)[ \t]*$", line)
        if match:
            heading = match.group(1).strip().casefold()
            current = heading if heading in RICH_HEADINGS and heading not in result else None
            if current is not None:
                result[current] = ""
            continue
        if current is not None:
            result[current] += line + "\n"
    return {key: value.strip() for key, value in result.items() if _without_comments(value.splitlines())}


def _existing_pr_numbers(changelog: str) -> set[str]:
    return set(re.findall(r"project-toolkit:rich-release-notes pr=([0-9]+)", changelog))


def enrich_changelog(changelog: str, prs: Iterable[Mapping[str, object]]) -> str:
    """Insert rich content for selected PRs, once, immediately under the version.

    ``prs`` must already be the current Release Please range. The function does
    not query GitHub and therefore cannot accidentally include unrelated or old
    PRs. Entries are ordered by numeric PR number and stable section order.
    """
    prs = list(prs)
    existing = _existing_pr_numbers(changelog)
    titles = {str(pr.get("number", "")): str(pr.get("title", "")).strip() for pr in prs}
    entries: list[tuple[int, str, dict[str, str]]] = []
    for pr in prs:
        number = str(pr.get("number", "")).strip()
        if not number.isdigit() or number in existing:
            continue
        sections = extract_rich_sections(str(pr.get("body", "")))
        if sections:
            entries.append((int(number), number, sections))
    if not entries:
        return changelog
    entries.sort(key=lambda item: item[0])
    blocks: list[str] = []
    for _, number, sections in entries:
        blocks.append(MARKER.format(number=number))
        title = titles.get(number, "")
        if title:
            blocks.append(f"#### {title}")
        for key, heading in RICH_HEADINGS.items():
            if key in sections:
                blocks.extend((f"### {heading}", sections[key], ""))
    payload = "\n".join(blocks).rstrip() + "\n\n"
    version_match = re.search(r"^## .*$", changelog, re.MULTILINE)
    if not version_match:
        return changelog.rstrip() + "\n\n" + payload
    end = version_match.end()
    return changelog[:end] + "\n\n" + payload + changelog[end + 1 :]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changelog", type=Path, required=True)
    parser.add_argument("--pull-requests", type=Path, required=True, help="JSON array of selected Release Please PRs")
    args = parser.parse_args()
    prs = json.loads(args.pull_requests.read_text(encoding="utf-8"))
    updated = enrich_changelog(args.changelog.read_text(encoding="utf-8"), prs)
    args.changelog.write_text(updated, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
