# project-toolkit

A small, versioned toolkit for composing consistent GitHub automation across Python, Node.js, Java, Docker, and polyglot repositories—without Git submodules.

- **Reusable workflows** own complete jobs and runner behavior.
- **Composite actions** provide reusable setup/runtime and JUnit reporting primitives for Python, Node.js, Java/Gradle, and Compose-based checks.
- **Copier** creates and later updates small physical files in a consumer repository.
- **Renovate** proposes version updates; **Release Please** prepares changelogs and releases.

## Quick start

The exact `v1.0.0` references below are the intended first-release production contract. They become runnable only after the owner publishes that immutable tag; this task intentionally does not create it.

```yaml
name: CI
on: [pull_request]
permissions:
  contents: read
jobs:
  python:
    uses: quokkify/project-toolkit/.github/workflows/python-ci.yml@v1.0.0
    with:
      python-version: "3.12"
      test-command: pytest
```

Use the independent [`Python`](examples/python-ci.yml), [`Node.js`](examples/node-ci.yml), and [`Java`](examples/java-ci.yml) examples, or compose all three with path filters in the [`polyglot example`](examples/polyglot-ci.yml). Docker builds do not push by default. For action-level usage, see [`examples/setup-actions.yml`](examples/setup-actions.yml).

## Documentation

- [Architecture and researched constraints](docs/architecture.md)
- [Usage, Copier, Release Please, and Renovate](docs/usage.md)
- [Versioning](docs/versioning.md)
- [Security model](docs/security.md)
- [Contributing](CONTRIBUTING.md)

The root [`copier.yml`](copier.yml) points at `templates/project/template/`. Keeping the Copier entry point at the Git root is required for reliable VCS-aware `copier update` operations.

Submodules are intentionally absent: consumers need a stable job API and upgrade PRs, not a second Git history embedded in every project. Production references use exact released versions, never `@main`. Update generated project files with `copier update`; update workflow versions through Renovate or a reviewed manual change.

Copier-generated `renovate.json` files extend presets from the central shared repository `ylazakovich/renovate-config` by default. Set the `renovate_config_repository` answer to another GitHub `owner/repo` slug to use a different shared preset repository; this answer names the preset repository, not the generated consumer repository. The `renovate_presets` YAML list selects preset names in order: `default` -> `presets/base`, `python` -> `presets/python/default`, `javascript` -> `presets/npm/default`, `java` -> `presets/gradle/default`, `docker` -> `presets/docker/default`, and `github-actions` -> `presets/github-actions/default`. New projects infer `default` plus language and Docker presets from Copier answers, while `github-actions` remains explicit opt-in. Generated extends intentionally follow the preset repository's default branch; projects with stricter stability requirements can manually pin entries later.

## Scope

The toolkit does not deploy to providers, publish language packages, hide project secrets, or generate arbitrary jobs. Validation is static and fixture-based until reusable workflows are available on an accessible Git ref; see the documented limitation in [architecture](docs/architecture.md).

Toolkit composite actions are maintained under `actions/` (setup steps plus Compose readiness) and can be consumed directly by downstream projects. They are independent building blocks for caller-owned jobs; reusable workflows keep their self-contained job implementations so cross-repository calls do not depend on a caller checkout containing toolkit-local actions.
