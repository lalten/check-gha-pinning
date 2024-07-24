import subprocess
import sys
from contextlib import nullcontext as does_not_raise
from unittest.mock import MagicMock, call, patch

import pytest
import ruamel.yaml

from check_gha_pinning import (
    ActionTagsBySha,
    ActionTagsByTag,
    _build_github_url,
    _check,
    _get_action_tags,
    _NotPinnedToCommitError,
    _RepoHasNoTagsError,
    _RepoNotFoundError,
    _UnpinnedContainerError,
    check_pinning,
)
from check_gha_pinning import (
    main as check_gha_pinning_main,
)


def _build_ls_remote_output(by_sha: ActionTagsBySha) -> str:
    return "\n".join([f"{sha}\trefs/tags/{tag}" for sha, tags in by_sha.items() for tag in tags])


def _build_by_tags_from_by_sha(by_sha: ActionTagsBySha) -> ActionTagsByTag:
    return {tag: sha for sha, tags in by_sha.items() for tag in tags}


@pytest.mark.parametrize(
    "action, expected",
    [
        ("actions/checkout", "https://github.com/actions/checkout"),
        ("actions/checkout@v4", "https://github.com/actions/checkout"),
        ("actions/checkout@aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d", "https://github.com/actions/checkout"),
        ("actions/something/else@v4", "https://github.com/actions/something"),
    ],
)
def test_build_github_url(action: str, expected: str):
    assert _build_github_url(action) == expected


def test_build_github_url_invalid():
    with pytest.raises(AttributeError):
        _build_github_url("invalid")


@patch("subprocess.check_output")
def test_get_action_tags_success(mock_check_output: MagicMock):
    action = "example/repo"
    repo_url = _build_github_url(action)

    expected_by_sha = {
        "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d": ["v3", "v3.1", "v3.1.5"],
        "7c211433f02071597741e6ff5a8ea34789abbf43": ["v2"],
    }
    expected_by_tag = _build_by_tags_from_by_sha(expected_by_sha)
    mock_check_output.return_value = _build_ls_remote_output(expected_by_sha)

    by_tag, by_sha = _get_action_tags(action)
    for tag, sha in expected_by_tag.items():
        assert tag in by_tag.keys()
        assert sha == by_tag.pop(tag)
    assert not by_tag

    for sha, tags in expected_by_sha.items():
        assert sha in by_sha.keys()
        assert set(tags) == set(by_sha.pop(sha))
    assert not by_sha

    mock_check_output.assert_called_once_with(["git", "ls-remote", "--tags", "--exit-code", repo_url], text=True)


@patch("subprocess.check_output")
def test_get_action_tags_repo_has_no_tags(mock_check_output: MagicMock):
    action = "example/repo"
    repo_url = _build_github_url(action)
    mock_check_output.return_value = ""
    with pytest.raises(_RepoHasNoTagsError) as cm:
        _get_action_tags(action)
    assert str(cm.value) == f"repo {repo_url} has no tags"
    mock_check_output.assert_called_once_with(["git", "ls-remote", "--tags", "--exit-code", repo_url], text=True)


@patch("subprocess.check_output")
def test_get_action_tags_repo_not_found(mock_check_output: MagicMock):
    action = "example/repo"
    repo_url = _build_github_url(action)
    mock_check_output.side_effect = subprocess.CalledProcessError(
        128, cmd=["git", "ls-remote", "-t", "--exit-code", repo_url]
    )
    with pytest.raises(_RepoNotFoundError) as cm:
        _get_action_tags(action)
    assert str(cm.value) == f"repo {repo_url} not found"
    mock_check_output.assert_called_once_with(["git", "ls-remote", "--tags", "--exit-code", repo_url], text=True)


@patch("subprocess.check_output")
def test_get_action_tags_other_error(mock_check_output: MagicMock):
    action = "example/repo"
    repo_url = _build_github_url(action)
    mock_check_output.side_effect = subprocess.CalledProcessError(
        1, cmd=["git", "ls-remote", "-t", "--exit-code", repo_url]
    )
    with pytest.raises(subprocess.CalledProcessError):
        _get_action_tags(action)
    mock_check_output.assert_called_once_with(["git", "ls-remote", "--tags", "--exit-code", repo_url], text=True)


