"""跟 git tag 對齊的版號只有兩處: `APP_VERSION` 與 CHANGELOG 最新的版本段落。

deploy.yml 只比對 tag 與 `APP_VERSION`, 這裡擋住 CHANGELOG 沒跟上 —— 否則 release 對應的
變更紀錄會掛在錯的版本底下, 而那不會有任何錯誤訊息。兩處由 `make release` 一起改。

其餘的版號刻意不跟發版: `pyproject.toml`、`package.json` 與 lock 檔是套件自己的版號,
有變更時才改; OpenAPI 的 `info.version` 固定不動 (見 `shared/platform.py`)。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import re
from pathlib import Path

from app.config import APP_VERSION

REPO_ROOT = Path(__file__).resolve().parents[3]


def _latest_changelog_release() -> str:
    text = (REPO_ROOT / "CHANGELOG.md").read_text()
    match = re.search(r"^## \[(\d+\.\d+\.\d+)\]", text, flags=re.MULTILINE)
    assert match, "CHANGELOG.md 找不到任何版本段落 (## [X.Y.Z])"
    return match.group(1)


def test_app_version_matches_latest_changelog_release():
    assert APP_VERSION == _latest_changelog_release(), (
        "APP_VERSION 與 CHANGELOG 最新的版本段落不一致, 用 make release 改版號"
    )
