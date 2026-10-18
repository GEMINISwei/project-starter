"""`make release` 改檔之前的檢查 (`scripts/lib/release.sh`)。

發版很少跑, 檢查壞掉時多半不是報錯而是安靜地放行 (例如版號用字串比較, 0.0.9 被當成比 0.0.10 大),
要等到下一次發版出事才會發現, 所以每次 `make check` 都測一次。

git 用真的: 每個測試在 tmp_path 建一個 bare repo 當 origin, 再 clone 一份工作目錄。
全域與系統的 git 設定刻意隔開, 本機的簽章或 hook 設定不該影響結果。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
LIB = REPO_ROOT / "scripts" / "lib" / "release.sh"
BASH = shutil.which("bash") or "/bin/bash"
GIT = shutil.which("git") or "/usr/bin/git"

CHANGELOG = """# 變更紀錄

## [Unreleased]

- 新功能

## [0.0.1]

- 第一版
"""

GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def git(cwd: Path, *args: str) -> None:
    # 指令是這支測試自己給的固定值, 不是外部輸入。
    subprocess.run(  # noqa: S603
        [GIT, *args], cwd=cwd, env={**os.environ, **GIT_ENV}, check=True, capture_output=True
    )


def run(cwd: Path, command: str, *args: str) -> subprocess.CompletedProcess[str]:
    # source 的時候 common.sh 會 cd 到 repo 根, 所以之後再 cd 回測試的工作目錄。
    return subprocess.run(  # noqa: S603
        [BASH, "-c", f'source "{LIB}"; cd "$1"; shift; {command} "$@"', "_", str(cwd), *args],
        env={**os.environ, **GIT_ENV},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(origin))
    git(tmp_path, "clone", "--quiet", str(origin), str(work))
    git(work, "symbolic-ref", "HEAD", "refs/heads/main")
    (work / "CHANGELOG.md").write_text(CHANGELOG)
    git(work, "add", ".")
    git(work, "commit", "--quiet", "-m", "init")
    git(work, "push", "--quiet", "origin", "main")
    return work


def push_from_another_clone(tmp_path: Path, repo: Path, *, tag: str = "") -> None:
    other = tmp_path / "other"
    git(tmp_path, "clone", "--quiet", str(repo.parent / "origin.git"), str(other))
    git(other, "commit", "--quiet", "--allow-empty", "-m", "someone else")
    git(other, "push", "--quiet", "origin", "main")
    if tag:
        git(other, "tag", tag)
        git(other, "push", "--quiet", "origin", tag)


# ── 版號格式與比較 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("version", ["0.0.1", "0.10.0", "10.20.30"])
def test_valid_version_format_passes(tmp_path: Path, version: str) -> None:
    result = run(tmp_path, "require_version_format", version)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("version", ["", "v0.0.1", "0.0", "0.0.1.2", "0.0.1 ", "0.0.1/x", "0.0.a"])
def test_malformed_version_is_rejected(tmp_path: Path, version: str) -> None:
    result = run(tmp_path, "require_version_format", version)
    assert result.returncode != 0


@pytest.mark.parametrize("version", ["0.08.1", "01.0.0", "0.0.00"])
def test_version_with_leading_zero_is_rejected(tmp_path: Path, version: str) -> None:
    result = run(tmp_path, "require_version_format", version)
    assert result.returncode != 0


@pytest.mark.parametrize(
    ("bigger", "smaller"),
    [("0.0.10", "0.0.9"), ("0.10.0", "0.9.9"), ("1.0.0", "0.99.99"), ("0.0.1", "0.0.0")],
)
def test_version_comparison_is_numeric_per_segment(
    tmp_path: Path, bigger: str, smaller: str
) -> None:
    assert run(tmp_path, "version_gt", bigger, smaller).returncode == 0
    assert run(tmp_path, "version_gt", smaller, bigger).returncode != 0


def test_equal_version_is_not_greater(tmp_path: Path) -> None:
    assert run(tmp_path, "version_gt", "0.1.0", "0.1.0").returncode != 0


# ── CHANGELOG ─────────────────────────────────────────────────────────────────


def test_version_greater_than_current_and_not_in_changelog_passes(repo: Path) -> None:
    result = run(repo, "require_new_version", "0.0.2", "0.0.1")
    assert result.returncode == 0, result.stderr


def test_version_not_greater_than_current_is_rejected(repo: Path) -> None:
    result = run(repo, "require_new_version", "0.0.1", "0.0.1")
    assert result.returncode != 0
    assert "必須大於" in result.stderr


def test_version_already_in_changelog_is_rejected(repo: Path) -> None:
    # APP_VERSION 落後 CHANGELOG 時 (三者不同步), 比目前大的版號仍可能已經用過。
    result = run(repo, "require_new_version", "0.0.1", "0.0.0")
    assert result.returncode != 0
    assert "[0.0.1]" in result.stderr


def test_unreleased_with_entries_passes(repo: Path) -> None:
    result = run(repo, "require_unreleased_entries")
    assert result.returncode == 0, result.stderr


def test_empty_unreleased_is_rejected(repo: Path) -> None:
    (repo / "CHANGELOG.md").write_text(CHANGELOG.replace("- 新功能\n", ""))
    result = run(repo, "require_unreleased_entries")
    assert result.returncode != 0
    assert "[Unreleased]" in result.stderr


# ── git 狀態 ──────────────────────────────────────────────────────────────────


def test_clean_tree_passes(repo: Path) -> None:
    result = run(repo, "require_clean_tree")
    assert result.returncode == 0, result.stderr


def test_modified_file_is_rejected(repo: Path) -> None:
    (repo / "CHANGELOG.md").write_text(CHANGELOG + "\n- 還沒 commit\n")
    result = run(repo, "require_clean_tree")
    assert result.returncode != 0
    assert "CHANGELOG.md" in result.stderr


def test_untracked_file_is_rejected(repo: Path) -> None:
    (repo / "new.txt").write_text("x")
    result = run(repo, "require_clean_tree")
    assert result.returncode != 0
    assert "new.txt" in result.stderr


def test_main_in_sync_with_origin_passes(repo: Path) -> None:
    result = run(repo, "require_synced_main")
    assert result.returncode == 0, result.stderr


def test_branch_other_than_main_is_rejected(repo: Path) -> None:
    git(repo, "checkout", "--quiet", "-b", "feat/x")
    result = run(repo, "require_synced_main")
    assert result.returncode != 0
    assert "feat/x" in result.stderr


def test_main_behind_origin_is_rejected(tmp_path: Path, repo: Path) -> None:
    push_from_another_clone(tmp_path, repo)
    result = run(repo, "require_synced_main")
    assert result.returncode != 0
    assert "origin/main" in result.stderr


def test_main_ahead_of_origin_is_rejected(repo: Path) -> None:
    git(repo, "commit", "--quiet", "--allow-empty", "-m", "not pushed")
    result = run(repo, "require_synced_main")
    assert result.returncode != 0
    assert "origin/main" in result.stderr


def test_untagged_version_passes(repo: Path) -> None:
    result = run(repo, "require_untagged_version", "0.0.2")
    assert result.returncode == 0, result.stderr


def test_version_with_local_tag_is_rejected(repo: Path) -> None:
    git(repo, "tag", "v0.0.2")
    result = run(repo, "require_untagged_version", "0.0.2")
    assert result.returncode != 0
    assert "v0.0.2" in result.stderr


def test_tag_created_only_on_origin_is_seen_after_sync(tmp_path: Path, repo: Path) -> None:
    # GitHub 上建 release 會在遠端建 tag, 本機要經 require_synced_main 的 fetch 才看得到。
    push_from_another_clone(tmp_path, repo, tag="v0.0.2")
    git(repo, "pull", "--quiet", "--no-tags", "origin", "main")

    result = run(repo, "require_synced_main && require_untagged_version", "0.0.2")

    assert result.returncode != 0
    assert "v0.0.2" in result.stderr
