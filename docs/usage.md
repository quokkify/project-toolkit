# Usage

Examples pin an exact immutable project-toolkit release. All toolkit references in this page are managed by Renovate and move together when a new release is published.

Copy a small caller workflow from [`examples/`](../examples/) and replace commands/paths. Production callers use an exact released tag:

```yaml
jobs:
  backend:
    uses: quokkify/project-toolkit/.github/workflows/python-ci.yml@v2.6.0
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
- `actions/deploy-gh-pages-subdir/action.yml`
- `actions/junit-step-summary/action.yml`
- `actions/allure-report/action.yml`

Use examples in [`examples/setup-actions.yml`](../examples/setup-actions.yml). The action inputs are versioned and can be called with their defaults where repository conventions already match the toolkit assumptions. Custom install commands are trusted caller configuration and must never interpolate untrusted pull-request data.

The Python and Node actions install dependencies by default; set `install-dependencies: "false"` when only the language runtime and cache are needed. The Java/Gradle action prepares Java, Gradle caches, and a workspace-relative wrapper command; callers run their own Gradle dependency/build command. `compose-up` is Linux-only, delegates exactly once to the immutable standalone `compose-health-check-action@c11a8fa409adc13a0b7c401728d680872903af99` (`v2.3.0`), accepts newline-separated `compose-files` and `wait-urls`, and validates and prefixes `working-directory`-relative compose paths so Compose derives its project directory from the first normalized file. With explicit `services`, it passes a normalized union with `completed-services`; without explicit services, standalone default coverage remains active and includes successful one-shot containers. `wait-for-health: "false"` and `show-logs-on-failure: "false"` fail closed; migrate to the standalone-owned defaults instead. It requires no write permissions by itself. Callers remain responsible for granting only the permissions required by their surrounding job and for running normal `docker compose down` cleanup when needed. `down-on-timeout: "true"` enables only failure cleanup scoped to the validated Compose files, without `-v`.

`deploy-gh-pages-subdir` in toolkit `v2.6.0` delegates exactly once to the immutable standalone [`quokkify/gh-pages-subdir-action`](https://github.com/quokkify/gh-pages-subdir-action) `v0.1.0` release (commit `816d85aa756f480457befb42168633cb6ccf09c7`) with unchanged inputs; this keeps existing input consumers stable. The standalone action validates workspace and destination paths, preserves sibling directories, keeps the token out of the remote URL and command arguments, and uses `--force-with-lease` with one concurrent-update retry. The caller must grant `contents: write`; normal branch protection and deployment policy remain the caller's responsibility. Use it for isolated paths such as `allure/pr-42`, not for replacing an entire Pages branch. New consumers can call the standalone root action directly.

`allure-report` runs the existing CSP Allure 3 report generator from an already-merged results directory, writes badges and the PR summary, optionally exports the existing epic-based test-pyramid files, optionally publishes the HTML report, and finally creates or updates one bot comment. Tests without `epic` metadata remain in overall totals and appear as `Other`. Public and private repositories use the same explicit `github-token` input and repository context; callers grant `pull-requests: write`, plus `contents: write` only when Pages publishing is enabled. Pages publishing is off by default so private repositories can still generate and comment the summary without a public Pages dependency.

Call `junit-step-summary` with `if: always()` after a test step. It accepts one or more workspace-relative JUnit XML paths or `*`, `?`, and `**` globs (`**` must be a complete path segment), aggregates standard `testsuite`/`testsuites` documents, appends a Markdown table to `GITHUB_STEP_SUMMARY`, and exposes counts and duration as action outputs. It warns when no files match unless `fail-on-missing: "true"`. Literal prefixes prevent unrelated repository trees from being scanned. Directory depth, scanned entries, matched files, per-file bytes, and aggregate bytes are bounded; symlinks, traversal, DTD/entity declarations, malformed numbers, and unsafe file replacements are rejected. Python 3.9 or newer must be available on a POSIX runner. Deprecated CSP `cwd`/`variant` inputs are supported only as a migration bridge and cannot be mixed with the generic inputs.

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
copier copy gh:quokkify/project-toolkit my-project --vcs-ref v2.6.0 --trust
cd my-project
copier update --trust
```

The template accepts an optional YAML list of `python`, `node`, and `java` components plus Docker, Release Please, and Renovate booleans. Leave `components` empty when the repository owns a custom CI workflow (for example a config-only repository); Copier then omits the toolkit CI workflow instead of generating an empty job set. Generated projects use Renovate presets from `quokkify/renovate-presets` by default. Set `renovate_config_repository` to another GitHub `owner/repo` slug when a project should consume a different shared preset repository; it names the preset repository, not the generated consumer repository. Set `renovate_presets` to a non-empty YAML list of selected preset names, preserving the desired extends order. Supported names map to paths as follows: `default` -> `presets/base`, `python` -> `presets/python/default`, `javascript` -> `presets/npm/default`, `java` -> `presets/gradle/default`, `docker` -> `presets/docker/default`, and `github-actions` -> `presets/github-actions/default`. New projects infer `default` plus language presets from `components` and `docker` when enabled; `github-actions` remains explicit opt-in. The generated extends entries follow that preset repository's default branch intentionally; pin them manually later if a stricter stability policy requires it. Commit `.copier-answers.yml`; it is the update contract. Review generated diffs before accepting an update.

## Release Please

Use [`examples/release-single.yml`](../examples/release-single.yml) for one product version or [`examples/release-components.yml`](../examples/release-components.yml) with the example [component config](../examples/release-please-components-config.json) and [manifest](../examples/release-please-components-manifest.json) for independent versions. Both rely on Conventional Commits. A push to `main` runs Release Please and creates or updates a release PR for user-facing `feat`/`fix` commits; merging that release PR creates the tag and GitHub Release. Chore-only commits intentionally do not create a release.

## Renovate

New Copier-generated projects extend selected presets from `quokkify/renovate-presets` by default. The repository slug comes from the `renovate_config_repository` Copier answer, so project teams can point new projects at their own shared Renovate preset repository while keeping the selected preset paths. The `renovate_presets` answer uses user-facing names: `default` maps to `//presets/base`, `python` to `//presets/python/default`, `javascript` to `//presets/npm/default`, `java` to `//presets/gradle/default`, `docker` to `//presets/docker/default`, and `github-actions` to `//presets/github-actions/default`.

The bundled `github>quokkify/project-toolkit//renovate/default.json` preset remains available for toolkit-specific workflow reference updates. New generated projects intentionally follow the shared preset repository's default branch unless the generated `renovate.json` is manually pinned to a tag or commit later.

The repository also manages versions that are easy to miss with Renovate's built-in managers:

- `_min_copier_version` in the root `copier.yml` uses the PyPI `copier` datasource.
- Toolkit release tags in Markdown and example YAML use the GitHub tags datasource.
- The documented Compose health action release follows the same GitHub tag as the pinned action implementation.

This keeps the version shown to readers consistent with the version executed by CI. Review the generated PR as usual; Renovate never automerges these changes.
