# Usage

Examples pin an exact immutable project-toolkit release. All toolkit references in this page are managed by Renovate and move together when a new release is published.

Copy a small caller workflow from [`examples/`](../examples/) and replace commands/paths. Production callers use an exact released tag:

```yaml
jobs:
  backend:
    uses: quokkify/project-toolkit/.github/workflows/python-ci.yml@v2.12.1
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

The Python and Node actions install dependencies by default; set `install-dependencies: "false"` when only the language runtime and cache are needed. The Java/Gradle action prepares Java, Gradle caches, and a workspace-relative wrapper command; callers run their own Gradle dependency/build command. `compose-up` is Linux-only, delegates exactly once to the immutable standalone health action, accepts newline-separated `compose-files` and `wait-urls`, normalizes `profiles`, and validates and prefixes `working-directory`-relative Compose and lifecycle-hook paths. `before-compose-hook` is sourced before startup so it can export Compose interpolation values; `after-health-hook` runs project-owned readiness checks after container health succeeds. With explicit `services`, the wrapper passes a normalized union with `completed-services`; without explicit services, standalone default coverage remains active and includes successful one-shot containers. `wait-for-health: "false"` and `show-logs-on-failure: "false"` fail closed; migrate to the standalone-owned defaults instead. It requires no write permissions by itself. Callers remain responsible for granting only the permissions required by their surrounding job and for running normal `docker compose down` cleanup when needed. `down-on-timeout: "true"` enables only failure cleanup scoped to the validated Compose files, without `-v`.

`deploy-gh-pages-subdir` in toolkit `v2.6.0` delegates exactly once to the immutable standalone [`quokkify/gh-pages-subdir-action`](https://github.com/quokkify/gh-pages-subdir-action) `v0.1.1` release (commit `816d85aa756f480457befb42168633cb6ccf09c7`) with unchanged inputs; this keeps existing input consumers stable. The standalone action validates workspace and destination paths, preserves sibling directories, keeps the token out of the remote URL and command arguments, and uses `--force-with-lease` with one concurrent-update retry. The caller must grant `contents: write`; normal branch protection and deployment policy remain the caller's responsibility. Use it for isolated paths such as `allure/pr-42`, not for replacing an entire Pages branch. New consumers can call the standalone root action directly.

`allure-report` delegates exactly once to the immutable standalone [`quokkify/allure-report-action`](https://github.com/quokkify/allure-report-action) `v0.4.1` release (commit `05778ce0c6cee483892e2cc80b841e031dc4c7d0`) while preserving the caller input contract. The wrapper defaults `source-artifacts-directory` to `auto`: complete colocated `ci-env-fragment.properties` provenance activates atomic per-job result merging and module attribution, while repositories without that contract keep their already-merged results. The standalone implementation creates module-scoped environments from the configurable `module-environment-label`, scopes each environment's variables to its authoritative provenance, writes badges and the PR summary, optionally exports the existing epic-based test-pyramid files, optionally publishes the HTML report, and creates or updates one marked PR comment when `pr-number` is set. Tests without `epic` metadata remain in overall totals: Playwright is classified as `E2E`, while otherwise unclassified results appear under `No epic assigned`. Public and private repositories use the same explicit `github-token` input and repository context; callers grant `pull-requests: write`, plus `contents: write` only when Pages publishing is enabled. Pages publishing is off by default so private repositories can still generate and comment the summary without a public Pages dependency.

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
copier copy https://github.com/quokkify/project-toolkit.git my-project --vcs-ref v2.12.1 --trust
cd my-project
copier update --trust
```

Every generated repository receives the shared baseline workflows:

- `validate.yml` validates the committed Copier/configuration contract and runs the selected Python, Node.js, Java, and Docker jobs;
- `codeql.yml` analyzes GitHub Actions plus the languages inferred from `components`;
- `gitleaks.yml` scans both Git history and the current tree with a checksum-verified binary;
- `release.yml` uses the shared Release Please workflow when `release_please` is enabled;
- `allure-report.yml` securely consumes source-run `allure-results-*` artifacts and comments an Allure 3 report when `allure_report` is enabled;
- `.github/renovate.json` extends the selected organization presets when `renovate` is enabled.

The `Audit Copier-managed repositories` workflow runs daily in read-only mode and can also be started by a CODEOWNER from the Actions UI or with `gh workflow run copier-fleet-update.yml --repo quokkify/project-toolkit`; the API call is authenticated by the caller's current `gh` session. Because the hosted job intentionally uses only the repository-scoped `GITHUB_TOKEN`, its supported scheduled fleet is explicitly limited to public Quokkify repositories; private consumers require an explicit CODEOWNER-run local audit and are never silently claimed as covered by the badge. The workflow discovers non-archived, non-fork public organization repositories containing `.copier-answers.yml`, accepts only answers whose `_src_path` resolves to `quokkify/project-toolkit`, and performs a `copier update` preview against the latest released template tag. The organization profile repository `quokkify/.github` and template source repository `quokkify/project-toolkit` are explicitly excluded before Copier metadata is inspected because neither is a generated consumer project. The audit fails with a distinct drift status when any supported repository would change, making the README badge red; a green badge means the most recent audit completed and found no drift in that public fleet. An explicitly requested repository that cannot be accessed fails the run. Console output includes the recorded template version, components, baseline coverage, and Docker, Allure, Release Please, and Renovate states for each managed repository. The Actions job summary renders the same inventory as a Markdown matrix with drift and missing-output details, and the workflow uploads a versioned `copier-fleet-audit.json` artifact for automation. JSON schema version 2 adds the `allure_report` feature state. Conditional outputs are classified as enabled, disabled, missing, custom, or unknown rather than treating absent legacy answers as false.

