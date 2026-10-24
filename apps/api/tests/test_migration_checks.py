"""migration 只往前: 已發版的不可改寫 (`make check migrate`), 部署不可讓資料庫往回 (deploy.yml)。

兩道檢查的實作都在 `scripts/lib/migrations.sh`:

- `check_released_migrations`: 和最近的 release tag 比對, 已發版的 migration 不可修改或刪除。
  部署判斷「一致」靠的是 revision id, 改了內容而 id 不變的話, 那道檢查會誤判成一致。
- `check_migration_direction`: 主機資料庫的 revision 必須在要部署的那一版的 migration 裡。
  不在裡面就是資料庫比較新 (回滾) 或分岔: 舊版的 migrate 會找不到 revision 而失敗。

每個測試在暫存目錄建一個 git repo, 不碰這個 repo 自己的歷史。
住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REPO_ROOT = Path(__file__).resolve().parents[3]
LIBRARY = REPO_ROOT / "scripts" / "lib" / "migrations.sh"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
REAL_VERSIONS = REPO_ROOT / "apps" / "api" / "migrations" / "versions"
VERSIONS = "apps/api/migrations/versions"
BASH = shutil.which("bash") or "/bin/bash"
GIT = shutil.which("git") or "/usr/bin/git"


class Repo:
    """暫存目錄裡的 git repo, 只有 migration 目錄。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.versions = root / VERSIONS
        self.versions.mkdir(parents=True)
        self.git("init", "-q", "-b", "main")

    def env(self) -> dict[str, str]:
        return {
            "PATH": os.environ["PATH"],
            "HOME": str(self.root),
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }

    def git(self, *args: str) -> None:
        # 指令是這支測試自己給的固定值, 不是外部輸入。
        subprocess.run([GIT, *args], cwd=self.root, env=self.env(), check=True)  # noqa: S603

    def migration(self, revision: str, down: str | None, body: str = "pass") -> Path:
        path = self.versions / f"{revision}.py"
        path.write_text(
            f"revision: str = {revision!r}\n"
            f"down_revision: str | None = {down!r}\n\n\n"
            f"def upgrade() -> None:\n    {body}\n"
        )
        return path

    def commit(self, tag: str | None = None) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "change")
        if tag:
            self.git("tag", tag)

    def run(self, function: str, *args: str) -> subprocess.CompletedProcess[str]:
        # 參數是這支測試自己給的固定值, 不是外部輸入。
        return subprocess.run(  # noqa: S603
            [BASH, "-c", f'source "{LIBRARY}" && {function} "$@"', "bash", *args],
            cwd=self.root,
            env=self.env(),
            capture_output=True,
            text=True,
            check=False,
        )


def released_check(repo: Repo) -> subprocess.CompletedProcess[str]:
    return repo.run("check_released_migrations", VERSIONS)


def direction_check(repo: Repo, db_revision: str) -> subprocess.CompletedProcess[str]:
    return repo.run("check_migration_direction", VERSIONS, db_revision)


# ── 已發版的 migration 不可改寫 ───────────────────────────────────────────────


def test_check_migrate_passes_without_release_tag(tmp_path: Path) -> None:
    # 發 0.0.1 前資料庫會 reset, 可以繼續把結構變更併回初始 migration。
    repo = Repo(tmp_path)
    initial = repo.migration("aaa", None)
    repo.commit()
    initial.write_text(initial.read_text() + "# folded change\n")

    result = released_check(repo)

    assert result.returncode == 0, result.stderr


