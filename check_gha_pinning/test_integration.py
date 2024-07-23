import pathlib
from unittest.mock import patch

import pytest
from github import Github
from github.GithubException import GithubException
from github.Repository import Repository
from github.Tag import Tag

from check_gha_pinning import check_pinning


@pytest.mark.integration
@patch("os.environ", {"GHA_PINNING_SKIP_GIT_CHECK": "1"})
def test_integration_no_git_remote(tmp_path: pathlib.Path):
    d = tmp_path / "no-git-remote"
    d.mkdir()
    workflow = d / "test.yml"
    workflow.write_text("""\
jobs:
  some_job:
    steps:
      - uses: actions/checkout@v4
      - uses: actions/checkout@v4 # noqa: gha-pinning
      - uses: actions/checkout@aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d # v4.1.2-example
      - uses: docker://something@latest
      - uses: docker://something@latest # noqa: gha-pinning
      - uses: docker://something@sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
""")
    result = check_pinning(workflow)
    assert set(result) == {
        f"{workflow}:4: actions/checkout@v4 is not pinned to commit",
        f"{workflow}:7: docker://something@latest is not pinned to sha256",
    }


@pytest.mark.integration
def test_integration_empty_yaml_file(tmp_path: pathlib.Path):
    d = tmp_path / "empty-yaml-file"
    d.mkdir()
    workflow = d / "test.yml"
    workflow.write_text("")
    assert check_pinning(workflow) == []


def _get_most_specific_tag_from_tag(repo: str, tag: str) -> Tag:
    g = Github()
    try:
        repo: Repository = g.get_repo(repo)
    except GithubException as e:
        raise pytest.fail(f"Failed to get repo: {e}")
    assert repo
    try:
        tag_data = repo.get_git_ref(f"tags/{tag}")
    except GithubException as e:
        raise pytest.fail(f"Failed to get tag: {e}")
    assert tag_data
    tag_sha = tag_data.object.sha
    try:
        all_tags = repo.get_tags()
    except GithubException as e:
        raise pytest.fail(f"Failed to get tags: {e}")
    assert all_tags

    tags_for_sha = filter(lambda t: t.commit.sha == tag_sha, all_tags)
    return max(tags_for_sha, key=lambda t: len(t.name))


@pytest.mark.integration
def test_integration_git_remote(tmp_path: pathlib.Path):
    repo = "actions/checkout"
    tag = "v4"

    d = tmp_path / "with-git-remote"
    d.mkdir()
    workflow = d / "test.yml"
    workflow.write_text(f"""\
jobs:
  some_job:
    steps:
      - uses: {repo}@{tag}
      - uses: {repo}@aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d
""")
    check_tag = _get_most_specific_tag_from_tag(repo, tag)
    result = check_pinning(workflow)
    assert set(result) == {
        f"{workflow}:4: {repo}@{tag} is not pinned to commit (should be {check_tag.commit.sha} # {check_tag.name})"
    }


def test_integration_git_remote_tagged_to_sha(tmp_path: pathlib.Path):
    d = tmp_path / "tagged-to-sha"
    d.mkdir()
    workflow = d / "test.yml"
    workflow.write_text("""\
jobs:
  some_job:
    steps:
      - uses: actions/checkout@aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d
""")
    assert check_pinning(workflow) == []
