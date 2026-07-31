# Composite actions

This toolkit now ships reusable composite actions for common setup and runtime patterns:

- `actions/setup-python/action.yml`
  - setup-python with dependency cache and install handling
- `actions/setup-node/action.yml`
  - setup-node with package-manager detection and cache
- `actions/setup-java-gradle/action.yml`
  - setup-java + dependency caching with Gradle wrapper resolution
- `actions/compose-up/action.yml`
  - one or more Compose files, optional image build, container health gating, and optional HTTP readiness

Consumers call these from their own jobs when they need the setup/runtime sequence without delegating the complete job to a reusable workflow. The toolkit reusable workflows remain self-contained because their checkout is the caller repository, not this toolkit repository.

The setup actions install dependencies by default. Set `install-dependencies: "false"` for runtime-only setup. Inputs such as `install-command` are trusted workflow configuration; never construct them from pull-request titles, branch names, or other untrusted event data.
