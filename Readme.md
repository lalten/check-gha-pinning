# check-gha-pinning

[![CI status](https://img.shields.io/github/actions/workflow/status/lalten/check-gha-pinning/ci.yml?branch=main)](https://github.com/lalten/check-gha-pinning/actions)
[![MIT License](https://img.shields.io/github/license/lalten/check-gha-pinning)](https://github.com/lalten/check-gha-pinning/blob/main/LICENSE)

Tool and [pre-commit](https://pre-commit.com) hook to check if a GitHub Actions workflow file is pinned to a specific commit hash of an action.

## Usage

Add the following to your `.pre-commit-config.yaml`:

```yaml
- repo: https://github.com/lalten/check-gha-pinning
  rev: v1.0.0  # or whatever is the latest version
  hooks:
  - id: check-gha-pinning
```

If a GitHub Actions Workflow is `using` an action without a commit hash, the hook will fail like this:
```
Problems in .github/workflows/ci.yml:
actions/checkout@v4.1.1 is not pinned to a commit hash
```

## Configuration

You can ignore the pinning of some actions by adding a `noqa: gha-pinning` comment on the uses line.
Example:
```yaml
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4.1.1  # noqa: gha-pinning
    - uses: actions/setup-python@0a5c61591373683505ea898e09a3ea4f39ef2b9c  # v5.0.0
```

By default the hook will check yaml files in `.github/workflows` (see [.pre-commit-hooks.yaml](.pre-commit-hooks.yaml)).
You can override this by setting the `files` parameter of the hook.
