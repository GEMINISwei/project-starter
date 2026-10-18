"""compose 檔裡每個具名 volume 都叫 `<專案>_<MODE>_<名稱>`。

名稱是腳本認 volume 的依據 (`make backup allow-fresh` 判斷全新主機、`make backup` 判斷有沒有
uploads volume), 也是人在主機上用 `docker volume ls` 分辨哪個專案、哪個模式的方式。
寫死 `dev` 這類例外不會有錯誤訊息, 只會讓依模式篩選的人漏掉它。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILES = sorted((REPO_ROOT / "infra" / "docker").glob("docker-compose*.yml"))


def _volume_names(path: Path) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^volumes:\n(.*?)(?=^\S|\Z)", text, flags=re.MULTILINE | re.DOTALL)
    if not match:
        return []
    return re.findall(r"^  (\S+):\n    name: (\S+)$", match.group(1), flags=re.MULTILINE)


def test_compose_files_declare_named_volumes() -> None:
    # 防止下面的參數化因為找不到檔案或寫法改變而變成零個測試, 安靜地全部通過。
    assert sum(len(_volume_names(path)) for path in COMPOSE_FILES) >= 4


@pytest.mark.parametrize("path", COMPOSE_FILES, ids=lambda path: path.name)
def test_volume_names_follow_project_and_mode(path: Path) -> None:
    for key, name in _volume_names(path):
        assert name == f"${{COMPOSE_PROJECT_NAME:?}}_${{MODE:?}}_{key}", f"{path.name}: {key}"
