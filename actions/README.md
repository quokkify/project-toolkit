# Composite actions

This toolkit now ships reusable composite actions for common setup and runtime patterns.

Examples use the current toolkit release, `v2.6.0`. Renovate updates the references in `examples/`, `README.md`, and `docs/` together with workflow references.

- `actions/setup-python/action.yml`
  - setup-python with dependency cache and install handling
- `actions/setup-node/action.yml`
  - setup-node with package-manager detection and cache
- `actions/setup-java-gradle/action.yml`
  - setup-java + Gradle-only caching with wrapper validation enabled by default and workspace-relative wrapper resolution
- `actions/compose-up/action.yml`
  - validates safe Compose paths, delegates one startup and container-health check to the immutable `compose-health-check-action@c11a8fa409adc13a0b7c401728d680872903af99` (`v2.3.0`), and optionally waits for HTTP readiness
- `actions/deploy-gh-pages-subdir/action.yml`
  - compatibility wrapper in toolkit `v2.6.0` that forwards the unchanged input contract once to immutable standalone `gh-pages-subdir-action` `v0.1.0` (`816d85aa756f480457befb42168633cb6ccf09c7`) and remains input-compatible for migration.
- `actions/junit-step-summary/action.yml`
  - safely aggregates bounded, workspace-contained JUnit XML globs into a GitHub job-summary table and numeric outputs
- `actions/allure-report/action.yml`
  - compatibility wrapper that forwards the CSP Allure 3 HTML/badge/PR-comment contract once to standalone `allure-report-action` `v0.1.1` (`8c79c827179d2ea135b9a14dd50d5c17d908636b`)

Consumers call these from their own jobs when they need the setup/runtime sequence without delegating the complete job to a reusable workflow. Run `actions/checkout` before these setup actions; in particular, `setup-java-gradle` must see the checked-out caller repository so its default wrapper validation can scan repository-contained `gradle-wrapper.jar` files. The toolkit reusable workflows remain self-contained because their checkout is the caller repository, not this toolkit repository.

`allure-report` expects the caller's already-merged Allure result directory and Allure 3 config. It delegates unchanged inputs to [`quokkify/allure-report-action`](https://github.com/quokkify/allure-report-action). Tests without an `epic` label remain in overall totals: the preserved CSP fallback classifies Playwright as `E2E`, while otherwise unclassified results appear under `Other`. The wrapper preserves CSP's `docs/testing/test-pyramid.md` policy link by default; standalone consumers can provide their own path or leave it empty. Pass `github-token: ${{ secrets.GITHUB_TOKEN }}` and grant `pull-requests: write` in both public and private repositories. GitHub Pages is optional and disabled by default; enable it only with `contents: write` and a destination directory. The hidden comment marker is configurable so repositories do not overwrite one another's report comments.

The Python and Node actions install dependencies by default. Set `install-dependencies: "false"` for runtime-only setup. The Java/Gradle action validates repository-contained Gradle Wrapper JAR files by default; set `validate-wrappers: "false"` only for repositories that intentionally do not use a wrapper. It deliberately leaves dependency and build commands to the caller. Inputs such as `install-command` are trusted workflow configuration; never construct them from pull-request titles, branch names, or other untrusted event data.

pnpm and modern Yarn projects must pin the package-manager version in `package.json` with `packageManager` (for example, `pnpm@10.0.0` or `yarn@4.0.0`). Yarn Classic lockfiles use the action's pinned Yarn 1 compatibility version. This avoids Corepack selecting an environment-dependent known-good release.

`junit-step-summary` is self-contained and framework-neutral. Call it with `if: always()` after the test command, because GitHub otherwise skips a later step when an earlier test step fails. `junit-paths` accepts newline-delimited paths or `*`, `?`, and `**` globs relative to `working-directory`; `**` must be a complete path segment. Literal path prefixes prune unrelated trees before a linear directory-fd walk. The action deduplicates files, does not follow symlinks, and bounds directory depth, scanned entries, matched files, per-file bytes, and aggregate bytes. It rejects traversal, DTD/entity declarations, malformed counts/durations, and unsafe file replacements, then exposes canonical suite totals through outputs without changing the underlying test command's result. Missing reports warn by default; set `fail-on-missing: "true"` when the report is mandatory. The action requires Python 3.9 or newer on a POSIX runner and no repository write permissions or secrets.

For a staged migration from the original CSP-local action, deprecated `cwd` plus `variant` inputs remain accepted together and map `frontend-single`, `backend-pytest`, and `e2e-playwright` to their historical report paths. New consumers must use `working-directory` plus `junit-paths`; do not mix the two contracts. CSP should use `fail-on-missing: "true"` while migrating so a wrong path cannot silently produce zero totals.

`compose-up` v2 is intentionally a thin wrapper. `compose-files` are relative to `working-directory`; paths are validated and prefixed before delegation so Compose derives its project directory from the first normalized file. When `services` is explicit, `completed-services` is appended as a stable, unique union; when `services` is empty, the standalone action retains its default coverage of all configured services, including successful one-shots. `build` maps to the standalone `--build` argument, and `timeout-seconds` maps to the standalone timeout. `wait-for-health: "false"` and `show-logs-on-failure: "false"` fail closed because the pinned standalone release owns those semantics. HTTP readiness is checked after the standalone action succeeds. With `down-on-timeout: "true"`, a failure runs only the scoped `docker compose down` command without `-v`; normal cleanup remains caller-owned.