GitHub does not transfer the dispatching user's credential into the hosted workflow, so cross-repository writes cannot safely happen inside Actions without a stored PAT or GitHub App key. Apply updates from a CODEOWNER's short-lived local/API session instead:

```console
GH_TOKEN="$(gh auth token)" python scripts/update_copier_fleet.py --org quokkify --write
gh workflow run copier-fleet-update.yml --repo quokkify/project-toolkit
```

The first command creates or refreshes `chore: update shared project template` pull requests using the caller's token without copying it into repository or organization secrets. The second command starts the read-only audit and refreshes the badge. Use `--repo owner/repository` to target one consumer and `--template-ref REF` to test an explicit template version. Existing project changes are preserved by Copier's update algorithm; `.rej` conflicts fail that repository loudly instead of opening a partial PR. The deterministic `automation/copier-template-update` branch is automation-owned and may be force-updated with an exact lease, so maintainers should not add manual commits to it. Normal updates follow the latest release tag rather than unreleased `main`.

The template accepts an optional YAML list of `python`, `node`, and `java` components plus Docker, Allure, Release Please, and Renovate booleans. Leave `components` empty when the repository owns custom language-specific validation; the shared template-contract validation, CodeQL Actions analysis, and Gitleaks still remain present. Generated projects use Renovate presets from `quokkify/renovate-presets` by default. Set `renovate_config_repository` to another GitHub `owner/repo` slug when a project should consume a different shared preset repository; it names the preset repository, not the generated consumer repository. Set `renovate_presets` to a non-empty YAML list of selected preset names, preserving the desired extends order. Supported names map to paths as follows: `default` -> `presets/base`, `python` -> `presets/python/default`, `javascript` -> `presets/npm/default`, `java` -> `presets/gradle/default`, `docker` -> `presets/docker/default`, and `github-actions` -> `presets/github-actions/default`. New projects infer `default`, `github-actions`, and the language/Docker presets selected by `components` and `docker`. The generated extends entries follow that preset repository's default branch intentionally; pin them manually later if a stricter stability policy requires it. Commit `.copier-answers.yml`; it is the update contract. Review generated pull requests before merging them.

## Copier Allure reporting

Set `allure_report: true` to generate `.github/allure/allurerc.mjs`, `.github/allure/safe_extract.py`, and `.github/workflows/allure-report.yml`. With generated `components`, each component job uploads one required, uniquely named `allure-results-<type>-<index>` artifact. The default source is `<component path>/allure-results`; set an optional safe relative `allure_results_path` on a component for layouts such as Gradle's `build/allure-results` or Maven's `target/allure-results`. Configure the project's test adapter to write there—for example `pytest --alluredir=allure-results`, an Allure-enabled Java test task, or the selected Node test framework's Allure reporter. Missing required results fail the component job. The template deliberately does not modify dependency manifests or replace project-specific test commands.

Repositories with `components: []` can still use the managed report workflow while retaining project-owned test orchestration. Configure the exact `allure_external_workflow_name` and `.github/workflows/...` path, a dedicated artifact-name prefix, and a minimum/maximum artifact count from 1 through 50. The source workflow must upload only Allure result bundles under that prefix; keep broader JUnit, logs, and build reports in separately named artifacts. Every selected bundle is subject to the same aggregate compressed/expanded limits and collision checks. Use `allure_categories_file` when the project owns an optional categories JSON file; the generated workflow verifies that the configured source workflow and categories file exist.

The follow-up resolves the current open PR through GitHub's API, requires its repository and head SHA to match the exact source run, validates either the generated exact-name allowlist or the configured external prefix/count contract, rejects expired artifacts, and suppresses stale runs. Artifact download, collision-safe bounded merging, and Allure generation happen in a read-only job. Compressed bytes are streamed into `runner.temp`; central-directory, path, type, count, per-file, and aggregate expanded-size limits are verified before any archive member is extracted. Extraction also stays under `runner.temp`; only fully validated regular files are then copied into a symlink-checked isolated workspace directory. The Pages job applies the same bounded pre-extraction gate to the generated report artifact before publication. A separate narrowly privileged job constructs a static trusted comment with links to the generated HTML artifact and source run—it never executes or posts Markdown supplied by the PR artifacts. Fork and Dependabot PRs receive that safe comment but never Pages publication.

Set `allure_publish_pages: true` only when the repository intentionally publishes reports, and provide the real `allure_pages_url` served by the repository. Only the Pages job receives `contents: write`; it rechecks source freshness, validates the exact generated report artifact, and publishes below `allure/pr-N` on `gh-pages`. Configure GitHub Pages to serve that branch/root and ensure repository Actions policy permits write tokens. Pages remains disabled by default.

Older `.copier-answers.yml` files have no Allure answer. Fleet audit reports them as `unknown`, not `disabled`; once configured, the workflow, config, and bounded extractor must all exist for the feature to be `enabled`. External-workflow mode remains template-managed: Copier owns the report workflow, config, and extractor while the consumer owns only its source test workflow and dedicated result uploads.

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
