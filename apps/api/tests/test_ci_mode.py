"""`.github/scripts/ci-mode.sh`: 這次 CI 要跑完整的檢查, 還是只跑單元測試。

PR 只改了 Markdown 時是 docs 模式: 文件不進 image、不影響 build, 但連結、ADR 與 skill 的格式
由單元測試檢查, 所以單元測試照跑, 其餘跳過。其他情況一律完整模式:

- 判斷用白名單: 全部是 `.md` 才放寬, 新的檔案類型預設跑完整。
- 不是 PR 的事件 (push main、deploy.yml 的 workflow_call、手動執行) 一律完整:
  部署靠 main 的 CI 結果。
- 拿不到改動清單 (空的) 時當成完整, 不當成「沒改東西」。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import shutil
import subprocess

import pytest

from tests.test_docs import REPO_ROOT

SCRIPT = REPO_ROOT / ".github" / "scripts" / "ci-mode.sh"
BASH = shutil.which("bash") or "/bin/bash"


def ci_mode(event: str, *files: str) -> str:
    # 輸入是 `git diff --name-only` 的格式, 一行一個路徑。
    result = subprocess.run(  # noqa: S603
        [BASH, str(SCRIPT), event],
        input="".join(f"{path}\n" for path in files),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_ci_mode_is_docs_when_pull_request_changes_only_markdown() -> None:
    files = ("docs/workflow.md", "AGENTS.md", ".agents/skills/watch-pr/SKILL.md")
    assert ci_mode("pull_request", *files) == "docs"


@pytest.mark.parametrize(
    "other",
    ["apps/api/main.py", ".github/workflows/ci.yml", "docs/diagram.png", "Makefile", "notes.mdx"],
)
def test_ci_mode_is_full_when_pull_request_changes_any_other_file(other: str) -> None:
    assert ci_mode("pull_request", "docs/workflow.md", other) == "full"


@pytest.mark.parametrize("event", ["push", "workflow_dispatch", "release"])
def test_ci_mode_is_full_when_event_is_not_pull_request(event: str) -> None:
    assert ci_mode(event, "docs/workflow.md") == "full"


def test_ci_mode_is_full_when_no_files_changed() -> None:
    assert ci_mode("pull_request") == "full"
