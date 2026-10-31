"""`.github/scripts/check-pr.sh`: PR 標題與描述的格式。

PR 標題 squash 後就是 main 的 commit, 所以必須是 Conventional Commits
(docs/workflow.md〈提交與 CI〉);
描述固定「摘要、驗證、檢查」三段。`gh pr create --body` 會跳過模板, 漏了也不會報錯。
標題與描述可以在 GitHub 上直接改, 所以 workflow 要在 edited 時也跑。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import os
import re
import subprocess

import pytest

from tests.test_docs import REPO_ROOT

CHECK_PR = REPO_ROOT / ".github" / "scripts" / "check-pr.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pr.yml"
TEMPLATE = REPO_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
BODY = "## 摘要\n\n- 改了 x\n\n## 驗證\n\n- `make check`：通過\n\n## 檢查\n\n- [ ] 在主機上跑一次\n"


def run_check(title: str, body: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PR_TITLE": title, "PR_BODY": body}
    return subprocess.run(  # noqa: S603
        [CHECK_PR], capture_output=True, text=True, env=env, cwd=REPO_ROOT, check=False
    )


@pytest.mark.parametrize(
    "title",
    [
        "feat: add product list page",
        "fix(api): 修正分頁",
        "chore!: 移除舊設定",
        "docs: 說明 hooks",
    ],
)
def test_pr_title_following_conventional_commits_passes(title: str) -> None:
    result = run_check(title, BODY)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "title",
    ["Add product list page", "feature: add x", "feat:add x", "feat: ", "WIP"],
)
def test_pr_title_not_following_conventional_commits_fails(title: str) -> None:
    result = run_check(title, BODY)
    assert result.returncode != 0
    assert "標題" in result.stderr


@pytest.mark.parametrize("section", ["摘要", "驗證", "檢查"])
def test_pr_body_missing_a_section_fails(section: str) -> None:
    body = BODY.replace(f"## {section}", "## 其他")
    result = run_check("feat: add x", body)
    assert result.returncode != 0
    assert section in result.stderr


def test_pr_body_left_as_template_fails() -> None:
    result = run_check("feat: add x", TEMPLATE.read_text(encoding="utf-8"))
    assert result.returncode != 0


def test_pr_body_with_crlf_line_endings_passes() -> None:
    # 在 GitHub 網頁上編輯過的描述是 CRLF。
    result = run_check("feat: add x", BODY.replace("\n", "\r\n"))
    assert result.returncode == 0, result.stderr


def test_pr_workflow_runs_when_title_or_body_is_edited() -> None:
    match = re.search(r"pull_request:\s*\n\s*types:\s*\[([^\]]*)\]", WORKFLOW.read_text("utf-8"))
    assert match, "pr.yml 要用 pull_request.types 列出觸發的事件"
    types = {item.strip() for item in match.group(1).split(",")}
    assert {"opened", "edited", "synchronize", "reopened"} <= types
