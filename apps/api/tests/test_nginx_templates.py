"""nginx 的每個 proxy location 都要以 `$remote_addr` 覆寫用戶端 IP 標頭。

限流只讀 `X-Real-IP` (`shared/http/rate_limit.py`) 而且**無條件信任它**, 正確性完全建立在
「nginx 一定會覆寫掉用戶端送來的值」這個前提上。漏掉一個 location 的後果是那條路徑上的請求
帶著用戶端自己宣稱的 IP 進到後端 —— 完全靜默, 沒有任何錯誤或日誌。

覆寫而不是附加 (`$proxy_add_x_forwarded_for`) 也是同一個理由: 附加會把用戶端送進來的值
留在最前面。這支測試住在 api 底下, 因為被保護的是 api 的限流, 不是 nginx 本身。
"""

import re
from pathlib import Path

import pytest

TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "infra" / "nginx"
SNIPPET_DIR = TEMPLATE_DIR / "snippets"
# compose 把 infra/nginx/snippets 掛到這裡 (見 infra/docker/docker-compose.yml)。
INCLUDE = re.compile(r"^\s*include\s+/etc/nginx/snippets/(\S+);", flags=re.MULTILINE)

# 不必帶用戶端 IP 標頭的 location, **每條都要附理由**。
ALLOW = {
    # Next 的 HMR WebSocket, dev only: 只連到 dev server 的熱更新通道, 不會走到後端。
    ("default.dev.conf.template", "/_next/hmr"),
}

REQUIRED_HEADERS = (
    re.compile(r"proxy_set_header\s+X-Real-IP\s+\$remote_addr;"),
    re.compile(r"proxy_set_header\s+X-Forwarded-For\s+\$remote_addr;"),
)


def proxy_locations(source: str) -> list[tuple[str, str]]:
    """回傳每個含 `proxy_pass` 的 location 的 (名稱, 區塊內容)。"""
    found: list[tuple[str, str]] = []
    for match in re.finditer(r"^\s*location\s+([^{]+?)\s*\{", source, flags=re.MULTILINE):
        depth, index = 1, match.end()
        while depth and index < len(source):
            depth += {"{": 1, "}": -1}.get(source[index], 0)
            index += 1
        body = source[match.end() : index]
        if "proxy_pass" in body:
            found.append((match.group(1), body))
    return found


def expand_includes(source: str) -> str:
    """把 snippets 的 include 換成檔案內容; 檔案不存在就讓測試失敗 (nginx 也會起不來)。"""
    return INCLUDE.sub(lambda match: (SNIPPET_DIR / match.group(1)).read_text("utf-8"), source)


def read_template(template: Path) -> str:
    return expand_includes(template.read_text(encoding="utf-8"))


TEMPLATES = sorted(TEMPLATE_DIR.glob("*.template"))


def test_templates_are_found() -> None:
    # 路徑算錯時「沒有模板」與「全部通過」看起來一樣。
    assert TEMPLATES


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda path: path.name)
def test_every_proxy_location_overwrites_client_ip(template: Path) -> None:
    locations = proxy_locations(read_template(template))
    assert locations, f"{template.name} 裡找不到任何 proxy location"

    missing = [
        name
        for name, body in locations
        if (template.name, name) not in ALLOW
        and not all(header.search(body) for header in REQUIRED_HEADERS)
    ]
    assert not missing, f"{template.name} 沒有覆寫 X-Real-IP／X-Forwarded-For：{missing}"


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda path: path.name)
def test_every_template_sends_security_headers(template: Path) -> None:
    # dev 少了這幾個標頭時開發中看不出差別, 等到 prod 才發現兩邊行為不同。
    assert "X-Content-Type-Options" in read_template(template)
