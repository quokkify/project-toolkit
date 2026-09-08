"""Deterministically enrich Release Please output from selected PR bodies."""
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
BLOCK_START = "<!-- project-toolkit:rich-block:start -->"
BLOCK_END = "<!-- project-toolkit:rich-block:end -->"


def _without_comments(lines: Iterable[str]) -> str:
    text = "\n".join(lines).strip()
    return re.sub(r"<!--[\s\S]*?-->", "", text).strip()


def extract_rich_sections(body: str) -> dict[str, str]:
    """Extract supported level-2 sections, retaining Markdown and fences."""
    result: dict[str, str] = {}
    current: str | None = None
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    fence: str | None = None
    for line in lines:
        fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence_match:
            marker = fence_match.group(1)
            if fence is None:
                fence = marker[0]
            elif marker[0] == fence:
                fence = None
            if current is not None:
                result[current] += line + "\n"
            continue
        if fence is not None:
            if current is not None:
                result[current] += line + "\n"
            continue
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


def _version_ranges(changelog: str) -> list[tuple[int, int]]:
    lines = changelog.splitlines(keepends=True)
    offsets: list[int] = []
    offset = 0
    fence: str | None = None
    for line in lines:
        fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence_match:
            marker = fence_match.group(1)
            if fence is None:
                fence = marker[0]
            elif marker[0] == fence:
                fence = None
        elif fence is None and re.match(r"^##[ \t]+.*$", line):
            offsets.append(offset)
        offset += len(line)
    matches = offsets
    return [(start, matches[i + 1] if i + 1 < len(matches) else len(changelog)) for i, start in enumerate(matches)]


def _rich_numbers(text: str) -> set[str]:
    return set(re.findall(r"project-toolkit:rich-release-notes pr=([0-9]+)", text))


def _remove_legacy_block(top: str) -> str:
    """Remove marker-only notes without treating fenced headings as boundaries."""
    output: list[str] = []
    removing = False
    fence: str | None = None
    for line in top.splitlines(keepends=True):
        fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence_match:
            token = fence_match.group(1)[0]
            if fence is None:
                fence = token
            elif token == fence:
                fence = None
            if not removing:
                output.append(line)
            continue
        if fence is None and re.match(r"^<!-- project-toolkit:rich-release-notes pr=\d+ -->\s*$", line):
            removing = True
            continue
        if removing and fence is None:
            heading = re.match(r"^###\s+(.+?)\s*$", line)
            if heading and heading.group(1).strip().casefold() not in {value.casefold() for value in RICH_HEADINGS.values()}:
                removing = False
            elif re.match(r"^##[ \t]+", line):
                removing = False
        if not removing:
            output.append(line)
    return "".join(output)


def _render_entries(prs: Iterable[Mapping[str, object]], excluded: set[str]) -> str:
    entries: list[tuple[int, str, dict[str, str]]] = []
    for pr in prs:
        number = str(pr.get("number", "")).strip()
        if not number.isdigit() or number in excluded:
            continue
        sections = extract_rich_sections(str(pr.get("body", "")))
        if sections:
            entries.append((int(number), number, sections))
    entries.sort(key=lambda item: item[0])
    blocks: list[str] = []
    for _, number, sections in entries:
        blocks.append(MARKER.format(number=number))
        title = str(next((p.get("title", "") for p in prs if str(p.get("number", "")).strip() == number), "")).strip()
        if title:
            blocks.append(f"#### {title}")
        for key, heading in RICH_HEADINGS.items():
            if key in sections:
                blocks.extend((f"### {heading}", sections[key], ""))
    return "\n".join(blocks).rstrip()


def enrich_changelog(changelog: str, prs: Iterable[Mapping[str, object]]) -> str:
    """Rebuild only the top-version rich block; older releases are immutable."""
    prs = list(prs)
    ranges = _version_ranges(changelog)
    if not ranges:
        return changelog
    start, end = ranges[0]
    top = changelog[start:end]
    older_numbers = _rich_numbers(changelog[end:])
    had_block = BLOCK_START in top
    top = re.sub(r"\n?<!-- project-toolkit:rich-block:start -->[\s\S]*?<!-- project-toolkit:rich-block:end -->\n?", "", top)
    # Compatibility with the original marker-only implementation.
    if not had_block:
        top = _remove_legacy_block(top)
    payload = _render_entries(prs, older_numbers)
    if payload:
        heading_end = top.find("\n")
        if heading_end < 0:
            heading_end = len(top)
        prefix = top[:heading_end].rstrip()
        suffix = top[heading_end:].lstrip("\n")
        top = prefix + "\n\n" + BLOCK_START + "\n" + payload + "\n" + BLOCK_END + "\n\n" + suffix
    return changelog[:start] + top + changelog[end:]


def enrich_release_body(body: str, rich_markdown: str) -> str:
    """Replace this tool's body block while preserving all Release Please text."""
    block = f"{BLOCK_START}\n{rich_markdown}\n{BLOCK_END}" if rich_markdown else ""
    pattern = rf"{re.escape(BLOCK_START)}[\s\S]*?{re.escape(BLOCK_END)}"
    if re.search(pattern, body):
        return re.sub(pattern, block, body)
    return body.rstrip() + ("\n\n" + block if block else "") + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changelog", type=Path, required=True)
    parser.add_argument("--pull-requests", type=Path, required=True, help="JSON array selected by Release Please")
    parser.add_argument("--release-body", type=Path)
    parser.add_argument("--rich-body", type=Path)
    args = parser.parse_args()
    prs = json.loads(args.pull_requests.read_text(encoding="utf-8"))
    original = args.changelog.read_text(encoding="utf-8")
    updated = enrich_changelog(original, prs)
    args.changelog.write_text(updated, encoding="utf-8", newline="\n")
    if args.release_body and args.rich_body:
        top = _version_ranges(updated)
        rich = _render_entries(prs, _rich_numbers(updated[top[0][1]:]) if top else set())
        args.rich_body.write_text(enrich_release_body(args.release_body.read_text(encoding="utf-8"), rich), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
