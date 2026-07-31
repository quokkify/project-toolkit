# project-toolkit

A small, versioned toolkit for composing consistent GitHub automation across Python, Node.js, Java, Docker, and polyglot repositories—without Git submodules.

- **Reusable workflows** own complete jobs and runner behavior.
- **Composite actions** would own repeated step sequences; none are justified in the MVP.
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
    uses: ylazakovich/project-toolkit/.github/workflows/python-ci.yml@v1.0.0
    with:
      python-version: "3.12"
      test-command: pytest
```

Use the independent [`Python`](examples/python-ci.yml), [`Node.js`](examples/node-ci.yml), and [`Java`](examples/java-ci.yml) examples, or compose all three with path filters in the [`polyglot example`](examples/polyglot-ci.yml). Docker builds do not push by default.

## Documentation

- [Architecture and researched constraints](docs/architecture.md)
- [Usage, Copier, Release Please, and Renovate](docs/usage.md)
- [Versioning](docs/versioning.md)
- [Security model](docs/security.md)
- [Contributing](CONTRIBUTING.md)

The root [`copier.yml`](copier.yml) points at `templates/project/template/`. Keeping the Copier entry point at the Git root is required for reliable VCS-aware `copier update` operations.

Submodules are intentionally absent: consumers need a stable job API and upgrade PRs, not a second Git history embedded in every project. Production references use exact released versions, never `@main`. Update generated project files with `copier update`; update workflow versions through Renovate or a reviewed manual change.

## Scope

The MVP does not deploy to providers, publish language packages, hide project secrets, generate arbitrary jobs, or replace setup Actions, Renovate, or Release Please. Validation is static and fixture-based until reusable workflows are available on an accessible Git ref; see the documented limitation in [architecture](docs/architecture.md).
