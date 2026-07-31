# Contributing

Use Conventional Commits, create one focused branch/PR, and keep workflows atomic. Before opening a PR run:

```console
python scripts/validate.py
actionlint .github/workflows/*.yml examples/*.yml
git diff --check
```

New third-party Actions must be pinned to a full commit SHA and covered by Renovate. Add a composite action only with evidence of repeated step-level logic. Do not create or move release tags from feature work.
