# Changelog

## [2.20.1](https://github.com/quokkify/project-toolkit/compare/v2.20.0...v2.20.1) (2026-09-02)


### 🐛 Bug Fixes

* **allure:** merge external results from a separate source directory ([#206](https://github.com/quokkify/project-toolkit/issues/206)) ([8082629](https://github.com/quokkify/project-toolkit/commit/8082629d8ccbfc16ac31cae8f3ddb8a35d83f883))

## [2.20.0](https://github.com/quokkify/project-toolkit/compare/v2.19.2...v2.20.0) (2026-09-02)


### ✨ Features

* **ci:** propagate template releases to consumers automatically ([#202](https://github.com/quokkify/project-toolkit/issues/202)) ([a8b7156](https://github.com/quokkify/project-toolkit/commit/a8b71566ff701f7df149dd3a060e61aee015bef3))


### 🐛 Bug Fixes

* **fleet:** bump digest-pinned toolkit refs with the template version ([#204](https://github.com/quokkify/project-toolkit/issues/204)) ([95c4bbd](https://github.com/quokkify/project-toolkit/commit/95c4bbd87cc7b8bcd80b47c1ad688cbb11180cec))

## [2.19.2](https://github.com/quokkify/project-toolkit/compare/v2.19.1...v2.19.2) (2026-09-02)


### 🐛 Bug Fixes

* **allure:** propagate current CLI and track Renovate updates ([#201](https://github.com/quokkify/project-toolkit/issues/201)) ([c33d542](https://github.com/quokkify/project-toolkit/commit/c33d54217b283c13fad4394e6befdf4e52da83d9))
* **renovate:** manage every executable Copier pin ([#200](https://github.com/quokkify/project-toolkit/issues/200)) ([da44951](https://github.com/quokkify/project-toolkit/commit/da44951ed110c467b011435da6e90d6160e6d94a))


### 📚 Documentation

* use centralized architecture diagram ([#198](https://github.com/quokkify/project-toolkit/issues/198)) ([2d98168](https://github.com/quokkify/project-toolkit/commit/2d9816882af46068e5bd9b9e1b6191e6b4c4c1c1))


### 🧹 Chores

* **deps:** update copier to v9.18.1 ([#195](https://github.com/quokkify/project-toolkit/issues/195)) ([f6ec162](https://github.com/quokkify/project-toolkit/commit/f6ec162ecbc5be3239395a903afbb13d11a5ce70))
* **deps:** update quokkify/project-toolkit to v2.19.1 ([#196](https://github.com/quokkify/project-toolkit/issues/196)) ([c735d8e](https://github.com/quokkify/project-toolkit/commit/c735d8eb2a3e6583f25204a55e359bc3d1e5d9ed))
* **deps:** update renovate to v44.56.1 ([#197](https://github.com/quokkify/project-toolkit/issues/197)) ([9fe83cf](https://github.com/quokkify/project-toolkit/commit/9fe83cfbd658b1fa303059af24cb8407d72c8d7a))

## [2.19.1](https://github.com/quokkify/project-toolkit/compare/v2.19.0...v2.19.1) (2026-09-01)


### 🐛 Bug Fixes

* **allure:** link the PR comment to the published report ([#194](https://github.com/quokkify/project-toolkit/issues/194)) ([bf3913b](https://github.com/quokkify/project-toolkit/commit/bf3913b605e20e0672530f75286a8b7911e0da7e))
* **fleet:** bump toolkit references in project-owned workflows ([#191](https://github.com/quokkify/project-toolkit/issues/191)) ([aa4d4e1](https://github.com/quokkify/project-toolkit/commit/aa4d4e19d6e84bfb1542c26bf84e861caf3d9039))

## [2.19.0](https://github.com/quokkify/project-toolkit/compare/v2.18.1...v2.19.0) (2026-09-01)


### ✨ Features

* **copier:** support manifest release mode ([#190](https://github.com/quokkify/project-toolkit/issues/190)) ([e5e8257](https://github.com/quokkify/project-toolkit/commit/e5e825736c71f08257a7c749821ebff7c6f7bcc2))


### 🐛 Bug Fixes

* **fleet:** let git use the token the workflow already provides ([#187](https://github.com/quokkify/project-toolkit/issues/187)) ([a00b4fa](https://github.com/quokkify/project-toolkit/commit/a00b4fad2ca34f768aaf7abc6c3fb6a5355adacb))


### 📚 Documentation

* state the permissions the fleet token actually needs ([#189](https://github.com/quokkify/project-toolkit/issues/189)) ([a7570b4](https://github.com/quokkify/project-toolkit/commit/a7570b4606e60cb971853d81c9f9c2ed569309aa))

## [2.18.1](https://github.com/quokkify/project-toolkit/compare/v2.18.0...v2.18.1) (2026-09-01)


### 🐛 Bug Fixes

* **copier:** return the Renovate config to the project that owns it ([#185](https://github.com/quokkify/project-toolkit/issues/185)) ([c070151](https://github.com/quokkify/project-toolkit/commit/c070151789d7305ca0e79b0902d0b9185fe56163))

## [2.18.0](https://github.com/quokkify/project-toolkit/compare/v2.17.0...v2.18.0) (2026-09-01)


### ✨ Features

* **copier:** let a project declare what CodeQL scans ([#182](https://github.com/quokkify/project-toolkit/issues/182)) ([72340c7](https://github.com/quokkify/project-toolkit/commit/72340c75e4e40d8e7d3ae29a835c3349421dc194))


### 🐛 Bug Fixes

* **copier:** emit a Renovate config that matches a formatter ([#183](https://github.com/quokkify/project-toolkit/issues/183)) ([c294840](https://github.com/quokkify/project-toolkit/commit/c294840c878aa87d628f28e7211abcf1f05f86aa))
* **copier:** stop template updates from overwriting a project's README ([#181](https://github.com/quokkify/project-toolkit/issues/181)) ([b4d8aec](https://github.com/quokkify/project-toolkit/commit/b4d8aec4a1aacf521ee1656a2f3a7595ce162058))

## [2.17.0](https://github.com/quokkify/project-toolkit/compare/v2.16.0...v2.17.0) (2026-09-01)


### ✨ Features

* **copier:** add a self-service template update workflow ([#179](https://github.com/quokkify/project-toolkit/issues/179)) ([7c81411](https://github.com/quokkify/project-toolkit/commit/7c814118849320dd458babb0e0935fd375c28504))
* **copier:** give project-toolkit sole ownership of template-owned pins ([#173](https://github.com/quokkify/project-toolkit/issues/173)) ([82a18e4](https://github.com/quokkify/project-toolkit/commit/82a18e43bb8e0bb4547c640f355e213e07c889e8))
* **workflows:** add the public-only Copier fleet auto-update workflow ([#162](https://github.com/quokkify/project-toolkit/issues/162)) ([44bf820](https://github.com/quokkify/project-toolkit/commit/44bf820dc0b74e97524be4c88c70842024e1a963))


### 🐛 Bug Fixes

* match Allure resolve step by action name, not pinned SHA ([#178](https://github.com/quokkify/project-toolkit/issues/178)) ([259c5a8](https://github.com/quokkify/project-toolkit/commit/259c5a8306356e402b6370c049e6b251f4208958))
* match the Allure report action by name, not by its pinned SHA ([#180](https://github.com/quokkify/project-toolkit/issues/180)) ([dee812c](https://github.com/quokkify/project-toolkit/commit/dee812c9a3ed4305332d96f2931adf700754bb5b))


### 🧹 Chores

* **deps:** update actions/github-script action to v9 ([#176](https://github.com/quokkify/project-toolkit/issues/176)) ([fab8049](https://github.com/quokkify/project-toolkit/commit/fab8049d052ca7395de8087bc7681f3117ea47b5))
* **deps:** update quokkify/allure-report-action action to v0.4.1 ([#174](https://github.com/quokkify/project-toolkit/issues/174)) ([56a5ce2](https://github.com/quokkify/project-toolkit/commit/56a5ce2634b67bc2d16cee90e7a8122d79af4074))
* **deps:** update renovate to v44.54.0 ([#175](https://github.com/quokkify/project-toolkit/issues/175)) ([de5bff6](https://github.com/quokkify/project-toolkit/commit/de5bff6e33ffe4f10fd725f90aad05895cd93250))

## [2.16.0](https://github.com/quokkify/project-toolkit/compare/v2.15.0...v2.16.0) (2026-09-01)


### ✨ Features

* **copier:** make the CodeQL workflow opt-out ([#172](https://github.com/quokkify/project-toolkit/issues/172)) ([cf34077](https://github.com/quokkify/project-toolkit/commit/cf34077bed1d76e024459600ab9f054a3945bdfe))


### 🐛 Bug Fixes

* **gitleaks:** stop fetching a ref the checkout already has ([#170](https://github.com/quokkify/project-toolkit/issues/170)) ([92b4ce6](https://github.com/quokkify/project-toolkit/commit/92b4ce6f19f7319ea90348b803399f76b9ea5262))

## [2.15.0](https://github.com/quokkify/project-toolkit/compare/v2.14.0...v2.15.0) (2026-09-01)


### ✨ Features

* **workflows:** add trusted reusable Allure publisher ([b5ecec8](https://github.com/quokkify/project-toolkit/commit/b5ecec8724d6dc86064c2741bd1292fda273e09d))


### 🧹 Chores

* **deps:** update quokkify/project-toolkit to v2.12.3 ([#163](https://github.com/quokkify/project-toolkit/issues/163)) ([a64f31d](https://github.com/quokkify/project-toolkit/commit/a64f31d1458ece4685c71a229902ee053c3dfe4f))
* **deps:** update quokkify/project-toolkit to v2.12.4 ([#166](https://github.com/quokkify/project-toolkit/issues/166)) ([7c7f2eb](https://github.com/quokkify/project-toolkit/commit/7c7f2eb6db6856d9069d696faf4738651b5af1b4))
* **deps:** update quokkify/project-toolkit to v2.14.0 ([#167](https://github.com/quokkify/project-toolkit/issues/167)) ([7bdc88c](https://github.com/quokkify/project-toolkit/commit/7bdc88c77feb91ed86b6ed97321132b65a97d960))
* **deps:** update renovate to v44.50.3 ([#168](https://github.com/quokkify/project-toolkit/issues/168)) ([be1ab05](https://github.com/quokkify/project-toolkit/commit/be1ab05837e71a5e633620860af207e864fff9b0))

## [2.14.0](https://github.com/quokkify/project-toolkit/compare/v2.13.0...v2.14.0) (2026-08-28)


### ✨ Features

* **deps:** update actions/setup-java action to v6 ([#160](https://github.com/quokkify/project-toolkit/issues/160)) ([e15bbed](https://github.com/quokkify/project-toolkit/commit/e15bbed541f0ede907009fa4e3dd886eccb8aa34))


### ⚙️ CI

* add emoji changelog sections ([#158](https://github.com/quokkify/project-toolkit/issues/158)) ([2f24d16](https://github.com/quokkify/project-toolkit/commit/2f24d1618b36fa6734b3f120f72c6c1002928f9b))


### 🧹 Chores

* **deps:** update actions/download-artifact to v8 ([#157](https://github.com/quokkify/project-toolkit/issues/157)) ([575ec41](https://github.com/quokkify/project-toolkit/commit/575ec41bacf7f499d719ebb1b6a0ad5a87640a5e))
* **deps:** update copier to v9.17.2 ([#137](https://github.com/quokkify/project-toolkit/issues/137)) ([789159a](https://github.com/quokkify/project-toolkit/commit/789159af62f9ff737f2e0d7db97bbdaed54ee1a6))
* **deps:** update github actions non-major updates ([#155](https://github.com/quokkify/project-toolkit/issues/155)) ([60aa749](https://github.com/quokkify/project-toolkit/commit/60aa74968fecc586ef6442b6e0872a2902d4be3b))
* **deps:** update renovate to v44.42.0 ([#153](https://github.com/quokkify/project-toolkit/issues/153)) ([f0b3d79](https://github.com/quokkify/project-toolkit/commit/f0b3d795ca479e3e3da2c949b2fab22f8cdae5e7))
* **deps:** update renovate to v44.42.1 ([#154](https://github.com/quokkify/project-toolkit/issues/154)) ([c0828a5](https://github.com/quokkify/project-toolkit/commit/c0828a57a517b13eb96cbd4f6e351f238c9fe1f4))
* **deps:** update renovate to v44.49.1 ([#156](https://github.com/quokkify/project-toolkit/issues/156)) ([42d7c09](https://github.com/quokkify/project-toolkit/commit/42d7c0972b198f1144aed91eac7e2718c00f80cc))

## [2.13.0](https://github.com/quokkify/project-toolkit/compare/v2.12.4...v2.13.0) (2026-08-28)


### Features

* **compose-up:** support quiet compose pulls ([#152](https://github.com/quokkify/project-toolkit/issues/152)) ([685f139](https://github.com/quokkify/project-toolkit/commit/685f139130e857513dcf3b42baa810f33010c1e2))


### Bug Fixes

* recognize custom Allure audit layouts ([#150](https://github.com/quokkify/project-toolkit/issues/150)) ([cc2cadf](https://github.com/quokkify/project-toolkit/commit/cc2cadfcb033f3ccaa2957f0f498676aba50bc25))

## [2.12.4](https://github.com/quokkify/project-toolkit/compare/v2.12.3...v2.12.4) (2026-08-27)


### Bug Fixes

* update Allure action to v0.4.1 ([#148](https://github.com/quokkify/project-toolkit/issues/148)) ([9a3c32e](https://github.com/quokkify/project-toolkit/commit/9a3c32e7e3eea9481fb0595392a108465a606025))

## [2.12.3](https://github.com/quokkify/project-toolkit/compare/v2.12.2...v2.12.3) (2026-08-25)


### Bug Fixes

* preserve trusted Allure compact comment content ([e138033](https://github.com/quokkify/project-toolkit/commit/e13803375369b08f395c43f9dd453702de8107f6))

## [2.12.2](https://github.com/quokkify/project-toolkit/compare/v2.12.1...v2.12.2) (2026-08-25)


### Bug Fixes

* **actions:** propagate Allure report v0.3.0 ([#143](https://github.com/quokkify/project-toolkit/issues/143)) ([308a02c](https://github.com/quokkify/project-toolkit/commit/308a02cd35c2f61728368643264b9b478b9e1b77))
* **ci:** add install-command for python components with allure_report ([#140](https://github.com/quokkify/project-toolkit/issues/140)) ([f6eb9ef](https://github.com/quokkify/project-toolkit/commit/f6eb9ef739255ee5bf7f66d61a9700c6496ca8af))
* pin copier fleet audit workflow ([#121](https://github.com/quokkify/project-toolkit/issues/121)) ([1f6c137](https://github.com/quokkify/project-toolkit/commit/1f6c1378f2dd7cadf32d398e4f4de5c82bf015f7))
* **validate:** handle unreadable copier.yml ([#123](https://github.com/quokkify/project-toolkit/issues/123)) ([baf0aab](https://github.com/quokkify/project-toolkit/commit/baf0aab9b5ce68a5e277df5efb56086b5e0b054a))

## [2.12.1](https://github.com/quokkify/project-toolkit/compare/v2.12.0...v2.12.1) (2026-08-11)


### Bug Fixes

* **actions:** update Allure report action ([#114](https://github.com/quokkify/project-toolkit/issues/114)) ([18d4ec6](https://github.com/quokkify/project-toolkit/commit/18d4ec65143bda06cd6629683fc806b6b824c721))

## [2.12.0](https://github.com/quokkify/project-toolkit/compare/v2.11.1...v2.12.0) (2026-08-09)


### Features

* **actions:** forward compose lifecycle hooks ([#106](https://github.com/quokkify/project-toolkit/issues/106)) ([cb0391a](https://github.com/quokkify/project-toolkit/commit/cb0391aa5546172dca8ba10c0a7a66ef9ee510e9))

## [2.11.1](https://github.com/quokkify/project-toolkit/compare/v2.11.0...v2.11.1) (2026-08-08)


### Bug Fixes

* **allure:** harden generated workflow inputs ([#99](https://github.com/quokkify/project-toolkit/issues/99)) ([0e8adfb](https://github.com/quokkify/project-toolkit/commit/0e8adfbb5cced488e281cbfe180e2a1a04f755b1))

## [2.11.0](https://github.com/quokkify/project-toolkit/compare/v2.10.1...v2.11.0) (2026-08-08)


### Features

* **allure:** support external workflow artifacts ([#98](https://github.com/quokkify/project-toolkit/issues/98)) ([cb1357e](https://github.com/quokkify/project-toolkit/commit/cb1357e29a77075d2168e2a1cbd375f0a45a1aff))


### Bug Fixes

* **fleet:** align Copier release answers ([#94](https://github.com/quokkify/project-toolkit/issues/94)) ([6b171ce](https://github.com/quokkify/project-toolkit/commit/6b171cea17b7e2d4e4798380b4a75fe36aaabb52))

## [2.10.1](https://github.com/quokkify/project-toolkit/compare/v2.10.0...v2.10.1) (2026-08-06)


### Bug Fixes

* **allure:** update report action to v0.2.1 ([#91](https://github.com/quokkify/project-toolkit/issues/91)) ([9e0c1a6](https://github.com/quokkify/project-toolkit/commit/9e0c1a62551b22b8a8b161a17d9174f7d801b3d2))

## [2.10.0](https://github.com/quokkify/project-toolkit/compare/v2.9.1...v2.10.0) (2026-08-06)


### Features

* add Copier Allure reporting to project template ([#84](https://github.com/quokkify/project-toolkit/issues/84)) ([e3e384d](https://github.com/quokkify/project-toolkit/commit/e3e384db947cbead8b79c4219d95f25bbac81a5c))

## [2.9.1](https://github.com/quokkify/project-toolkit/compare/v2.9.0...v2.9.1) (2026-08-06)


### Bug Fixes

* **allure:** update report action to v0.2.0 ([#85](https://github.com/quokkify/project-toolkit/issues/85)) ([2abc6f9](https://github.com/quokkify/project-toolkit/commit/2abc6f9b8dcdc8c5d513702c15e78ef47b6831b5))

## [2.9.0](https://github.com/quokkify/project-toolkit/compare/v2.8.2...v2.9.0) (2026-08-06)


### Features

* report Copier template inventory ([#79](https://github.com/quokkify/project-toolkit/issues/79)) ([7f874b2](https://github.com/quokkify/project-toolkit/commit/7f874b24f59aad334613223cc4b6f979770328ef))


### Bug Fixes

* canonicalize Copier template source URLs ([#71](https://github.com/quokkify/project-toolkit/issues/71)) ([388e35f](https://github.com/quokkify/project-toolkit/commit/388e35f7b7fefbe408beb8ed97dc5a4f1df9ce5d))
* preserve Copier answers formatting during audit ([#73](https://github.com/quokkify/project-toolkit/issues/73)) ([be4e244](https://github.com/quokkify/project-toolkit/commit/be4e2445139d5798b6fc677e21664aa55d728a40))

## [2.8.2](https://github.com/quokkify/project-toolkit/compare/v2.8.1...v2.8.2) (2026-08-03)


### Bug Fixes

* harden generated project automation workflows ([#69](https://github.com/quokkify/project-toolkit/issues/69)) ([10000c3](https://github.com/quokkify/project-toolkit/commit/10000c3057166ca7be5b47348acb5fe34d3fb354))

## [2.8.1](https://github.com/quokkify/project-toolkit/compare/v2.8.0...v2.8.1) (2026-08-03)


### Bug Fixes

* exclude non-consumer repositories from Copier audit ([#66](https://github.com/quokkify/project-toolkit/issues/66)) ([123167f](https://github.com/quokkify/project-toolkit/commit/123167fede66543fe4ca91d206e60a8bf3aa34ca))

## [2.8.0](https://github.com/quokkify/project-toolkit/compare/v2.7.2...v2.8.0) (2026-08-03)


### Features

* automate Copier fleet updates ([#64](https://github.com/quokkify/project-toolkit/issues/64)) ([784b675](https://github.com/quokkify/project-toolkit/commit/784b67579e9fae07ffbaf3b0eec1f557fe2aa4c1))

## [2.7.2](https://github.com/quokkify/project-toolkit/compare/v2.7.1...v2.7.2) (2026-08-02)


### Bug Fixes

* **actions:** support Allure installation tokens ([#61](https://github.com/quokkify/project-toolkit/issues/61)) ([7b7b82c](https://github.com/quokkify/project-toolkit/commit/7b7b82c1c39513b4523d61e3a186c12175cf2e20))

## [2.7.1](https://github.com/quokkify/project-toolkit/compare/v2.7.0...v2.7.1) (2026-08-02)


### Bug Fixes

* **actions:** update secure Allure reporter ([#59](https://github.com/quokkify/project-toolkit/issues/59)) ([b61eb85](https://github.com/quokkify/project-toolkit/commit/b61eb8506769dbe1e2787a0d93fcbbad8800b688))

## [2.7.0](https://github.com/quokkify/project-toolkit/compare/v2.6.0...v2.7.0) (2026-08-02)


### Features

* **actions:** add Allure report action ([#57](https://github.com/quokkify/project-toolkit/issues/57)) ([e09af98](https://github.com/quokkify/project-toolkit/commit/e09af98bff6783e81f92dc526f20290de674c266))

## [2.6.0](https://github.com/quokkify/project-toolkit/compare/v2.5.3...v2.6.0) (2026-08-02)


### Features

* **ci:** split validation jobs and add CodeQL ([#49](https://github.com/quokkify/project-toolkit/issues/49)) ([cedeea9](https://github.com/quokkify/project-toolkit/commit/cedeea98dd085ce8496202fd0eec141e28938640))
* wire gh-pages subdirectory compatibility wrapper to immutable standalone action ([#55](https://github.com/quokkify/project-toolkit/issues/55)) ([5bd0355](https://github.com/quokkify/project-toolkit/commit/5bd03558151e7d8159b94d3a3cff12642760f000))


### Bug Fixes

* **security:** resolve CodeQL validation alerts ([#51](https://github.com/quokkify/project-toolkit/issues/51)) ([a3a6978](https://github.com/quokkify/project-toolkit/commit/a3a697891447e09fc5e778a0e72c271a6a1cc8b8))

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