def test_check_migrate_allows_new_migration_after_release(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    repo.migration("aaa", None)
    repo.commit(tag="v0.0.1")
    repo.migration("bbb", "aaa")

    result = released_check(repo)

    assert result.returncode == 0, result.stderr


def test_check_migrate_rejects_modified_released_migration(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    initial = repo.migration("aaa", None)
    repo.commit(tag="v0.0.1")
    initial.write_text(initial.read_text() + "# changed after release\n")

    result = released_check(repo)

    assert result.returncode != 0
    assert "aaa.py" in result.stderr


def test_check_migrate_rejects_deleted_released_migration(tmp_path: Path) -> None:
    repo = Repo(tmp_path)
    initial = repo.migration("aaa", None)
    repo.commit(tag="v0.0.1")
    initial.unlink()

    result = released_check(repo)

    assert result.returncode != 0
    assert "aaa.py" in result.stderr


def test_check_migrate_compares_with_latest_release_tag(tmp_path: Path) -> None:
    # bbb 在 v0.0.1 之後才加, 但已經隨 v0.0.2 發出去了: 跟 v0.0.1 比的話它是「新增」而放行。
    repo = Repo(tmp_path)
    repo.migration("aaa", None)
    repo.commit(tag="v0.0.1")
    second = repo.migration("bbb", "aaa")
    repo.commit(tag="v0.0.2")
    second.write_text(second.read_text() + "# changed after release\n")

    result = released_check(repo)

    assert result.returncode != 0
    assert "bbb.py" in result.stderr


def test_ci_check_job_fetches_release_tags() -> None:
    # actions/checkout 預設只抓一個 commit、不抓 tag: 找不到 tag 時檢查會當成「還沒發版」而略過。
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"^  check:\n(.*?)(?=^  \S|\Z)", workflow, flags=re.MULTILINE | re.DOTALL)
    assert match, "ci.yml 找不到 check job"
    assert re.search(r"^\s+fetch-depth: 0$", match.group(1), flags=re.MULTILINE)


# ── 部署不可讓資料庫往回 ─────────────────────────────────────────────────────


def _two_migrations(tmp_path: Path) -> Repo:
    repo = Repo(tmp_path)
    repo.migration("aaa", None)
    repo.migration("bbb", "aaa")
    return repo


def test_migration_direction_allows_same_revision(tmp_path: Path) -> None:
    result = direction_check(_two_migrations(tmp_path), "bbb")

    assert result.returncode == 0, result.stderr


def test_migration_direction_allows_upgrade(tmp_path: Path) -> None:
    result = direction_check(_two_migrations(tmp_path), "aaa")

    assert result.returncode == 0, result.stderr


def test_migration_direction_rejects_revision_unknown_to_target(tmp_path: Path) -> None:
    result = direction_check(_two_migrations(tmp_path), "ccc")

    assert result.returncode != 0
    # 被拒絕時要直接告訴人該怎麼辦: 往前修, 或還原部署前的備份。
    assert "ccc" in result.stderr
    assert "往前修" in result.stderr
    assert "make db restore" in result.stderr


def test_migration_direction_allows_fresh_database(tmp_path: Path) -> None:
    result = direction_check(_two_migrations(tmp_path), "")

    assert result.returncode == 0, result.stderr


def test_migration_direction_reads_real_migrations() -> None:
    """讀的是 repo 裡真的 migration: 檔案格式變了而讀不到 revision 的話, 整組檢查會變成恆真。"""
    script = ScriptDirectory.from_config(Config(str(REPO_ROOT / "apps" / "api" / "alembic.ini")))
    expected = {revision.revision for revision in script.walk_revisions()}
    # 參數是這支測試自己給的固定值, 不是外部輸入。
    listed = subprocess.run(  # noqa: S603
        [BASH, "-c", f'source "{LIBRARY}" && list_migration_revisions "$1"', "bash", REAL_VERSIONS],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    assert set(listed) == expected
    for head in script.get_heads():
        assert direction_check_real(head).returncode == 0


def direction_check_real(revision: str) -> subprocess.CompletedProcess[str]:
    # 參數是這支測試自己給的固定值, 不是外部輸入。
    return subprocess.run(  # noqa: S603
        [
            BASH,
            "-c",
            f'source "{LIBRARY}" && check_migration_direction "$1" "$2"',
            "bash",
            str(REAL_VERSIONS),
            revision,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
