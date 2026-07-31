# Usage

The examples intentionally target the planned immutable `v1.0.0` release. They are production-shaped but cannot run until the owner separately approves and publishes that tag.

Copy a small caller workflow from [`examples/`](../examples/) and replace commands/paths. Production callers use an exact released tag:

```yaml
jobs:
  backend:
    uses: ylazakovich/project-toolkit/.github/workflows/python-ci.yml@v1.0.0
    with:
      working-directory: backend
      install-command: python -m pip install -e .[test]
      lint-command: ruff check .
      test-command: pytest
```

A polyglot repository calls Python, Node.js, and Java workflows as separate jobs. See [`examples/polyglot-ci.yml`](../examples/polyglot-ci.yml) for path filtering and an integration job that treats unrelated skipped checks as acceptable but requires every selected component check to succeed.

## Reusable composite actions

Toolkit consumers can call composite actions directly for repeated setup and compose orchestration:

- `actions/setup-python/action.yml`
- `actions/setup-node/action.yml`
- `actions/setup-java-gradle/action.yml`
- `actions/compose-up/action.yml`

Use examples in [`examples/setup-actions.yml`](../examples/setup-actions.yml). The action inputs are versioned and can be called with their defaults where repository conventions already match the toolkit assumptions. Custom install commands are trusted caller configuration and must never interpolate untrusted pull-request data.

The Python and Node actions install dependencies by default; set `install-dependencies: "false"` when only the language runtime and cache are needed. The Java/Gradle action prepares Java, Gradle caches, and a workspace-relative wrapper command; callers run their own Gradle dependency/build command. `compose-up` is Linux-only, accepts newline-separated `compose-files` and `wait-urls`, and supports explicit `completed-services` for successful one-shot containers. It requires no write permissions by itself. Callers remain responsible for granting only the permissions required by their surrounding job and for running `docker compose down` during normal cleanup when needed.

## Docker secrets

Docker push is off by default. When `push: true`, pass both declared secrets explicitly:

```yaml
secrets:
  registry-username: ${{ github.actor }}
  registry-password: ${{ secrets.GITHUB_TOKEN }}
```

The caller must grant `packages: write` when its registry requires it. Never pass secrets via `build-args`; use BuildKit secret mounts in a project-specific workflow if secret material is genuinely needed during a build.

## Copier

```console
copier copy gh:ylazakovich/project-toolkit my-project --vcs-ref v1.0.0 --trust
cd my-project
copier update --trust
```

The template accepts a YAML list of `python`, `node`, and `java` components plus Docker, Release Please, and Renovate booleans. Generated projects use Renovate presets from `ylazakovich/renovate-config` by default. Set `renovate_config_repository` to another GitHub `owner/repo` slug when a project should consume a different shared preset repository; it names the preset repository, not the generated consumer repository. Set `renovate_presets` to a non-empty YAML list of selected preset names, preserving the desired extends order. Supported names map to paths as follows: `default` -> `presets/base`, `python` -> `presets/python/default`, `javascript` -> `presets/npm/default`, `java` -> `presets/gradle/default`, `docker` -> `presets/docker/default`, and `github-actions` -> `presets/github-actions/default`. New projects infer `default` plus language presets from `components` and `docker` when enabled; `github-actions` remains explicit opt-in. The generated extends entries follow that preset repository's default branch intentionally; pin them manually later if a stricter stability policy requires it. Commit `.copier-answers.yml`; it is the update contract. Review generated diffs before accepting an update.

## Release Please

Use [`examples/release-single.yml`](../examples/release-single.yml) for one product version or [`examples/release-components.yml`](../examples/release-components.yml) with the example [component config](../examples/release-please-components-config.json) and [manifest](../examples/release-please-components-manifest.json) for independent versions. Both rely on Conventional Commits. Release Please updates `CHANGELOG.md` through its release PR. No release is created merely by copying this toolkit.

## Renovate

New Copier-generated projects extend selected presets from `ylazakovich/renovate-config` by default. The repository slug comes from the `renovate_config_repository` Copier answer, so project teams can point new projects at their own shared Renovate preset repository while keeping the selected preset paths. The `renovate_presets` answer uses user-facing names: `default` maps to `//presets/base`, `python` to `//presets/python/default`, `javascript` to `//presets/npm/default`, `java` to `//presets/gradle/default`, `docker` to `//presets/docker/default`, and `github-actions` to `//presets/github-actions/default`.

The legacy `github>ylazakovich/project-toolkit//renovate/default.json5` preset remains available for existing consumers. New generated projects intentionally follow the shared preset repository's default branch unless the generated `renovate.json` is manually pinned to a tag or commit later.
