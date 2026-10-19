"""`make init` 產生 .env 前的檢查 (`scripts/lib/compose.sh`): docker 能用、專案名稱沒被佔用。

容器、volume、network 都以 `COMPOSE_PROJECT_NAME` 為前綴 (compose 也以它當專案標籤),
撞名的話新專案會接手舊專案的容器與資料庫 volume —— 症狀是「登入不了」或「資料怎麼是別人的」,
看不出跟名稱有關, 所以在還沒寫出 .env 時就擋。

docker 用假的取代: 測試不該依賴本機有哪些容器。假 docker 照 `--filter label=...` 只回傳
該專案的資源, 「別的專案不算」才測得到。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LIB = REPO_ROOT / "scripts" / "lib" / "compose.sh"
BASH = shutil.which("bash") or "/bin/bash"

FAKE_DOCKER = """#!/bin/sh
[ -e "$FAKE_DOCKER_DIR/fail-$1" ] && exit 1
project=""
for arg in "$@"; do
    case "$arg" in
        label=com.docker.compose.project=*) project="${arg#label=com.docker.compose.project=}" ;;
    esac
done
case "$1" in
    ps) file=containers ;;
    volume) file=volumes ;;
    *) exit 0 ;;
esac
awk -v p="$project" '$1 == p { print $2 }' "$FAKE_DOCKER_DIR/$file"
exit 0
"""


def fake_docker(tmp_path: Path, *, containers: str = "", volumes: str = "", fail: str = "") -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    (tmp_path / "containers").write_text(containers)
    (tmp_path / "volumes").write_text(volumes)
    if fail:
        (tmp_path / f"fail-{fail}").touch()
    return bin_dir


def run(tmp_path: Path, command: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "FAKE_DOCKER_DIR": str(tmp_path),
    }
    # 指令是這支測試自己給的固定值, 不是外部輸入。
    return subprocess.run(  # noqa: S603
        [BASH, "-c", f'source "{LIB}"; {command} "$@"', "_", *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_unused_project_name_passes(tmp_path: Path) -> None:
    fake_docker(tmp_path)
    result = run(tmp_path, "require_unused_project_name", "my-app")
    assert result.returncode == 0, result.stderr


def test_project_name_with_containers_is_rejected(tmp_path: Path) -> None:
    fake_docker(tmp_path, containers="my-app my-app-api\nmy-app my-app-postgres\n")
    result = run(tmp_path, "require_unused_project_name", "my-app")
    assert result.returncode != 0
    assert "my-app-api" in result.stderr
    assert "my-app-postgres" in result.stderr


def test_project_name_with_only_volumes_is_rejected(tmp_path: Path) -> None:
    # 容器刪了但資料 volume 還在: 新專案起來會直接掛上舊資料庫。
    fake_docker(tmp_path, volumes="my-app my-app_development_postgres_data\n")
    result = run(tmp_path, "require_unused_project_name", "my-app")
    assert result.returncode != 0
    assert "my-app_development_postgres_data" in result.stderr


def test_other_projects_do_not_block_the_name(tmp_path: Path) -> None:
    fake_docker(
        tmp_path,
        containers="other my-app-like-name\nmy-app-2 my-app-2-api\n",
        volumes="other other_development_postgres_data\n",
    )
    result = run(tmp_path, "require_unused_project_name", "my-app")
    assert result.returncode == 0, result.stderr


def test_docker_query_failure_is_not_treated_as_unused(tmp_path: Path) -> None:
    fake_docker(tmp_path, fail="volume")
    result = run(tmp_path, "require_unused_project_name", "my-app")
    assert result.returncode != 0
    assert result.stderr


def test_missing_compose_plugin_is_reported(tmp_path: Path) -> None:
    fake_docker(tmp_path, fail="compose")
    result = run(tmp_path, "require_compose")
    assert result.returncode != 0
    assert "docker compose" in result.stderr


def test_unreachable_docker_daemon_is_reported(tmp_path: Path) -> None:
    fake_docker(tmp_path, fail="info")
    result = run(tmp_path, "require_compose")
    assert result.returncode != 0
    assert "daemon" in result.stderr


# 同一台主機放好幾套系統時, 目錄名稱與專案名稱取一樣最好對照, 所以預設就拿目錄名稱;
# 目錄名稱不一定符合專案名稱的規則, 轉不出合法的名稱時才退回範本的 my-app。


def test_default_project_name_is_the_directory_name(tmp_path: Path) -> None:
    result = run(tmp_path, "default_project_name", "/srv/project-starter-test")
    assert result.stdout == "project-starter-test\n", result.stderr


def test_default_project_name_is_lowercased(tmp_path: Path) -> None:
    result = run(tmp_path, "default_project_name", "/srv/Project_Starter")
    assert result.stdout == "project_starter\n", result.stderr


def test_default_project_name_replaces_invalid_characters(tmp_path: Path) -> None:
    result = run(tmp_path, "default_project_name", "/srv/my.app v2")
    assert result.stdout == "my-app-v2\n", result.stderr


def test_default_project_name_trims_separators(tmp_path: Path) -> None:
    result = run(tmp_path, "default_project_name", "/srv/_my-app.")
    assert result.stdout == "my-app\n", result.stderr


def test_default_project_name_falls_back_when_nothing_is_left(tmp_path: Path) -> None:
    result = run(tmp_path, "default_project_name", "/srv/專案")
    assert result.stdout == "my-app\n", result.stderr
