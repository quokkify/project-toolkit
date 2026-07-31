# Versioning

- The toolkit publishes SemVer releases.
- Production examples and generated callers use exact immutable tags such as `@v1.2.0`; release tags are never rewritten.
- Renovate proposes toolkit upgrades through reviewable PRs.
- Breaking workflow/input/template changes require a new major release.
- Before `1.0.0`, breaking changes are called out prominently in release notes even when SemVer permits a minor bump.
- Mutable major aliases such as `v1` may be convenient but are weaker supply-chain pins; this toolkit's production examples prefer exact release tags, while a full commit SHA is the strongest immutable reference.

Template versioning and reusable workflow versioning are related but separate: `copier update` changes physical generated files, while Renovate changes referenced workflow tags.
