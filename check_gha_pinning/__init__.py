import os
import pathlib
import re
import subprocess
import sys
from typing import NamedTuple

import ruamel.yaml
import ruamel.yaml.comments

IGNORE_PRAGMA = "noqa: gha-pinning"

_SHA256 = re.compile(r"\b[a-fA-F0-9]{64}\b")
_SHA1 = re.compile(r"\b[a-f0-9]{40}\b")
_REPO = re.compile(r"^[a-zA-Z0-9-]+/[a-zA-Z0-9-]+\b")
_TAG_REF = re.compile(r"^refs/tags/([a-zA-Z0-9-\.]+)$")


class GHAPinningError(RuntimeError):
    """Base class for all errors raised by this module."""


class _RefNotFoundError(GHAPinningError):
    """Git ref is not found by `git ls-remote`."""


class _RepoNotFoundError(GHAPinningError):
    """GitHub repo is not found."""


class _RepoHasNoTagsError(GHAPinningError):
    """GitHub repo has no tags."""


class _UnpinnedContainerError(GHAPinningError):
    """Container is not pinned to a sha256 hash."""


class _NotPinnedToCommitError(GHAPinningError):
    """Action is not pinned to a SHA1 commit hash."""


def _build_github_url(action: str) -> str:
    repo = re.match(_REPO, action)
    return f"https://github.com/{repo.group()}"


ActionTagsByTag = dict[str, str]
ActionTagsBySha = dict[str, list[str]]


class ActionTags(NamedTuple):
    by_tag: ActionTagsByTag
    by_sha: ActionTagsBySha


def _get_action_tags(action: str) -> ActionTags:
    repo_url = _build_github_url(action)
    cmd = ["git", "ls-remote", "--tags", "--exit-code", repo_url]
    by_tag: ActionTagsByTag = {}
    by_sha: ActionTagsBySha = {}
    try:
        lines = subprocess.check_output(cmd, text=True).splitlines()
        if not lines:
            raise _RepoHasNoTagsError(f"repo {repo_url} has no tags")
        for line in lines:
            sha, ref = line.split("\t")
            match = re.match(_TAG_REF, ref)
            if match:
                by_tag[match.group(1)] = sha
                if sha not in by_sha:
                    by_sha[sha] = [match.group(1)]
                else:
                    by_sha[sha].append(match.group(1))
        return by_tag, by_sha
    except subprocess.CalledProcessError as ex:
        if ex.returncode == 2:
            raise _RepoHasNoTagsError(f"repo {repo_url} has no tags") from ex
        elif ex.returncode == 128:
            raise _RepoNotFoundError(f"repo {repo_url} not found") from ex
        raise


def _check(line: str) -> None:
    if "@" not in line:
        return  # local actions (./path) don't use @ versions.
    if line.startswith("docker://"):
        if "sha256:" not in line or not re.match(_SHA256, line.split("sha256:")[1]):
            raise _UnpinnedContainerError()
    elif not re.match(_SHA1, line.split("@")[1]):
        raise _NotPinnedToCommitError()


def check_pinning(file: pathlib.Path) -> list[str]:
    try:
        workflow: dict = ruamel.yaml.YAML().load(file)
    except ruamel.yaml.YAMLError as ex:
        return [f"Error parsing yaml: {ex}"]

    try:
        jobs: dict = workflow.get("jobs", {})
    except AttributeError:
        return []

    uses = [job for job in jobs.values() if "uses" in job]
    for job in jobs.values():
        for step in job.get("steps", []):
            if "uses" in step:
                uses.append(step)

    problems = []
    for item in uses:
        item: ruamel.yaml.comments.CommentedMap
        action: str = item["uses"]
        if IGNORE_PRAGMA in item.ca:
            continue
        prefix = f"{file}:{item.lc.line+1}: {action}"
        try:
            _check(action)
        except _UnpinnedContainerError:
            problems.append(f"{prefix} is not pinned to sha256")
        except _NotPinnedToCommitError:
            if os.getenv("GHA_PINNING_SKIP_GIT_CHECK"):
                problems.append(f"{prefix} is not pinned to commit")
            else:
                ref = action.split("@")[1]
                try:
                    tags, shas = _get_action_tags(action)
                    hash = tags.get(ref)
                    if not hash:
                        raise _RefNotFoundError(f"tag {ref} not found")
                    tags = shas.get(hash)
                    specific_tag = max(tags, key=len)

                    problems.append(f"{prefix} is not pinned to commit (should be {hash} # {specific_tag})")
                except (_RefNotFoundError, _RepoHasNoTagsError) as ex:
                    problems.append(f"{prefix}: {ex}")
        except _RepoNotFoundError:
            problems.append(f"{prefix}: repo not found")

    return problems


def main() -> int:
    paths = sys.argv[1:] or [".github/workflows"]

    files = []
    for path in paths:
        p = pathlib.Path(path)
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files.extend(f for f in p.rglob("*") if f.is_file())
    files = list(set(files))

    if problems := sum((check_pinning(file) for file in files), []):
        print("\n".join(problems))
        return 1
    return os.EX_OK


if __name__ == "__main__":
    sys.exit(main())