@pytest.mark.parametrize(
    "line, expectation",
    [
        ("./path", does_not_raise()),
        ("docker://image@sha256:5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03", does_not_raise()),
        ("docker://image@sha256:not_a_hash", pytest.raises(_UnpinnedContainerError)),
        ("actions/checkout@f572d396fae9206628714fb2ce00f72e94f2258f", does_not_raise()),
        ("actions/checkout@v4.1.1", pytest.raises(_NotPinnedToCommitError)),
        ("actions/checkout@main", pytest.raises(_NotPinnedToCommitError)),
    ],
)
def test__check(line, expectation):
    with expectation:
        _check(line)


def test_check_pinning_empty_file():
    file = MagicMock()
    with patch("ruamel.yaml.YAML.load", return_value=None):
        assert check_pinning(file) == []


def test_check_pinning_yaml_parsing_failure():
    file = MagicMock()
    with patch("ruamel.yaml.YAML.load", side_effect=ruamel.yaml.YAMLError("Parsing error")):
        assert check_pinning(file) == ["Error parsing yaml: Parsing error"]


def test_check_pinning_yaml_parsing_success_no_jobs():
    file = MagicMock()
    file_contents = {"some_key": "some_value"}
    with patch("ruamel.yaml.YAML.load", return_value=file_contents):
        assert check_pinning(file) == []


@pytest.mark.parametrize(
    "action, check_exception, expected",
    [
        ("valid_action", None, None),
        ("unpinned_action # noqa: gha-pinning", None, None),
        ("unpinned_container", _UnpinnedContainerError(), "unpinned_container is not pinned to sha256"),
        ("unpinned_action", _NotPinnedToCommitError(), "unpinned_action is not pinned to commit"),
    ],
)
@patch("check_gha_pinning._check")
@patch("os.environ", {"GHA_PINNING_SKIP_GIT_CHECK": "1"})
def test_check_pinning_success_no_github_check(
    mock__check: MagicMock,
    action: str,
    check_exception: Exception,
    expected: str,
):
    file = MagicMock()
    file_path = ".github/workflows/test.yaml"
    file.__str__.return_value = file_path
    yaml = ruamel.yaml.YAML()
    yaml_str = f"""\
jobs:
  some_job:
    steps:
      - uses: {action}
"""
    if check_exception:
        mock__check.side_effect = check_exception
    with patch("ruamel.yaml.YAML.load", return_value=yaml.load(yaml_str)):
        check = check_pinning(file)
        if expected:
            assert len(check) == 1
            problem: str = check.pop(0)
            assert problem.startswith(f"{file_path}:4:")
            assert expected in problem
        assert not check


@patch("check_gha_pinning._check")
@patch("check_gha_pinning._get_action_tags")
def test_check_pinning_success_github_check(
    mock__get_action_tags: MagicMock,
    mock__check: MagicMock,
):
    file = MagicMock()
    file_path = ".github/workflows/test.yaml"
    file.__str__.return_value = file_path
    yaml = ruamel.yaml.YAML()

    action = "invalid_action@v3"
    yaml_str = f"""\
jobs:
  some_job:
    steps:
      - uses: {action}
"""
    mock__check.side_effect = _NotPinnedToCommitError()

    by_sha = {
        "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d": ["v3", "v3.1", "v3.1.5"],
    }
    by_tag = _build_by_tags_from_by_sha(by_sha)
    mock__get_action_tags.return_value = (by_tag, by_sha)
    with patch("ruamel.yaml.YAML.load", return_value=yaml.load(yaml_str)):
        assert check_pinning(file) == [
            f".github/workflows/test.yaml:4: {action} is not pinned to commit (should be aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d # v3.1.5)"
        ]


@patch("check_gha_pinning._check")
@patch("check_gha_pinning._get_action_tags")
def test_check_pinning_ref_not_found(
    mock__get_action_tags: MagicMock,
    mock__check: MagicMock,
):
    file = MagicMock()
    file_path = ".github/workflows/test.yaml"
    file.__str__.return_value = file_path
    yaml = ruamel.yaml.YAML()
    yaml_str = """\
jobs:
  some_job:
    steps:
      - uses: actions/checkout@v2
"""
    mock__check.side_effect = _NotPinnedToCommitError()

    by_sha = {
        "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d": ["v3", "v3.1", "v3.1.5"],
    }
    by_tag = _build_by_tags_from_by_sha(by_sha)
    mock__get_action_tags.return_value = (by_tag, by_sha)

    with patch("ruamel.yaml.YAML.load", return_value=yaml.load(yaml_str)):
        assert check_pinning(file) == [".github/workflows/test.yaml:4: actions/checkout@v2: tag v2 not found"]


