"""PR 的改動檢查 (`.github/scripts/check-pr-changes.py`, 由 pr.yml 執行)。

`pr` 是 required check, 過不了就不能合併。只檢查一件事: 這個 PR 新增的抑制註解
(noqa、type: ignore、eslint-disable、ts-expect-error、skip) 同一行要寫理由。

實作後改測試檔、動到防線檔案或 agent 的說明, 不要求在 PR 描述裡再寫一次: 改的當下 hook 已經
請使用者確認, 審查時 diff 的檔案清單也看得到 (docs/extending/agent-hooks.md)。

每個測試用暫存的 git repo 造出 PR 的 commit, 再把 base 與 head 交給腳本。
"""

import re
import subprocess
from pathlib import Path

import pytest

from tests.test_docs import REPO_ROOT

SCRIPT = REPO_ROOT / ".github" / "scripts" / "check-pr-changes.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pr.yml"

TEST = "apps/api/tests/modules/users/test_service.py"
SOURCE = "apps/api/modules/users/service.py"
# 抑制註解拆開來寫: 這個檔案本身也會被 PR 檢查, 字面上寫完整的話會被當成新增的抑制註解。
NOQA = "# " + "noqa"
IGNORE = "# " + "type: ignore"
ESLINT = "// " + "eslint-disable-next-line"
TS_EXPECT = "// " + "@ts-expect-error"


def body(checks: str = "- [ ] 在主機上跑一次", verification: str = "- `make check`：通過") -> str:
    return f"## 摘要\n\n- 改了 x\n\n## 驗證\n\n{verification}\n\n## 檢查\n\n{checks}\n"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(  # noqa: S603 # 參數固定, 只在暫存 repo 裡跑
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],  # noqa: S607
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def commit(repo: Path, files: dict[str, str], message: str = "change") -> None:
    for path, text in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """main 上有原始碼與測試, 目前在功能分支上。"""
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    commit(path, {SOURCE: "x = 1\n", TEST: "def test_x():\n    assert True\n", "README.md": "x\n"})
    git(path, "switch", "-q", "-c", "feat/x")
    return path


def check(repo: Path, pr_body: str) -> subprocess.CompletedProcess[str]:
    env = {
        "BASE_SHA": git(repo, "merge-base", "main", "HEAD"),
        "HEAD_SHA": git(repo, "rev-parse", "HEAD"),
        "PR_BODY": pr_body,
        "PATH": "/usr/bin:/bin",
    }
    return subprocess.run(  # noqa: S603 # 執行受測的腳本
        ["python3", SCRIPT],  # noqa: S607
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_test_and_protected_changes_need_no_description(repo: Path) -> None:
    commit(repo, {SOURCE: "x = 2\n"}, "impl")
    commit(
        repo,
        {
            TEST: "def test_x():\n    assert 1\n",
            ".github/workflows/ci.yml": "name: CI\n",
            "AGENTS.md": "x\n",
            ".agents/skills/feature-workflow/SKILL.md": "x\n",
        },
        "change test and guard files",
    )
    result = check(repo, body())
    assert result.returncode == 0, result.stderr


WITHOUT_REASON = [
    ("apps/api/x.py", f"import os  {NOQA}: F401\n"),
    ("apps/api/x.py", f"y = f()  {IGNORE}[arg-type]\n"),
    ("apps/web/x.ts", f"{ESLINT} no-console\n"),
    ("apps/web/x.ts", f"{TS_EXPECT}\n"),
    ("apps/api/tests/test_x.py", "@pytest.mark." + "skip\n"),
    ("apps/web/tests/x.test.ts", "it." + "skip('a', () => {})\n"),
]

WITH_REASON = [
    ("apps/api/x.py", f"import os  {NOQA}: F401  # 重新匯出給外部用\n"),
    ("apps/api/x.py", f"y = f()  {IGNORE}[arg-type]  # 第三方套件的型別標錯\n"),
    ("apps/web/x.ts", f"{ESLINT} no-console -- 除錯用的輸出\n"),
    ("apps/web/x.ts", f"{TS_EXPECT} 端點不存在\n"),
    ("apps/api/tests/test_x.py", "@pytest.mark." + 'skip(reason="需要網路")\n'),
    ("apps/web/tests/x.test.ts", "it." + "skip('a', () => {}) // 等上游修正\n"),
]


@pytest.mark.parametrize(("path", "line"), WITHOUT_REASON)
def test_new_suppression_without_reason_fails(repo: Path, path: str, line: str) -> None:
    commit(repo, {path: line})
    result = check(repo, body())
    assert result.returncode != 0
    assert path in result.stderr


@pytest.mark.parametrize(("path", "line"), WITH_REASON)
def test_new_suppression_with_reason_passes(repo: Path, path: str, line: str) -> None:
    commit(repo, {path: line})
    assert check(repo, body()).returncode == 0


def test_existing_suppressions_are_not_checked(repo: Path) -> None:
    git(repo, "switch", "-q", "main")
    commit(repo, {"apps/api/x.py": f"import os  {NOQA}: F401\nz = 1\n"})
    git(repo, "switch", "-q", "feat/x")
    git(repo, "merge", "-q", "--ff-only", "main")
    git(repo, "branch", "-f", "main", "HEAD")
    commit(repo, {"apps/api/x.py": f"import os  {NOQA}: F401\nz = 2\n"})
    assert check(repo, body()).returncode == 0


@pytest.mark.parametrize(
    ("line", "passes"),
    [
        (f"run(cmd)  {NOQA}: S603\n", True),
        (f"run(cmd)  {NOQA}: S603, S607\n", True),
        (f"run(cmd)  {NOQA}: S603, F401\n", False),
    ],
)
def test_subprocess_noqa_is_exempt(repo: Path, line: str, passes: bool) -> None:
    # 呼叫子行程的警告: hook 與測試用固定參數呼叫 git、gh 是常態, 每次寫理由只是噪音。
    commit(repo, {"apps/api/x.py": line})
    assert (check(repo, body()).returncode == 0) is passes


def test_pr_workflow_checks_changes_with_full_history() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    # 預設只抓一個 commit, 看不到 PR 裡每個 commit 改了什麼。
    assert re.search(r"uses: actions/checkout@\S+\s*\n\s*with:\s*\n\s*fetch-depth: 0", workflow)
    steps = re.split(r"\n\s*- (?=name:|uses:)", workflow)
    change_steps = [step for step in steps if "check-pr-changes.py" in step]
    assert change_steps, "pr.yml 要執行 .github/scripts/check-pr-changes.py"
    for name in ("BASE_SHA", "HEAD_SHA"):
        assert f"{name}:" in change_steps[0], f"執行 check-pr-changes.py 的步驟要帶 {name}"
