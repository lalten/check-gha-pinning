import pathlib
import re
import sys
import ruamel.yaml
import subprocess

IGNORE_PRAGMA = "noqa: gha-pinning"

_SHA256 = re.compile(r"\b[a-fA-F0-9]{64}\b")
_SHA1 = re.compile(r"\b[a-f0-9]{40}\b")


class _RefNotFound(RuntimeError):
    pass


def _get_commit_for_tag(action: str, tag: str) -> str:
    cmd = ["git", "ls-remote", "--exit-code", f"https://github.com/{action}", tag]
    try:
        return subprocess.check_output(cmd, text=True).split("\t")[0]
    except subprocess.CalledProcessError as ex:
        if ex.returncode == 2:
            raise _RefNotFound(f"Tag {tag} not found for {action}")
        raise


def _check(line: str) -> str | None:
    if "@" not in line:
        return  # local actions (./path) don't use @ versions.
    if line.startswith("docker://"):
        if "sha256:" not in line or not re.match(_SHA256, line.split("sha256:")[1]):
            return f"{line} does not have a valid sha256 hash"
        return None
    if not re.match(_SHA1, line.split("@")[1]):
        try:
            hash = _get_commit_for_tag(*line.split("@"))
        except _RefNotFound as ex:
            return str(ex)
        return f"{line} is pinned to a tag, not a commit hash. Suggest using {hash}"


def check_pinning(file: pathlib.Path) -> list[str]:
    try:
        workflow = ruamel.yaml.YAML().load(file)
    except ruamel.yaml.YAMLError as ex:
        return [f"Error parsing yaml: {ex}"]
    try:
        jobs = workflow.get("jobs", {})
    except AttributeError:
        return []  # yaml is not a mapping on top level

    uses = []
    for _, job in jobs.items():
        if u := job.get("uses"):
            if IGNORE_PRAGMA not in job.ca:
                uses.append(u)
        for step in job.get("steps", []):
            if u := step.get("uses"):
                if IGNORE_PRAGMA not in step.ca:
                    uses.append(u)
    return [problem for u in uses if (problem := _check(u))]


def main() -> int:
    paths = sys.argv[1:]
    if not paths or sys.argv[1] in ("-h", "--help"):
        print(f"Usage: {__file__} <file1> <file2> ... <fileN>")
        sys.exit(1)

    files = []
    for path in paths:
        p = pathlib.Path(path)
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files.extend(f for f in p.rglob("*") if f.is_file())
    files = list(set(files))

    fail = False
    for file in files:
        if problems := check_pinning(file):
            fail = True
            print(f"Problems in {file}:")
            print("\n".join(problems))
            print()

    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
