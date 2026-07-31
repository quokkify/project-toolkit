# Composite actions

This toolkit now ships reusable composite actions for common setup and runtime patterns:

- `actions/setup-python/action.yml`
  - setup-python with dependency cache and install handling
- `actions/setup-node/action.yml`
  - setup-node with package-manager detection and cache
- `actions/setup-java-gradle/action.yml`
  - setup-java + Gradle-only caching with wrapper validation enabled by default and workspace-relative wrapper resolution
- `actions/compose-up/action.yml`
  - validates safe Compose paths, delegates one startup and container-health check to the immutable `compose-health-check-action@c11a8fa409adc13a0b7c401728d680872903af99` (`v2.3.0`), and optionally waits for HTTP readiness

Consumers call these from their own jobs when they need the setup/runtime sequence without delegating the complete job to a reusable workflow. Run `actions/checkout` before these setup actions; in particular, `setup-java-gradle` must see the checked-out caller repository so its default wrapper validation can scan repository-contained `gradle-wrapper.jar` files. The toolkit reusable workflows remain self-contained because their checkout is the caller repository, not this toolkit repository.

The Python and Node actions install dependencies by default. Set `install-dependencies: "false"` for runtime-only setup. The Java/Gradle action validates repository-contained Gradle Wrapper JAR files by default; set `validate-wrappers: "false"` only for repositories that intentionally do not use a wrapper. It deliberately leaves dependency and build commands to the caller. Inputs such as `install-command` are trusted workflow configuration; never construct them from pull-request titles, branch names, or other untrusted event data.

pnpm and modern Yarn projects must pin the package-manager version in `package.json` with `packageManager` (for example, `pnpm@10.0.0` or `yarn@4.0.0`). Yarn Classic lockfiles use the action's pinned Yarn 1 compatibility version. This avoids Corepack selecting an environment-dependent known-good release.

`compose-up` v2 is intentionally a thin wrapper. `compose-files` are relative to `working-directory`; paths are validated and prefixed before delegation so Compose derives its project directory from the first normalized file. When `services` is explicit, `completed-services` is appended as a stable, unique union; when `services` is empty, the standalone action retains its default coverage of all configured services, including successful one-shots. `build` maps to the standalone `--build` argument, and `timeout-seconds` maps to the standalone timeout. `wait-for-health: "false"` and `show-logs-on-failure: "false"` fail closed because the pinned standalone release owns those semantics. HTTP readiness is checked after the standalone action succeeds. With `down-on-timeout: "true"`, a failure runs only the scoped `docker compose down` command without `-v`; normal cleanup remains caller-owned.
