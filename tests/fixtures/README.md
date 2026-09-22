# GitHub ruleset request schema fixture

`github_ruleset_request_schema_2022-11-28.json` is an offline, faithful extraction of the request-body constraints used by the GitHub REST repository-ruleset create and update endpoints (`POST /repos/{owner}/{repo}/rulesets` and `PUT /repos/{owner}/{repo}/rulesets/{ruleset_id}`).

Provenance:

- API version: `2022-11-28`
- Upstream source: `https://github.com/github/rest-api-description/blob/4d0b8391b66a2178f27e082a940f82fb14d7feb9a3f183a7328f3d1d81f48ede/descriptions/api.github.com/api.github.com.2022-11-28.json`
- Fixture scope: all fields and rule variants emitted or preserved by `scripts/reconcile_ruleset.py`, including required pull-request parameters, code-scanning thresholds, and the optional integer `integration_id`.
- Fixture SHA-256: `7dd56f6ade037baeb13faf4555d6a40d629d36e7dd764ef15ad4f37041c7175d`
- Tests intentionally perform no network access; the fixture is loaded from this directory.

The fixture is reviewed as a versioned contract. Update the upstream commit, fixture, and this provenance record together when GitHub changes the API schema.
