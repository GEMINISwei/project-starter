"""容器內的 nginx 一定在主機的 reverse proxy 後面, 要信任它送來的用戶端資訊。

TLS 在主機那層結束, 容器 nginx 看到的連線來自主機, 不是用戶端。不信任上一層的話:

- `$remote_addr` 是主機的位址, 所有人共用同一份登入限流額度, 一個人打爆全站被鎖。
- `$scheme` 永遠是 `http`, cookie 安靜地失去 `Secure` (`shared/session/cookie-options.ts`)。

信任的前提是**只有主機連得到容器 nginx**: port 只綁 loopback, 外部的請求一定先經過主機
那層, 標頭由它覆寫。兩件事要一起成立, 所以放在同一支測試裡。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import re
from pathlib import Path

import pytest

from tests.test_nginx_templates import TEMPLATES, read_template

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE = REPO_ROOT / "infra" / "docker" / "docker-compose.yml"
HOST_EXAMPLE = REPO_ROOT / "infra" / "host-nginx" / "example.conf"

# 主機經 docker 的 port 轉進來時, 來源是 loopback 或 docker 網路的 gateway, 都在這幾段裡。
PRIVATE_NETWORKS = {"127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"}


def outside_server_blocks(source: str) -> str:
    """去掉 server 區塊, 留下 http 層的設定 (realip 與 map 要對整份設定生效)。"""
    start = source.index("server {")
    depth, index = 1, start + len("server {")
    while depth and index < len(source):
        depth += {"{": 1, "}": -1}.get(source[index], 0)
        index += 1
    return source[:start] + source[index:]


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda path: path.name)
def test_every_template_trusts_only_private_networks(template: Path) -> None:
    http_level = outside_server_blocks(read_template(template))

    trusted = set(re.findall(r"^\s*set_real_ip_from\s+(\S+);", http_level, flags=re.MULTILINE))
    assert trusted == PRIVATE_NETWORKS
    assert re.search(r"^\s*real_ip_header\s+X-Real-IP;", http_level, flags=re.MULTILINE)


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda path: path.name)
def test_forwarded_proto_follows_upstream_proxy(template: Path) -> None:
    source = read_template(template)

    assert re.search(r"proxy_set_header\s+X-Forwarded-Proto\s+\$forwarded_proto;", source)
    # 只接受 http/https, 其他值 (含沒送) 退回這一層看到的協定。
    proto_map = re.search(
        r"map\s+\$http_x_forwarded_proto\s+\$forwarded_proto\s*\{(.*?)\}", source, re.DOTALL
    )
    assert proto_map
    assert re.search(r"^\s*default\s+\$scheme;", proto_map.group(1), flags=re.MULTILINE)
    assert set(re.findall(r"^\s*\S+\s+(\S+);", proto_map.group(1), flags=re.MULTILINE)) == {
        "$scheme",
        "https",
        "http",
    }


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda path: path.name)
def test_every_template_hides_nginx_version(template: Path) -> None:
    assert re.search(r"^\s*server_tokens\s+off;", read_template(template), flags=re.MULTILINE)


def test_nginx_port_binds_loopback_only() -> None:
    # 綁 0.0.0.0 的話外部可以繞過主機直接連進來, 自己帶 X-Real-IP 就能冒充任何 IP。
    # Docker 直接改 iptables, 主機的 ufw 擋不住它開的 port。
    service = re.search(r"^  nginx:\n(.*?)(?=^  \S|\Z)", COMPOSE.read_text("utf-8"), re.M | re.S)
    assert service
    ports = re.search(r"ports:\n((?:\s+- .*\n)+)", service.group(1))
    assert ports
    assert re.findall(r"^\s+- (\S+)$", ports.group(1), re.M) == ["127.0.0.1:${SYSTEM_PORT:?}:80"]


def test_host_example_overwrites_client_headers() -> None:
    # 主機那層是唯一面對用戶端的地方, 必須**覆寫**這兩個標頭, 容器才能信任它們。
    source = HOST_EXAMPLE.read_text("utf-8")

    assert re.search(r"proxy_set_header\s+X-Real-IP\s+\$remote_addr;", source)
    assert re.search(r"proxy_set_header\s+X-Forwarded-Proto\s+\$scheme;", source)


def test_host_example_body_size_covers_server_actions() -> None:
    # 比容器小的話, 介於兩者之間的請求在主機就被擋下 (nginx 預設只有 1m)。
    sizes = re.findall(r"^\s*client_max_body_size\s+(\d+)m;", HOST_EXAMPLE.read_text("utf-8"), re.M)
    assert sizes
    assert all(int(size) >= 16 for size in sizes)
