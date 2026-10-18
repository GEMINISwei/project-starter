"""上傳的檔案放在 api 的 `/app/uploads`, 由具名 volume 保存, `make backup` 會備份它。

掛載或擁有者錯了都不會有錯誤訊息: 沒掛 volume 的話檔案在容器重建時消失; 目錄不是 app 的話
新建的 volume 屬於 root, 上傳到執行期才 Permission denied。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE = REPO_ROOT / "infra" / "docker" / "docker-compose.yml"
DOCKERFILE = REPO_ROOT / "apps" / "api" / "Dockerfile"


def _service(name: str) -> str:
    text = COMPOSE.read_text(encoding="utf-8")
    match = re.search(rf"^  {name}:\n(.*?)(?=^  \S|^\S|\Z)", text, flags=re.MULTILINE | re.DOTALL)
    assert match, f"docker-compose.yml 找不到 {name} service"
    return match.group(1)


def test_api_mounts_uploads_volume() -> None:
    # 寫在 base 而不是 overlay: dev 與 prod 都要有, 備份才找得到。
    assert re.search(r"^\s+- uploads:/app/uploads$", _service("api"), flags=re.MULTILINE)


def test_uploads_volume_name_follows_project_and_mode() -> None:
    # make uploads 依這個名稱判斷 volume 在不在。
    text = COMPOSE.read_text(encoding="utf-8")
    assert re.search(
        r"^  uploads:\n    name: \$\{COMPOSE_PROJECT_NAME:\?\}_\$\{MODE:\?\}_uploads$",
        text,
        flags=re.MULTILINE,
    )


def test_api_image_creates_uploads_dir_before_chown() -> None:
    # 新的具名 volume 會沿用 image 裡那個目錄的擁有者; 目錄不存在就會是 root。
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "mkdir -p /app/uploads" in text
    assert text.index("mkdir -p /app/uploads") < text.index("chown -R app:app /app")
