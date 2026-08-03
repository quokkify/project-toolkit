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

`allure-report` delegates exactly once to the immutable standalone [`quokkify/allure-report-action`](https://github.com/quokkify/allure-report-action) `v0.1.2` release (commit `72fb74fff8b564040f12fd5d97b9867241e2c35d`) while preserving the CSP input contract. The standalone implementation reads an already-merged results directory, writes badges and the PR summary, optionally exports the existing epic-based test-pyramid files, optionally publishes the HTML report, and finally creates or updates one marked comment. Tests without `epic` metadata remain in overall totals: the preserved CSP fallback classifies Playwright as `E2E`, while otherwise unclassified results appear under `Other`. Public and private repositories use the same explicit `github-token` input and repository context; callers grant `pull-requests: write`, plus `contents: write` only when Pages publishing is enabled. Pages publishing is off by default so private repositories can still generate and comment the summary without a public Pages dependency.

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
copier copy https://github.com/quokkify/project-toolkit.git my-project --vcs-ref v2.6.0 --trust
cd my-project
copier update --trust
```

Every generated repository receives the shared baseline workflows:

- `validate.yml` validates the committed Copier/configuration contract and runs the selected Python, Node.js, Java, and Docker jobs;
- `codeql.yml` analyzes GitHub Actions plus the languages inferred from `components`;
- `gitleaks.yml` scans both Git history and the current tree with a checksum-verified binary;
- `release.yml` uses the shared Release Please workflow when `release_please` is enabled;
- `.github/renovate.json` extends the selected organization presets when `renovate` is enabled.

The `Audit Copier-managed repositories` workflow runs daily in read-only mode and can also be started by a CODEOWNER from the Actions UI or with `gh workflow run copier-fleet-update.yml --repo quokkify/project-toolkit`; the API call is authenticated by the caller's current `gh` session. Because the hosted job intentionally uses only the repository-scoped `GITHUB_TOKEN`, its supported scheduled fleet is explicitly limited to public Quokkify repositories; private consumers require an explicit CODEOWNER-run local audit and are never silently claimed as covered by the badge. The workflow discovers non-archived, non-fork public organization repositories containing `.copier-answers.yml`, accepts only answers whose `_src_path` resolves to `quokkify/project-toolkit`, and performs a `copier update` preview against the latest released template tag. The organization profile repository `quokkify/.github` and template source repository `quokkify/project-toolkit` are explicitly excluded before Copier metadata is inspected because neither is a generated consumer project. The audit fails with a distinct drift status when any supported repository would change, making the README badge red; a green badge means the most recent audit completed and found no drift in that public fleet. An explicitly requested repository that cannot be accessed fails the run. The complete per-repository result is written to the Actions job summary.

GitHub does not transfer the dispatching user's credential into the hosted workflow, so cross-repository writes cannot safely happen inside Actions without a stored PAT or GitHub App key. Apply updates from a CODEOWNER's short-lived local/API session instead:

```console
GH_TOKEN="$(gh auth token)" python scripts/update_copier_fleet.py --org quokkify --write
gh workflow run copier-fleet-update.yml --repo quokkify/project-toolkit
```

The first command creates or refreshes `chore: update shared project template` pull requests using the caller's token without copying it into repository or organization secrets. The second command starts the read-only audit and refreshes the badge. Use `--repo owner/repository` to target one consumer and `--template-ref REF` to test an explicit template version. Existing project changes are preserved by Copier's update algorithm; `.rej` conflicts fail that repository loudly instead of opening a partial PR. The deterministic `automation/copier-template-update` branch is automation-owned and may be force-updated with an exact lease, so maintainers should not add manual commits to it. Normal updates follow the latest release tag rather than unreleased `main`.

The template accepts an optional YAML list of `python`, `node`, and `java` components plus Docker, Release Please, and Renovate booleans. Leave `components` empty when the repository owns custom language-specific validation; the shared template-contract validation, CodeQL Actions analysis, and Gitleaks still remain present. Generated projects use Renovate presets from `quokkify/renovate-presets` by default. Set `renovate_config_repository` to another GitHub `owner/repo` slug when a project should consume a different shared preset repository; it names the preset repository, not the generated consumer repository. Set `renovate_presets` to a non-empty YAML list of selected preset names, preserving the desired extends order. Supported names map to paths as follows: `default` -> `presets/base`, `python` -> `presets/python/default`, `javascript` -> `presets/npm/default`, `java` -> `presets/gradle/default`, `docker` -> `presets/docker/default`, and `github-actions` -> `presets/github-actions/default`. New projects infer `default`, `github-actions`, and the language/Docker presets selected by `components` and `docker`. The generated extends entries follow that preset repository's default branch intentionally; pin them manually later if a stricter stability policy requires it. Commit `.copier-answers.yml`; it is the update contract. Review generated pull requests before merging them.

## Release Please

Use [`examples/release-single.yml`](../examples/release-single.yml) for one product version or [`examples/release-components.yml`](../examples/release-components.yml) with the example [component config](../examples/release-please-components-config.json) and [manifest](../examples/release-please-components-manifest.json) for independent versions. Both rely on Conventional Commits. A push to `main` runs Release Please and creates or updates a release PR for user-facing `feat`/`fix` commits; merging that release PR creates the tag and GitHub Release. Chore-only commits intentionally do not create a release.

## Renovate

New Copier-generated projects extend selected presets from `quokkify/renovate-presets` by default. The repository slug comes from the `renovate_config_repository` Copier answer, so project teams can point new projects at their own shared Renovate preset repository while keeping the selected preset paths. The `renovate_presets` answer uses user-facing names: `default` maps to `//presets/base`, `python` to `//presets/python/default`, `javascript` to `//presets/npm/default`, `java` to `//presets/gradle/default`, `docker` to `//presets/docker/default`, and `github-actions` to `//presets/github-actions/default`.

The bundled `github>quokkify/project-toolkit//renovate/default.json` preset remains available for toolkit-specific workflow reference updates. New generated projects intentionally follow the shared preset repository's default branch unless the generated `.github/renovate.json` is manually pinned to a tag or commit later.

The repository also manages versions that are easy to miss with Renovate's built-in managers:

- `_min_copier_version` in the root `copier.yml` uses the PyPI `copier` datasource.
- Toolkit release tags in Markdown and example YAML use the GitHub tags datasource.
- The documented Compose health action release follows the same GitHub tag as the pinned action implementation.

This keeps the version shown to readers consistent with the version executed by CI. Review the generated PR as usual; Renovate never automerges these changes.
