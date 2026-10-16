"""整個 repo 只有一個版號: 根目錄的 VERSION, 其餘每一份副本都要跟它一致。

副本存在是因為工具或 image 要求 (api 與 web 的 image 各自在子目錄建置, 讀不到根目錄的檔案),
由 `make release` 一次改齊。這支測試不重用那支腳本的取代邏輯, 自己再讀一次: 腳本漏改一份,
或有人手動只改了其中一處, 都會在這裡被擋下 —— 否則設定頁顯示的版號 (讀 web 的 package.json)
會跟 api 回報的 (`APP_VERSION`, 也是 deploy.yml 比對 tag 的那一份) 默默分歧。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import json
import tomllib
from pathlib import Path

import pytest

from app.config import APP_VERSION

REPO_ROOT = Path(__file__).resolve().parents[3]


def _root_version() -> str:
    return (REPO_ROOT / "VERSION").read_text().strip()


def _uv_lock_version() -> str:
    lock = tomllib.loads((REPO_ROOT / "apps/api/uv.lock").read_text())
    return next(package["version"] for package in lock["package"] if package["name"] == "api")


def _copies() -> dict[str, str]:
    pyproject = tomllib.loads((REPO_ROOT / "apps/api/pyproject.toml").read_text())
    package_json = json.loads((REPO_ROOT / "apps/web/package.json").read_text())
    package_lock = json.loads((REPO_ROOT / "apps/web/package-lock.json").read_text())
    openapi = json.loads((REPO_ROOT / "contracts/openapi.json").read_text())
    return {
        "apps/api/app/config.py APP_VERSION": APP_VERSION,
        "apps/api/pyproject.toml": pyproject["project"]["version"],
        "apps/api/uv.lock": _uv_lock_version(),
        "apps/web/package.json": package_json["version"],
        "apps/web/package-lock.json (檔頭)": package_lock["version"],
        'apps/web/package-lock.json (packages."")': package_lock["packages"][""]["version"],
        "contracts/openapi.json": openapi["info"]["version"],
    }


@pytest.mark.parametrize("label", list(_copies()))
def test_every_version_copy_matches_root_version_file(label: str):
    assert _copies()[label] == _root_version(), f"{label} 與 VERSION 不一致, 用 make release 改版號"
