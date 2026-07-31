# Versioning

- The toolkit publishes SemVer releases, with the first feature release expected at `v0.1.0` (manifest starts at `0.0.0`).
- Production examples and generated callers use exact immutable tags such as `@v1.2.0`; release tags are never rewritten.
- Breaking workflow/input/template changes require a new major release.
- Release flow is a stable two-step process:
  1) push to `main` runs `.github/workflows/release.yml` (caller) which invokes `.github/workflows/release-please.yml` in `manifest` mode with `config-file: .github/release-please/config.json` and `manifest-file: .github/release-please/manifest.json`;
  2) maintainers review and merge the Release Please PR; this task does not create tags or publish releases directly.
- Before `1.0.0`, breaking changes are called out prominently in release notes even when SemVer permits a minor bump.
- Renovate proposes toolkit upgrades through reviewable PRs.
- Mutable major aliases such as `v1` may be convenient but are weaker supply-chain pins; this toolkit's production examples prefer exact release tags, while a full commit SHA is the strongest immutable reference.

Template versioning and reusable workflow versioning are related but separate: `copier update` changes physical generated files, while Renovate changes referenced workflow tags.
