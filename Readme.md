# check-gha-pinning

[![CI status](https://img.shields.io/github/actions/workflow/status/lalten/check-gha-pinning/ci.yml?branch=main)](https://github.com/lalten/check-gha-pinning/actions)
[![MIT License](https://img.shields.io/github/license/lalten/check-gha-pinning)](https://github.com/lalten/check-gha-pinning/blob/main/LICENSE)

Tool and [pre-commit](https://pre-commit.com) hook to check if a GitHub Actions workflow file is pinned to a specific commit hash of an action.

## Usage

Add the following to your `.pre-commit-config.yaml`:

```yaml
- repo: https://github.com/lalten/check-gha-pinning
  rev: v1.1.0 # or whatever is the latest version
  hooks:
    - id: check-gha-pinning
```

If a GitHub Actions Workflow is `using` an action without a commit hash, the hook will fail like this:

```
.github/workflows/ci.yml:11: actions/checkout@v4.1.1 is not pinned to commit (should be b4ffde65f46336ab88eb53be808477a3936bae11)
```

## Configuration

You can ignore the pinning of some actions by adding a `noqa: gha-pinning` comment on the uses line.
Example:

```yaml
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4.1.1 # noqa: gha-pinning
      - uses: actions/setup-python@0a5c61591373683505ea898e09a3ea4f39ef2b9c # v5.0.0
```

By default the hook will check yaml files in `.github/workflows` (see [.pre-commit-hooks.yaml](.pre-commit-hooks.yaml)).
You can override this by setting the `files` parameter of the hook.

To disable the suggestion for the commit hashes of tag and branch pins, set the `GHA_PINNING_SKIP_GIT_CHECK` environment variable.

## References

This pre-commit hook was inspired by https://github.com/zgosalvez/github-actions-ensure-sha-pinned-actions.

Alternatives:

- https://github.com/zgosalvez/github-actions-ensure-sha-pinned-actions
- https://github.com/mheap/pin-github-action
- https://github.com/renovatebot/renovate/blob/main/docs/usage/configuration-options.md#pindigests
- https://github.com/rhysd/actionlint (does not check action pinning as of 2023-02-11)
