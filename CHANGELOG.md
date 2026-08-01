# Changelog

## [2.5.3](https://github.com/quokkify/project-toolkit/compare/v2.5.2...v2.5.3) (2026-08-01)


### Bug Fixes

* **actions:** authenticate gh-pages git with askpass ([#46](https://github.com/quokkify/project-toolkit/issues/46)) ([117229a](https://github.com/quokkify/project-toolkit/commit/117229addda82d2dd1a16a2d200e9aa19d0d79a7))

## [2.5.2](https://github.com/quokkify/project-toolkit/compare/v2.5.1...v2.5.2) (2026-08-01)


### Bug Fixes

* **actions:** use real token for gh-pages auth ([#44](https://github.com/quokkify/project-toolkit/issues/44)) ([c7cba31](https://github.com/quokkify/project-toolkit/commit/c7cba315692f61a4e17bd07536531a3d407c109b))

## [2.5.1](https://github.com/quokkify/project-toolkit/compare/v2.5.0...v2.5.1) (2026-08-01)


### Bug Fixes

* **actions:** pass token to gh-pages git auth ([#42](https://github.com/quokkify/project-toolkit/issues/42)) ([41b2e36](https://github.com/quokkify/project-toolkit/commit/41b2e3697f3d41905bf95e7b6b0f2a03e50ef2b6))

## [2.5.0](https://github.com/quokkify/project-toolkit/compare/v2.4.0...v2.5.0) (2026-08-01)


### Features

* **actions:** add gh-pages report retention ([#40](https://github.com/quokkify/project-toolkit/issues/40)) ([7f797ab](https://github.com/quokkify/project-toolkit/commit/7f797abd4a2efa95989fe341eba8392f76e636b3))

## [2.4.0](https://github.com/quokkify/project-toolkit/compare/v2.3.0...v2.4.0) (2026-08-01)


### Features

* **actions:** add gh-pages subdirectory deploy action ([#38](https://github.com/quokkify/project-toolkit/issues/38)) ([5aaca14](https://github.com/quokkify/project-toolkit/commit/5aaca142a43b998e0756b2995d13f4bec1bf2990))

## [2.3.0](https://github.com/quokkify/project-toolkit/compare/v2.2.0...v2.3.0) (2026-08-01)


### Features

* **renovate:** track validation dependencies ([#30](https://github.com/quokkify/project-toolkit/issues/30)) ([8707332](https://github.com/quokkify/project-toolkit/commit/870733296b04f650249b96f80f70dc11e3aa9525))


### Bug Fixes

* **renovate:** use quokkify shared preset ([#28](https://github.com/quokkify/project-toolkit/issues/28)) ([583d403](https://github.com/quokkify/project-toolkit/commit/583d40315cd5587b1570635f51a8866215d44d20))

## [2.2.0](https://github.com/quokkify/project-toolkit/compare/v2.1.0...v2.2.0) (2026-08-01)


### Features

* **copier:** support config-only projects ([#24](https://github.com/quokkify/project-toolkit/issues/24)) ([d932533](https://github.com/quokkify/project-toolkit/commit/d932533b27c3d2d1b7117cab994fce7eb6ce0379))

## [2.1.0](https://github.com/quokkify/project-toolkit/compare/v2.0.1...v2.1.0) (2026-08-01)


### Features

* **actions:** add JUnit step summary ([#13](https://github.com/quokkify/project-toolkit/issues/13)) ([b3dfca7](https://github.com/quokkify/project-toolkit/commit/b3dfca76183b306e57624885c67d8069f3e15d21))

## [2.0.1](https://github.com/quokkify/project-toolkit/compare/v2.0.0...v2.0.1) (2026-08-01)


### Bug Fixes

* **actions:** use quokkify repositories ([#11](https://github.com/quokkify/project-toolkit/issues/11)) ([63b504d](https://github.com/quokkify/project-toolkit/commit/63b504dc5f63ba3cce5a9e15837bae61155eb3cc))

## [2.0.0](https://github.com/ylazakovich/project-toolkit/compare/v1.1.1...v2.0.0) (2026-07-31)


### ⚠ BREAKING CHANGES

* Compose startup and container-health ownership moves to the pinned standalone v2.3.0 action. Legacy wait-for-health=false and show-logs-on-failure=false modes now fail closed before startup.

### Features

* delegate Compose startup to standalone health action ([68e51e0](https://github.com/ylazakovich/project-toolkit/commit/68e51e07bd48d804d6e9b7543ad830126b3a096b))

## [1.1.1](https://github.com/ylazakovich/project-toolkit/compare/v1.1.0...v1.1.1) (2026-07-31)


### Bug Fixes

* **actions:** validate Gradle wrappers ([#7](https://github.com/ylazakovich/project-toolkit/issues/7)) ([d933683](https://github.com/ylazakovich/project-toolkit/commit/d933683e8143db428888a3a0707903580c600f1a))

## [1.1.0](https://github.com/ylazakovich/project-toolkit/compare/v1.0.0...v1.1.0) (2026-07-31)


### Features

* **copier:** add shared Renovate presets ([#5](https://github.com/ylazakovich/project-toolkit/issues/5)) ([3e1f7fc](https://github.com/ylazakovich/project-toolkit/commit/3e1f7fc9a48b13ab36d79667536920d3bc618667))

## 1.0.0 (2026-07-31)


### Features

* **actions:** add reusable setup and compose primitives ([#2](https://github.com/ylazakovich/project-toolkit/issues/2)) ([6fa4b48](https://github.com/ylazakovich/project-toolkit/commit/6fa4b481e1271111b82939ca538c6554104a8e0f))
* initialize reusable project toolkit ([#1](https://github.com/ylazakovich/project-toolkit/issues/1)) ([d3798b5](https://github.com/ylazakovich/project-toolkit/commit/d3798b5b656d61e6f2e0fde4e8a62e67be9227f3))
* **release:** add Release Please driver ([#3](https://github.com/ylazakovich/project-toolkit/issues/3)) ([56590cb](https://github.com/ylazakovich/project-toolkit/commit/56590cb91bfdd92856235949c9364485593342f2))

## Changelog

Release Please maintains this file from Conventional Commits.
