"""`.env` 的 `MODE` 決定這台主機是哪種環境, 指令依它切換或拒絕執行。

- `make init dev|prod` 是唯一寫入 `MODE` 的地方, 之後所有碰容器的指令都要它而且值要合法。
- `make start` 依 `MODE` 疊 overlay; production 只能從發版的 tag 啟動。
- production 拒絕只屬於開發機的指令 (清空資料、產生 migration、檢查與發版)。
- `make backup` 備份期間停掉 nginx (唯一的對外入口), 讓資料庫與上傳檔案是同一個時間點;
  還原前一律先完整備份一次。

每個測試在暫存目錄放一份 `scripts/` 與它讀的檔案, 用假的 docker 記下每一次呼叫:
測試不能碰本機真的容器, 也不能讀到開發者自己的 `.env`。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.config import APP_VERSION

REPO_ROOT = Path(__file__).resolve().parents[3]
BASH = shutil.which("bash") or "/bin/bash"
GIT = shutil.which("git") or "/usr/bin/git"
PROJECT = "my-app"
NGINX = f"{PROJECT}-nginx"
ALL_RUNNING = (f"{PROJECT}-postgres", f"{PROJECT}-api", f"{PROJECT}-web", NGINX)

# 腳本讀到的 repo 檔案: 版號、.env 範本、Node 版本線。
COPIED_FILES = (
    ".env.example",
    "apps/api/app/config.py",
    "apps/web/.nvmrc",
    "apps/web/package.json",
    "e2e/package.json",
)

# 依參數決定行為, 每一次呼叫都記進 calls。`stop`/`start` 會改 running, 巢狀的停機才測得到。
# 任何一個參數有對應的 fail-<參數> 檔案就失敗 (例如 fail-pg_dump)。
# `volume ls --filter label=…project=<專案>` 只回傳 labeled 裡那個專案的 volume (每行 `專案 名稱`),
# `system df` 回傳 sizes 的內容 (每行 `名稱<TAB>容量`)。
# 資料庫的 migration revision 取自 revision 檔; 沒有這個檔案就是還沒跑過 migration。
FAKE_DOCKER = """#!/bin/sh
state="$FAKE_DOCKER_DIR"
printf '%s\\n' "$*" >> "$state/calls"
# compose 從環境變數展開 `${DEV_BIND_ADDRESS:-…}`, 參數裡看不到, 另外記下最後一次的值。
printf '%s\\n' "${DEV_BIND_ADDRESS-unset}" > "$state/bind"
for arg in "$@"; do
    [ -e "$state/fail-$arg" ] && exit 1
done
case "$1" in
    ps)
        case "$*" in *--filter*) exit 0 ;; esac
        cat "$state/running" ;;
    volume)
        case "$*" in
            *--filter*)
                project=""
                for arg in "$@"; do
                    case "$arg" in
                        label=com.docker.compose.project=*) project="${arg#*project=}" ;;
                    esac
                done
                awk -v p="$project" '$1 == p { print $2 }' "$state/labeled" ;;
            *) cat "$state/volumes" ;;
        esac ;;
    system)
        cat "$state/sizes" ;;
    stop)
        grep -vx "$2" "$state/running" > "$state/running.tmp" || true
        mv "$state/running.tmp" "$state/running" ;;
    start)
        printf '%s\\n' "$2" >> "$state/running" ;;
    exec)
        case "$*" in
            *to_regclass*) [ -e "$state/revision" ] && echo t || echo f ;;
            *version_num*) cat "$state/revision" ;;
            *pg_dump*) echo dump ;;
            *" -cf "*) echo archive ;;
            "exec -i "*) cat > /dev/null ;;
        esac ;;
esac
exit 0
"""

# 預設讓主機端工具失敗: 開發機才有的指令在沙盒裡不該真的跑起 uv 或 npm。
FAILING_TOOL = "#!/bin/sh\nexit 1\n"
PASSING_TOOL = "#!/bin/sh\nexit 0\n"
# 版本取自 .nvmrc 的 major 與 package.json 的下限, check_node_version 才會放行。
FAKE_NODE = """#!/bin/sh
case "$1" in
    -v) echo v24.15.0 ;;
    -p) echo 24.15.0 ;;
