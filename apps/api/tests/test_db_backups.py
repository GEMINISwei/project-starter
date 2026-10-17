"""備份檔帶版號 (`scripts/lib/backups.sh`), `make db restore` 只列出與 `make version` 一致的備份。

回滾到某一版之後, 能還原的只有那一版的備份: 新版 migration 改過的結構, 舊程式讀不了。
檔名帶版號、清單只列這一版, 確認的人才不會挑錯檔案。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import shutil
import subprocess
from pathlib import Path

from app.config import APP_VERSION

REPO_ROOT = Path(__file__).resolve().parents[3]
LIB = REPO_ROOT / "scripts" / "lib" / "backups.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
BASH = shutil.which("bash") or "/bin/bash"


def run(cwd: Path, command: str, *args: str) -> subprocess.CompletedProcess[str]:
    # 指令是這支測試自己給的固定值, 不是外部輸入。
    return subprocess.run(  # noqa: S603
        [BASH, "-c", f'source "{LIB}"; {command} "$@"', "_", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def output(cwd: Path, command: str, *args: str) -> list[str]:
    result = run(cwd, command, *args)
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


def make_backups(tmp_path: Path, *names: str) -> None:
    (tmp_path / "backups").mkdir()
    for name in names:
        (tmp_path / "backups" / name).touch()


def test_backup_name_includes_project_version_and_time(tmp_path: Path) -> None:
    assert output(tmp_path, "backup_name", "my-app", "0.0.1", "20261017_083553") == [
        "backups/my-app_v0.0.1_20261017_083553.dump"
    ]


def test_backup_label_shows_version_date_and_time_only(tmp_path: Path) -> None:
    file = "backups/my_app_v0.0.1_20261017_083553.dump"
    assert output(tmp_path, "backup_label", file) == ["v0.0.1 2026-10-17 08:35:53"]


def test_backup_version_is_read_from_file_name(tmp_path: Path) -> None:
    # 專案名稱本身可以有底線, 版號要從檔名尾端認。
    file = "elsewhere/my_project_v0.1.2_20261017_083553.dump"
    assert output(tmp_path, "backup_version", file) == ["0.1.2"]


def test_backup_version_fails_for_unversioned_name(tmp_path: Path) -> None:
    # 改版前的舊命名認不出版本, 不能被當成任何一版的備份。
    assert run(tmp_path, "backup_version", "backups/app_20261017_083553.dump").returncode != 0


def test_list_only_includes_current_version(tmp_path: Path) -> None:
    make_backups(
        tmp_path,
        "app_v0.0.1_20261017_083553.dump",
        "app_v0.0.2_20261018_090000.dump",
        "app_v0.0.10_20261019_090000.dump",
    )
    assert output(tmp_path, "list_backups", "0.0.1") == ["backups/app_v0.0.1_20261017_083553.dump"]


def test_list_is_newest_first(tmp_path: Path) -> None:
    make_backups(
        tmp_path,
        "app_v0.0.1_20261017_083553.dump",
        "app_v0.0.1_20261101_000000.dump",
        "app_v0.0.1_20261017_120000.dump",
    )
    assert output(tmp_path, "list_backups", "0.0.1") == [
        "backups/app_v0.0.1_20261101_000000.dump",
        "backups/app_v0.0.1_20261017_120000.dump",
        "backups/app_v0.0.1_20261017_083553.dump",
    ]


def test_list_skips_files_without_version(tmp_path: Path) -> None:
    make_backups(
        tmp_path,
        "app_20261017_083553.dump",
        "app_v0.0.1_20261017_083553.dump.partial",
    )
    assert output(tmp_path, "list_backups", "0.0.1") == []


def test_make_version_prints_app_version() -> None:
    result = subprocess.run(  # noqa: S603
        [BASH, str(REPO_ROOT / "scripts" / "version.sh")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"v{APP_VERSION}\n"


def test_deploy_backs_up_before_checking_out_new_tag() -> None:
    # 備份檔的版號取自這份 checkout; 先 checkout 新 tag 的話, 舊版的資料會被標成新版號。
    text = WORKFLOW.read_text()
    assert text.index("echo 'make db backup allow-fresh'") < text.index("git checkout --detach")
