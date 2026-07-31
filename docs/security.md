# Security

## Action pinning

Every third-party Action used by the toolkit is pinned to a full commit SHA with a nearby human-readable release comment. Renovate tracks and updates those pins. Consumer examples pin this toolkit to exact immutable SemVer release tags; `@main` is mutable and unsafe for production because an unrelated push changes executed code.

An exact release tag is immutable by project policy but Git itself permits tag deletion/recreation; a full commit SHA is cryptographically stronger. A mutable major alias such as `v1` intentionally moves and trades stronger immutability for easier updates.

## Permissions and secrets

Language and Docker workflows request only `contents: read`. Release Please needs `contents: write` and `pull-requests: write`. Docker login is skipped unless `push: true`; a caller pushing to GitHub Packages must explicitly grant `packages: write`, because the called workflow cannot elevate the caller token.

Only Docker push accepts secrets (`registry-username` and `registry-password`). They are passed directly to the pinned login Action and are never echoed. Build arguments are not secret-safe. Reusable workflows cannot elevate permissions granted by their caller, and secrets are not automatically forwarded through nested workflows unless explicitly passed or inherited.

## Fork pull requests

GitHub normally withholds repository secrets from workflows triggered by untrusted fork pull requests. Keep PR validation read-only, do not use `pull_request_target` to execute fork code with write tokens, and keep push/release paths on trusted branch events.

## Private workflow repositories

A private reusable workflow works only when the owner/organization grants the caller repository Actions access. The caller receives a scoped token to download workflow code, and outside collaborators may indirectly view logs containing workflow output. Cross-owner and organization policy restrictions apply; public toolkit workflows avoid most access-policy friction but remain supply-chain code and must be pinned.