@patch("check_gha_pinning._check")
@patch("check_gha_pinning._get_action_tags")
def test_check_pinning_repo_not_found(
    mock__get_action_tags: MagicMock,
    mock__check: MagicMock,
):
    file = MagicMock()
    file_path = ".github/workflows/test.yaml"
    file.__str__.return_value = file_path
    yaml = ruamel.yaml.YAML()
    yaml_str = """\
jobs:
  some_job:
    steps:
      - uses: actions/checkout@v2
"""
    mock__check.side_effect = _RepoNotFoundError()

    by_sha = {
        "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d": ["v3", "v3.1", "v3.1.5"],
    }
    by_tag = _build_by_tags_from_by_sha(by_sha)
    mock__get_action_tags.return_value = (by_tag, by_sha)

    with patch("ruamel.yaml.YAML.load", return_value=yaml.load(yaml_str)):
        assert check_pinning(file) == [".github/workflows/test.yaml:4: actions/checkout@v2: repo not found"]


@patch("pathlib.Path")
@patch("check_gha_pinning.check_pinning")
def test_main_success_no_args_no_files(mock_check_pinning: MagicMock, mock_path: MagicMock):
    mock_path.return_value.is_file.return_value = False
    mock_path.return_value.is_dir.return_value = True
    mock_path.return_value.rglob.return_value = []
    with patch.object(sys, "argv", ["check_gha_pinning"]):
        mock_check_pinning.return_value = []
        assert check_gha_pinning_main() == 0

        mock_check_pinning.assert_not_called()
        mock_path.assert_called_with(".github/workflows")


@patch("pathlib.Path")
def test_main_success_args_files(mock_path: MagicMock):
    mock_path.return_value.is_file.return_value = True
    mock_path.return_value.is_dir.return_value = False
    mock_path.return_value.__hash__.side_effect = [1, 2]
    with patch.object(sys, "argv", ["check_gha_pinning", "file1", "file2"]):
        with patch("check_gha_pinning.check_pinning") as mock_check_pinning:
            mock_check_pinning.return_value = []
            assert check_gha_pinning_main() == 0
            mock_path.assert_has_calls([call("file1"), call("file2")], any_order=True)

            mock_check_pinning.assert_called()
            assert mock_check_pinning.call_count == 2


def test_main_success_args_dirs():
    with patch("pathlib.Path") as mock_file:
        mock_file.return_value.is_file.return_value = True
        mock_file.return_value.__hash__.side_effect = [1, 2, 3, 4]
        with patch("pathlib.Path") as mock_path:
            mock_path.return_value.is_file.return_value = False
            mock_path.return_value.is_dir.return_value = True
            mock_path.return_value.rglob.side_effect = [
                [mock_file("file1"), mock_file("file2")],
                [mock_file("file3"), mock_file("file4")],
            ]
            with patch.object(sys, "argv", ["check_gha_pinning", "dir1", "dir2"]):
                with patch("check_gha_pinning.check_pinning") as mock_check_pinning:
                    mock_check_pinning.return_value = []
                    assert check_gha_pinning_main() == 0
                    mock_path.assert_has_calls([call("dir1"), call("dir2")], any_order=True)
                    mock_file.assert_has_calls(
                        [call("file1"), call("file2"), call("file3"), call("file4")], any_order=True
                    )

                    mock_check_pinning.assert_called()
                    assert mock_check_pinning.call_count == 4


@patch("builtins.print")
@patch("pathlib.Path")
@patch("check_gha_pinning.check_pinning")
def test_main_success_args_file_with_problems(
    mock_check_pinning: MagicMock, mock_file: MagicMock, mock_print: MagicMock
):
    mock_file.return_value.is_file.return_value = True
    with patch.object(sys, "argv", ["check_gha_pinning", "file1"]):
        mock_check_pinning.return_value = ["line1", "line2"]
        assert check_gha_pinning_main() == 1

        mock_check_pinning.assert_called()
        mock_print.assert_called()
        mock_print.assert_called_once_with("line1\nline2")
