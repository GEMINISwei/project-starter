"""compose 的 healthcheck 只負責「啟動時準備好了沒」, 而且每次探測都要便宜。

Docker 沒有原生的 HTTP 探測, 每次 healthcheck 都在容器裡起一個行程。探測若是
`python -c "import urllib…"` 這類指令, 每次要花上百毫秒 CPU, 每 10 秒一次就是 `docker stats`
裡看到的週期性尖峰。單機 compose 在 unhealthy 時也不會重啟容器, 執行期間的狀態只是顯示用,
所以啟動期間密集檢查 (`start_interval`)、之後放慢即可。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import json
import re
import shutil
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILES = sorted((REPO_ROOT / "infra" / "docker").glob("docker-compose*.yml"))
BASE_COMPOSE = REPO_ROOT / "infra" / "docker" / "docker-compose.yml"
INTERPRETERS = {"python", "python3", "node", "npm", "npx"}
MIN_STEADY_INTERVAL_SECONDS = 30
BASH = shutil.which("bash") or "/bin/bash"


def _healthchecks(path: Path) -> dict[str, dict[str, str]]:
    """`{服務: {欄位: 原始值}}`。只認 compose 檔的固定縮排 (服務 2 格、欄位 6 格)。"""
    text = path.read_text(encoding="utf-8")
    services = re.search(r"^services:\n(.*?)(?=^\S|\Z)", text, flags=re.MULTILINE | re.DOTALL)
    if not services:
        return {}
    result: dict[str, dict[str, str]] = {}
    blocks = re.split(r"^  (?=[\w-]+:\n)", services.group(1), flags=re.MULTILINE)
    for block in blocks:
        name, _, body = block.partition(":\n")
        check = re.search(r"^    healthcheck:\n((?:      .*\n)+)", body, flags=re.MULTILINE)
        if check:
            fields = re.findall(r"^      (\w+): (.+)$", check.group(1), flags=re.MULTILINE)
            result[name] = dict(fields)
    return result


ALL_HEALTHCHECKS = [
    (f"{path.name}:{service}", fields)
    for path in COMPOSE_FILES
    for service, fields in _healthchecks(path).items()
]
HEALTHCHECK_IDS = [where for where, _ in ALL_HEALTHCHECKS]


def _seconds(value: str) -> int:
    match = re.fullmatch(r"(\d+)(s|m)", value)
    assert match, f"看不懂的時間格式: {value}"
    return int(match.group(1)) * (60 if match.group(2) == "m" else 1)


def test_compose_files_declare_healthchecks() -> None:
    # 防止下面的參數化因為寫法改變而變成零個測試, 安靜地全部通過。
    assert {"api", "web", "postgres"} <= set(_healthchecks(BASE_COMPOSE))


@pytest.mark.parametrize(("where", "fields"), ALL_HEALTHCHECKS, ids=HEALTHCHECK_IDS)
def test_healthcheck_with_any_service_does_not_start_interpreter(
    where: str, fields: dict[str, str]
) -> None:
    command = json.loads(fields["test"])
    assert command[0] in {"CMD", "CMD-SHELL"}, where
    assert command[1] not in INTERPRETERS, f"{where}: 探測不要起直譯器, 改用 bash 或小程式"


@pytest.mark.parametrize(("where", "fields"), ALL_HEALTHCHECKS, ids=HEALTHCHECK_IDS)
def test_healthcheck_with_any_service_polls_fast_only_while_starting(
    where: str, fields: dict[str, str]
) -> None:
    assert "start_period" in fields, where
    assert _seconds(fields["start_interval"]) <= 2, where
    assert _seconds(fields["interval"]) >= MIN_STEADY_INTERVAL_SECONDS, where


# --- bash 的 HTTP 探測 --------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    status = 200

    def do_GET(self) -> None:
        self.send_response(self.status)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def http_server() -> Iterator[HTTPServer]:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _probe(service: str, port: int) -> int:
    """在本機跑 compose 裡那條探測指令, 只把容器內的 port 換成測試伺服器的。"""
    command = json.loads(_healthchecks(BASE_COMPOSE)[service]["test"])
    assert command[:2] == ["CMD", "bash"], f"{service} 的探測不是 bash"
    script = re.sub(r"/dev/tcp/127\.0\.0\.1/\d+", f"/dev/tcp/127.0.0.1/{port}", command[3])
    return subprocess.run([BASH, *command[2:3], script], timeout=5, check=False).returncode  # noqa: S603


@pytest.mark.parametrize("service", ["api", "web"])
def test_http_probe_with_ok_response_succeeds(service: str, http_server: HTTPServer) -> None:
    _Handler.status = 200
    assert _probe(service, http_server.server_address[1]) == 0


@pytest.mark.parametrize("service", ["api", "web"])
def test_http_probe_with_error_response_fails(service: str, http_server: HTTPServer) -> None:
    _Handler.status = 503
    try:
        assert _probe(service, http_server.server_address[1]) != 0
    finally:
        _Handler.status = 200


@pytest.mark.parametrize("service", ["api", "web"])
def test_http_probe_with_closed_port_fails(service: str, http_server: HTTPServer) -> None:
    port = http_server.server_address[1]
    http_server.shutdown()
    http_server.server_close()
    assert _probe(service, port) != 0


def _service(path: Path, name: str) -> str:
    """回傳服務的區塊。只認 compose 檔的固定縮排 (服務 2 格、內容至少 4 格)。"""
    text = path.read_text(encoding="utf-8")
    block = re.search(rf"^  {name}:\n((?:(?:    .*)?\n)+)", text, flags=re.MULTILINE)
    assert block, f"{path.name} 沒有 {name} 服務"
    return block.group(1)


def test_start_web_without_key_keeps_nginx_down() -> None:
    """金鑰缺失時 web 會結束行程, 靠這幾個設定才變成明顯的重啟迴圈, 而不是半套服務上線。"""
    web = _service(BASE_COMPOSE, "web")
    nginx = _service(BASE_COMPOSE, "nginx")

    assert "NEXT_SERVER_ACTIONS_ENCRYPTION_KEY: ${NEXT_SERVER_ACTIONS_ENCRYPTION_KEY:?}" in web
    assert "    restart: always\n" in web
    assert "    healthcheck:\n" in web
    depends_on = r"^    depends_on:\n(?:      .*\n)*?"
    assert re.search(depends_on + r"      web:\n        condition: service_healthy$", nginx, re.M)
