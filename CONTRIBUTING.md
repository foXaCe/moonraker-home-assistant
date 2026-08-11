# Contributing

Thank you for your interest in Moonraker Home Assistant!

## Bug reports

Use the [bug report template](https://github.com/foXaCe/moonraker-home-assistant/issues/new?template=bug_report.yml).

## Feature requests

Use the [feature request template](https://github.com/foXaCe/moonraker-home-assistant/issues/new?template=feature_request.yml).

## Pull requests

1. Fork the repository
2. Create a dedicated branch: `git checkout -b feat/my-feature`
3. Set up the environment: `scripts/setup`
4. Code + tests: `scripts/test_strict`
5. Lint: `scripts/lint`
6. Run all checks before pushing: `scripts/prepush`
7. Commit using [conventional commits](https://www.conventionalcommits.org/) (`feat: …`, `fix: …`) — releases and the changelog are generated automatically by release-please from commit messages
8. Push and open a PR against `main`

## Local setup

```bash
scripts/setup
```

This installs the Python requirements and the pre-commit hooks via [prek](https://github.com/j178/prek) (a fast drop-in replacement for pre-commit — `pipx install pre-commit` works too if you prefer the Python version).

A [devcontainer](.devcontainer/) is also available for VS Code.

## Dependency management

This repository uses **Renovate**. Update PRs are opened by `@renovate[bot]`; patch updates are auto-merged once CI passes.

## Releases

Releases are managed by [release-please](https://github.com/googleapis/release-please): a release PR is maintained automatically from conventional commits, and merging it publishes the tag, the GitHub release and bumps `manifest.json` / `const.py`.
