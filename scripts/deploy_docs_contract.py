from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

STANDALONE_VERSION = "0.1.0"
STANDALONE_SHA = "816d85aa756f480457befb42168633cb6ccf09c7"

_ACTION_PIN_RE = re.compile(
    r"quokkify/gh-pages-subdir-action@(?P<sha>[0-9a-f]{40})(?:\s*#\s*v(?P<version>\d+\.\d+\.\d+))?",
    re.IGNORECASE,
)

_SHA_RE = re.compile(r"[0-9a-f]{40}")
_VERSION_RE = re.compile(r"v(?P<version>\d+\.\d+\.\d+)")


@dataclass(frozen=True)
class StandaloneDelegationClaim:
    line_no: int
    line: str
    versions: set[str]
    shas: set[str]
    has_released_toolkit_source_state: bool


def parse_action_delegate(text: str) -> tuple[str, str | None] | None:
    """Return standalone action sha and optional version comment from the wrapper action."""
    match = _ACTION_PIN_RE.search(text)
    if not match:
        return None
    return match.group("sha"), match.group("version")


def parse_standalone_claims(text: str) -> list[StandaloneDelegationClaim]:
    """Extract standalone deployment delegation claim lines with version and SHA captures."""
    claims: list[StandaloneDelegationClaim] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        if "gh-pages-subdir-action" not in lowered:
            continue
        if "standalone" not in lowered and "delegates" not in lowered:
            continue
        versions = set(_VERSION_RE.findall(line))
        shas = set(_SHA_RE.findall(line))
        has_released = bool(re.search(r"\breleased\b.*\btoolkit\b", lowered))
        claims.append(
            StandaloneDelegationClaim(
                line_no=line_no,
                line=line.strip(),
                versions=versions,
                shas=shas,
                has_released_toolkit_source_state=has_released,
            )
        )
    return claims


def validate_deploy_docs_contract_file(
    path: Path,
    text: str,
    target_version: str = STANDALONE_VERSION,
    target_sha: str = STANDALONE_SHA,
) -> list[str]:
    """Validate file-local standalone delegation claims and return list of errors."""
    rel = path.as_posix()
    claims = parse_standalone_claims(text)
    if not claims:
        return [f"{rel}: missing standalone delegation claim to gh-pages-subdir-action"]

    errors: list[str] = []
    for claim in claims:
        if claim.has_released_toolkit_source_state:
            errors.append(
                f"{rel}: line {claim.line_no}: standalone claim uses released-toolkit source wording, expected source-state wording in this contract"
            )

        if claim.versions and target_version not in claim.versions:
            joined = ", ".join(sorted(claim.versions))
            errors.append(
                f"{rel}: line {claim.line_no}: standalone delegation references version(s) [{joined}], expected v{target_version}"
            )

        if claim.shas and target_sha not in claim.shas:
            joined = ", ".join(sorted(claim.shas))
            errors.append(
                f"{rel}: line {claim.line_no}: standalone delegation references SHA(s) [{joined}], expected {target_sha}"
            )

    return errors
