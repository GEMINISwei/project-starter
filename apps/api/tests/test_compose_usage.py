"""compose 的旗標組合 (專案名、overlay、env 檔) 只定義在 `scripts/lib/compose.sh`。

自己組的話少一個 `-f` 或 `--env-file` 照樣跑得起來, 只是動到的是另一組容器或用了別的設定。
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_LIB = REPO_ROOT / "scripts" / "lib" / "compose.sh"

# 註解之後的內容不算; `docker-compose.yml` 這類檔名不算呼叫。
_COMPOSE_CALL = re.compile(r"^[^#]*\bdocker(?:\s+compose\b|-compose(?![.\w-]))")


def _command_files() -> list[Path]:
    return [
        *(REPO_ROOT / "scripts").rglob("*.sh"),
        *(REPO_ROOT / ".github").rglob("*.sh"),
        *(REPO_ROOT / ".github" / "workflows").glob("*.yml"),
        REPO_ROOT / "Makefile",
    ]


def test_only_compose_lib_invokes_docker_compose() -> None:
    offenders = sorted(
        f"{path.relative_to(REPO_ROOT)}:{number}"
        for path in _command_files()
        if path != COMPOSE_LIB
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if _COMPOSE_CALL.match(line)
    )
    assert offenders == []