esac
"""


class Sandbox:
    def __init__(self, tmp_path: Path) -> None:
        self.repo = tmp_path / "repo"
        # 呼叫者 shell 裡已經匯出的變數, 測「腳本不沿用外面的值」用。
        self.exported: dict[str, str] = {}
        self.state = tmp_path / "state"
        self.bin = tmp_path / "bin"
        self.home = tmp_path / "home"
        for directory in (self.state, self.bin, self.home):
            directory.mkdir()
        shutil.copytree(REPO_ROOT / "scripts", self.repo / "scripts")
        for relative in COPIED_FILES:
            (self.repo / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO_ROOT / relative, self.repo / relative)
        self.tool("docker", FAKE_DOCKER)
        for name in ("uv", "npm", "npx"):
            self.tool(name, FAILING_TOOL)
        self.containers()
        self.volumes()
        self.labeled()
        self.sizes()

    def tool(self, name: str, script: str) -> None:
        path = self.bin / name
        path.write_text(script)
        path.chmod(0o755)

    def write_env(self, mode: str | None) -> None:
        lines = [
            f"COMPOSE_PROJECT_NAME={PROJECT}",
            "SYSTEM_PORT=3000",
            "POSTGRES_PASSWORD=secret",
        ]
        if mode is not None:
            lines.append(f"MODE={mode}")
        (self.repo / ".env").write_text("\n".join(lines) + "\n")

    def containers(self, *names: str) -> None:
        (self.state / "running").write_text("".join(f"{name}\n" for name in names))

    def volumes(self, *names: str) -> None:
        (self.state / "volumes").write_text("".join(f"{name}\n" for name in names))

    def labeled(self, *volumes: tuple[str, str]) -> None:
        # (專案, volume 名稱): compose 加在 volume 上的專案標籤。
        (self.state / "labeled").write_text("".join(f"{p} {n}\n" for p, n in volumes))

    def sizes(self, *volumes: tuple[str, str]) -> None:
        (self.state / "sizes").write_text("".join(f"{n}\t{size}\n" for n, size in volumes))

    def fail(self, arg: str) -> None:
        (self.state / f"fail-{arg}").touch()

    def git(self, *args: str) -> None:
        # 指令是這支測試自己給的固定值, 不是外部輸入。
        subprocess.run([GIT, *args], cwd=self.repo, env=self.env(), check=True)  # noqa: S603

    def release_checkout(self, tag: str | None = f"v{APP_VERSION}") -> None:
        self.git("init", "-q", "-b", "main")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "init")
        if tag:
            self.git("tag", tag)

    def env(self) -> dict[str, str]:
        # 不繼承 os.environ: conftest 設的 MODE 會蓋過「.env 沒有 MODE」的情境。
        return {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(self.home),
            "FAKE_DOCKER_DIR": str(self.state),
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
            **self.exported,
        }

    def run(self, script: str, *args: str, answer: str = "") -> subprocess.CompletedProcess[str]:
        # 指令是這支測試自己給的固定值, 不是外部輸入。
        return subprocess.run(  # noqa: S603
            [BASH, str(self.repo / "scripts" / f"{script}.sh"), *args],
            cwd=self.repo,
            env=self.env(),
            input=answer,
            capture_output=True,
            text=True,
            check=False,
        )

    def calls(self) -> list[str]:
        log = self.state / "calls"
        return log.read_text().splitlines() if log.exists() else []

    def first(self, needle: str) -> int:
        return next(i for i, call in enumerate(self.calls()) if needle in call)

    def last(self, needle: str) -> int:
        return max(i for i, call in enumerate(self.calls()) if needle in call)

    def bind_address(self) -> str:
        return (self.state / "bind").read_text().strip()

    def called(self, needle: str) -> bool:
        return any(needle in call for call in self.calls())


@pytest.fixture
def box(tmp_path: Path) -> Sandbox:
    return Sandbox(tmp_path)


def running_production(box: Sandbox) -> None:
    box.write_env("production")
    box.containers(*ALL_RUNNING)
    box.volumes(f"{PROJECT}_production_postgres_data", f"{PROJECT}_production_uploads")


# ── make init ────────────────────────────────────────────────────────────────


def test_init_without_mode_prints_usage(box: Sandbox) -> None:
    # 不帶參數就選預設的話, 正式主機上習慣性打的 `make init` 會被當成開發機。
    result = box.run("init")
    assert result.returncode != 0
    assert "make init dev" in result.stderr
    assert "make init prod" in result.stderr
    assert not (box.repo / ".env").exists()


@pytest.mark.parametrize(("command", "mode"), [("dev", "development"), ("prod", "production")])
def test_init_writes_mode(box: Sandbox, command: str, mode: str) -> None:
    for name in ("uv", "npm"):
        box.tool(name, PASSING_TOOL)
    box.tool("node", FAKE_NODE)
    # 專案名稱, 其餘用預設值。
    result = box.run("init", command, answer="my-app\n\n\n")
    assert result.returncode == 0, result.stderr
    assert f"MODE={mode}" in (box.repo / ".env").read_text().splitlines()


def init_env_values(box: Sandbox) -> dict[str, str]:
    """跑一次 `make init dev` (全用預設值), 回傳 `.env` 裡的 KEY=VALUE。"""
    for name in ("uv", "npm"):
        box.tool(name, PASSING_TOOL)
    box.tool("node", FAKE_NODE)
    result = box.run("init", "dev", answer="my-app\n\n\n")
    assert result.returncode == 0, result.stderr
    lines = (box.repo / ".env").read_text().splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))


def test_init_does_not_write_postgres_user_or_db(box: Sandbox) -> None:
    """兩者是寫死在 compose 的固定值, `.env` 再放一份只會跟它對不上。"""
    values = init_env_values(box)
    assert "POSTGRES_USER" not in values
    assert "POSTGRES_DB" not in values


def test_init_generates_postgres_password(box: Sandbox) -> None:
    # 只有 api 的連線 URL 用得到, 沒有人需要記住它; 十六進位插進 URL 不必跳脫。
    assert re.fullmatch(r"[0-9a-f]{64}", init_env_values(box)["POSTGRES_PASSWORD"])


# ── MODE ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("mode", [None, "", "staging"])
@pytest.mark.parametrize("script", ["start", "services", "backup"])
def test_missing_or_invalid_mode_is_rejected(box: Sandbox, script: str, mode: str | None) -> None:
    # 猜一個模式比停下來糟: 猜錯就是用另一組 volume 起服務, 或在正式主機上放行開發用的指令。
    box.write_env(mode)
    box.containers(*ALL_RUNNING)
    result = box.run(script)
    assert result.returncode != 0
    assert "MODE" in result.stderr
    assert not box.called("compose")
    assert not box.called("pg_dump")


DEV_ONLY_COMMANDS = [
    ("db", "reset"),
    ("db", "migrate"),
    ("db", "migration", "add phone"),
    ("check", "lint"),
    ("gen-types",),
    ("release", "9.9.9"),
    ("init", "dev"),
]


@pytest.mark.parametrize("command", DEV_ONLY_COMMANDS)
def test_production_denies_dev_only_commands(box: Sandbox, command: tuple[str, ...]) -> None:
    running_production(box)
    result = box.run(*command, answer="y\n")
    assert result.returncode != 0
    assert "正式環境" in result.stderr
    assert not box.called("exec")


@pytest.mark.parametrize("command", DEV_ONLY_COMMANDS)
def test_development_allows_dev_only_commands(box: Sandbox, command: tuple[str, ...]) -> None:
    # 只看有沒有被模式擋下: 沙盒裡沒有真的工具, 指令本身照樣會因別的原因失敗。
    box.write_env("development")
    box.containers(*ALL_RUNNING)
    result = box.run(*command, answer="n\n")
    assert "正式環境" not in result.stderr


# ── make start / make services ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("mode", "overlay", "other"),
    [
        ("development", "docker-compose.dev.yml", "docker-compose.prod.yml"),
        ("production", "docker-compose.prod.yml", "docker-compose.dev.yml"),
    ],
)
def test_start_uses_overlay_for_mode(box: Sandbox, mode: str, overlay: str, other: str) -> None:
    box.write_env(mode)
    box.release_checkout()
    result = box.run("start")
    assert result.returncode == 0, result.stderr
    up = box.calls()[box.first(" up ")]
    assert overlay in up
    assert other not in up


@pytest.mark.parametrize("tag", [None, "v0.0.0-other"])
def test_production_start_requires_matching_tag(box: Sandbox, tag: str | None) -> None:
    # 主機上 `git pull` 了 main 再啟動, 等於上線一份沒發版、沒經過 CI 的程式碼。
    box.write_env("production")
    box.release_checkout(tag)
    result = box.run("start")
    assert result.returncode != 0
    assert f"v{APP_VERSION}" in result.stderr
    assert not box.called(" up ")


def test_start_binds_loopback_by_default(box: Sandbox) -> None:
    # 明確給 loopback 而不是不設: shell 裡留著的值會讓一般的 `make start` 也對區網開放。
    box.write_env("development")
    box.exported["DEV_BIND_ADDRESS"] = "0.0.0.0"  # noqa: S104
    result = box.run("start")
    assert result.returncode == 0, result.stderr
    assert box.called(" up ")
    assert box.bind_address() == "127.0.0.1"


def test_start_lan_binds_all_interfaces(box: Sandbox) -> None:
    box.write_env("development")
    result = box.run("start", "lan")
    assert result.returncode == 0, result.stderr
    assert box.called(" up ")
    assert box.bind_address() == "0.0.0.0"  # noqa: S104


def test_production_start_rejects_lan(box: Sandbox) -> None:
    # 正式環境的 nginx 信任上一層送來的 X-Real-IP, 對外開放就能冒充任何 IP。
    box.write_env("production")
    box.release_checkout()
    result = box.run("start", "lan")
    assert result.returncode != 0
    assert "正式環境" in result.stderr
    assert not box.called(" up ")


def test_start_rejects_unknown_argument(box: Sandbox) -> None:
    box.write_env("development")
    result = box.run("start", "lna")
    assert result.returncode != 0
    assert "make start lan" in result.stderr
    assert not box.called(" up ")


@pytest.mark.parametrize(("answer", "stopped"), [("n\n", False), ("", False), ("y\n", True)])
def test_production_down_requires_confirmation(box: Sandbox, answer: str, stopped: bool) -> None:
    running_production(box)
    result = box.run("services", "down", answer=answer)
    assert (result.returncode == 0) == stopped
    assert box.called(" down") == stopped


def test_development_down_needs_no_confirmation(box: Sandbox) -> None:
    box.write_env("development")
    result = box.run("services", "down")
    assert result.returncode == 0, result.stderr
    assert box.called(" down")


def test_services_prints_app_version(box: Sandbox) -> None:
    running_production(box)
    result = box.run("services")
    assert result.returncode == 0, result.stderr
    assert f"v{APP_VERSION}" in result.stdout
    assert box.called(" ps")


def test_services_prints_mode_after_version(box: Sandbox) -> None:
    running_production(box)
    result = box.run("services")
    assert result.returncode == 0, result.stderr
    assert f"版本：v{APP_VERSION}  MODE：production" in result.stdout.splitlines()


PROJECT_VOLUMES = (
    (PROJECT, f"{PROJECT}_production_postgres_data"),
    (PROJECT, f"{PROJECT}_production_uploads"),
    (PROJECT, f"{PROJECT}_development_postgres_data"),
    (PROJECT, f"{PROJECT}_legacy_data"),
)
OTHER_VOLUMES = (
    ("other", "other_production_postgres_data"),
    (f"{PROJECT}-2", f"{PROJECT}-2_production_uploads"),
)


def volume_lines(stdout: str) -> list[str]:
    # `Volumes` 標題之後的每一行, 名稱靠左不縮排。
    lines = stdout.splitlines()
    return lines[lines.index("Volumes") + 1 :]


def test_services_lists_project_volumes(box: Sandbox) -> None:
    # 以 compose 的專案標籤篩選: `my-app-2` 這種開頭相同的別的專案不算。
    running_production(box)
    box.labeled(*PROJECT_VOLUMES, *OTHER_VOLUMES)
    result = box.run("services")
    assert result.returncode == 0, result.stderr
    names = [line.split()[0] for line in volume_lines(result.stdout) if line.strip()]
    assert names == [name for _, name in PROJECT_VOLUMES]


def test_services_marks_volumes_not_matching_mode(box: Sandbox) -> None:
    # 另一種模式留下的, 以及不符合 `<專案>_<MODE>_` 命名的, 都是這個 MODE 用不到的 volume。
    running_production(box)
    box.labeled(*PROJECT_VOLUMES)
    result = box.run("services")
    assert result.returncode == 0, result.stderr
    marked = {
        line.split()[0]: line.endswith("← Not Matched") for line in volume_lines(result.stdout)
    }
    assert marked == {
        f"{PROJECT}_production_postgres_data": False,
        f"{PROJECT}_production_uploads": False,
        f"{PROJECT}_development_postgres_data": True,
        f"{PROJECT}_legacy_data": True,
    }


def test_services_does_not_compute_sizes(box: Sandbox) -> None:
    # 算容量要掃過整台主機的 volume; 部署每次都跑 make services, 不能被它拖慢。
    running_production(box)
    box.labeled(*PROJECT_VOLUMES)
    result = box.run("services")
    assert result.returncode == 0, result.stderr
    assert not box.called("system df")


def test_services_volumes_shows_sizes(box: Sandbox) -> None:
    running_production(box)
    box.labeled(*PROJECT_VOLUMES, *OTHER_VOLUMES)
    box.sizes(
        (f"{PROJECT}_production_postgres_data", "245MB"),
        (f"{PROJECT}_production_uploads", "3.1GB"),
        (f"{PROJECT}_development_postgres_data", "52MB"),
        (f"{PROJECT}_legacy_data", "0B"),
        ("other_production_postgres_data", "9GB"),
    )
    result = box.run("services", "volumes")
    assert result.returncode == 0, result.stderr
    assert f"版本：v{APP_VERSION}  MODE：production" in result.stdout.splitlines()
    rows = {line.split()[0]: line.split()[1:] for line in volume_lines(result.stdout)}
    assert rows == {
        f"{PROJECT}_production_postgres_data": ["245MB"],
        f"{PROJECT}_production_uploads": ["3.1GB"],
        f"{PROJECT}_development_postgres_data": ["52MB", "←", "Not", "Matched"],
        f"{PROJECT}_legacy_data": ["0B", "←", "Not", "Matched"],
    }
    assert not box.called(" ps ")


def test_services_without_volumes_says_none(box: Sandbox) -> None:
    running_production(box)
    result = box.run("services")
    assert result.returncode == 0, result.stderr
    assert volume_lines(result.stdout) == ["沒有 volume"]


# ── make backup ──────────────────────────────────────────────────────────────


def test_fresh_host_check_uses_current_mode(box: Sandbox) -> None:
    # 只有另一個模式的 volume: 對這個模式來說仍是全新主機, 部署的第一次備份要放行。
    box.write_env("production")
    box.volumes(f"{PROJECT}_development_postgres_data", f"{PROJECT}_development_uploads")
    result = box.run("backup", "allow-fresh")
    assert result.returncode == 0, result.stderr
    assert not box.called("pg_dump")
    assert not box.called(f"stop {NGINX}")


def test_backup_stops_and_restarts_nginx(box: Sandbox) -> None:
    running_production(box)
    result = box.run("backup")
    assert result.returncode == 0, result.stderr
    stop, dump, archive, start = (
        box.first(f"stop {NGINX}"),
        box.first("pg_dump"),
        box.first(" -cf "),
        box.first(f"start {NGINX}"),
    )
    assert stop < dump < archive < start
    # 兩份只差副檔名, 才配得成一組。
    files = list((box.repo / "backups").iterdir())
    assert sorted(path.suffix for path in files) == [".dump", ".tar"]
    assert len({path.stem for path in files}) == 1


def test_backup_restarts_nginx_on_failure(box: Sandbox) -> None:
    # 備份失敗不能讓網站一直停著。
    running_production(box)
    box.fail("pg_dump")
    result = box.run("backup")
    assert result.returncode != 0
    assert box.first(f"stop {NGINX}") < box.last(f"start {NGINX}")
    assert not box.called(" -cf ")


def test_backup_leaves_stopped_nginx_alone(box: Sandbox) -> None:
    # 還原時外層已經停了 nginx; 裡面的備份不能在還原之前就把它開回來。
    running_production(box)
    box.containers(f"{PROJECT}-postgres", f"{PROJECT}-api")
    result = box.run("backup")
    assert result.returncode == 0, result.stderr
    assert not box.called(f"stop {NGINX}")
    assert not box.called(f"start {NGINX}")


# 帳號與資料庫名稱只寫在 compose, 腳本在容器裡讀它們, 走本機 socket 不需要密碼。
CONTAINER_CREDENTIALS = ('-U "$POSTGRES_USER"', '-d "$POSTGRES_DB"')


def test_psql_reads_credentials_inside_container(box: Sandbox) -> None:
    box.write_env("development")
    box.containers(*ALL_RUNNING)
    result = box.run("db", "psql")
    assert result.returncode == 0, result.stderr
    call = next(call for call in box.calls() if " psql " in call)
    assert all(part in call for part in CONTAINER_CREDENTIALS)
    assert "PGPASSWORD" not in call


def test_psql_prompt_shows_project_name(box: Sandbox) -> None:
    """每套系統的資料庫都叫 app, 同時連好幾套時要從提示字元分得出是哪一套。"""
    box.write_env("development")
    box.containers(*ALL_RUNNING)
    result = box.run("db", "psql")
    assert result.returncode == 0, result.stderr
    call = next(call for call in box.calls() if " psql " in call)
    assert f"PROMPT1={PROJECT}%R" in call
    assert f"PROMPT2={PROJECT}%R" in call


@pytest.mark.parametrize(
    ("command", "tool"), [(("backup",), "pg_dump"), (("db", "restore"), "pg_restore")]
)
def test_backup_and_restore_read_credentials_inside_container(
    box: Sandbox, command: tuple[str, ...], tool: str
) -> None:
    running_production(box)
    file = existing_backup(box, "dump")
    args = (*command, file) if tool == "pg_restore" else command
    result = box.run(*args, answer="y\n")
    assert result.returncode == 0, result.stderr
    call = next(call for call in box.calls() if tool in call)
    assert all(part in call for part in CONTAINER_CREDENTIALS)
    assert "PGPASSWORD" not in call


# ── restore ──────────────────────────────────────────────────────────────────

RESTORES = [
    ("db", "dump", "pg_restore"),
    ("uploads", "tar", f"exec -i {PROJECT}-api sh"),
]


def existing_backup(box: Sandbox, extension: str) -> str:
    (box.repo / "backups").mkdir(exist_ok=True)
    name = f"backups/{PROJECT}_v{APP_VERSION}_20260101_000000.{extension}"
    (box.repo / name).write_text("old")
    return name


@pytest.mark.parametrize(("script", "extension", "restore"), RESTORES)
def test_restore_backs_up_first(box: Sandbox, script: str, extension: str, restore: str) -> None:
    running_production(box)
    file = existing_backup(box, extension)
    result = box.run(script, "restore", file, answer="y\n")
    assert result.returncode == 0, result.stderr
    stop, dump, archive, restored, start = (
        box.first(f"stop {NGINX}"),
        box.first("pg_dump"),
        box.first(" -cf "),
        box.first(restore),
        box.last(f"start {NGINX}"),
    )
    assert stop < dump < archive < restored < start
    assert box.calls().count(f"stop {NGINX}") == 1


@pytest.mark.parametrize(("script", "extension", "restore"), RESTORES)
def test_restore_aborts_when_backup_fails(
    box: Sandbox, script: str, extension: str, restore: str
) -> None:
    running_production(box)
    file = existing_backup(box, extension)
    box.fail("pg_dump")
    result = box.run(script, "restore", file, answer="y\n")
    assert result.returncode != 0
    assert not box.called(restore)
    assert box.first(f"stop {NGINX}") < box.last(f"start {NGINX}")


@pytest.mark.parametrize("mode", ["development", "production"])
@pytest.mark.parametrize(("answer", "revoked"), [("n\n", False), ("", False), ("y\n", True)])
def test_revoke_sessions_requires_confirmation(
    box: Sandbox, mode: str, answer: str, revoked: bool
) -> None:
    """所有人都會被登出, 開發機與正式環境都要先確認。"""
    box.write_env(mode)
    box.containers(*ALL_RUNNING)
    result = box.run("db", "revoke-sessions", answer=answer)
    assert (result.returncode == 0) == revoked
    assert box.called("revoke-sessions") == revoked


# ── help ─────────────────────────────────────────────────────────────────────


def test_help_hides_internal_commands() -> None:
    # 部署與還原內部用的指令只寫在 docs/operations.md, 不列給一般使用者。
    makefile = (REPO_ROOT / "Makefile").read_text()
    targets = re.search(r"^TARGETS = (.+)$", makefile, re.MULTILINE)
    assert targets is not None
    # 指令是這支測試自己給的固定值, 不是外部輸入。
    result = subprocess.run(  # noqa: S603
        [BASH, str(REPO_ROOT / "scripts" / "help.sh"), *targets.group(1).split()],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    for visible in ("make start", "make services", "make backup", "make init dev"):
        assert visible in result.stdout
    for hidden in ("allow-fresh", "prune", "make version", "[內部]"):
        assert hidden not in result.stdout


# ── 先單獨跑 migrate, 成功才切換服務 ──────────────────────────────────────────


@pytest.mark.parametrize("mode", ["development", "production"])
def test_start_runs_migrate_before_switching_services(box: Sandbox, mode: str) -> None:
    # compose 會先把線上的 api 換掉才知道 migrate 失敗, 結果就是停機; 先單獨跑過才換。
    box.write_env(mode)
    box.release_checkout()
    result = box.run("start")
    assert result.returncode == 0, result.stderr
    migrate = box.first(" migrate")
    assert " run " in box.calls()[migrate]
    assert migrate < box.first(" up ")


@pytest.mark.parametrize("mode", ["development", "production"])
def test_start_stops_when_migrate_fails(box: Sandbox, mode: str) -> None:
    box.write_env(mode)
    box.release_checkout()
    box.fail("migrate")
    result = box.run("start")
    assert result.returncode != 0
    assert not box.called(" up ")


# ── 部署前讀資料庫的 revision (make db revision) ─────────────────────────────


def _with_database(box: Sandbox, mode: str, revision: str | None) -> None:
    box.write_env(mode)
    box.containers(*ALL_RUNNING)
    box.volumes(f"{PROJECT}_{mode}_postgres_data")
    if revision is not None:
        (box.state / "revision").write_text(f"{revision}\n")


def test_db_revision_prints_current_revision(box: Sandbox) -> None:
    _with_database(box, "development", "959dc24d48e4")
    result = box.run("db", "revision")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "959dc24d48e4"


def test_db_revision_prints_nothing_on_fresh_host(box: Sandbox) -> None:
    # 全新主機 (還沒有資料 volume): 部署的方向檢查視為沒有資料庫而放行。
    box.write_env("production")
    result = box.run("db", "revision")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_db_revision_is_allowed_on_production(box: Sandbox) -> None:
    _with_database(box, "production", "959dc24d48e4")
    result = box.run("db", "revision")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "959dc24d48e4"
