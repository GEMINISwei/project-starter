"""PR 的改動檢查 (`.github/scripts/check-pr-changes.py`, 由 pr.yml 執行)。

agent 這一側的 hook 換個寫法就可能繞過, 這裡在 CI 上再檢查一次。
`pr` 是 required check, 過不了就不能合併:

- 實作開始之後還改到測試檔: PR 描述要寫出那個檔案的路徑, 說明為什麼改
  (docs/testing.md〈改程式不改測試〉)
- 動到防線檔案或 agent 的說明: 「檢查」段要列出那個檔案或它的目錄, 審查時一定會被看到
- 新增的抑制註解 (noqa、type: ignore、eslint-disable、ts-expect-error、skip): 同一行要寫理由

每個測試用暫存的 git repo 造出 PR 的 commit, 再把 base、head 與描述交給腳本。
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


def test_test_change_after_implementation_without_reason_fails(repo: Path) -> None:
    commit(repo, {SOURCE: "x = 2\n"}, "impl")
    commit(repo, {TEST: "def test_x():\n    assert 1\n"}, "loosen test")
    result = check(repo, body())
    assert result.returncode != 0
    assert TEST in result.stderr


def test_test_change_after_implementation_with_reason_passes(repo: Path) -> None:
    commit(repo, {SOURCE: "x = 2\n"}, "impl")
    commit(repo, {TEST: "def test_x():\n    assert 1\n"}, "fix test")
    reason = f"- 實作後改了 `{TEST}`：原本的斷言把 x 寫死成 1，需求是可設定"
    assert check(repo, body(verification=reason)).returncode == 0


def test_tests_written_before_implementation_pass(repo: Path) -> None:
    commit(repo, {TEST: "def test_x():\n    assert 2\n"}, "test first")
    commit(repo, {SOURCE: "x = 2\n"}, "impl")
    assert check(repo, body()).returncode == 0


def test_merge_commits_are_ignored(repo: Path) -> None:
    commit(repo, {TEST: "def test_x():\n    assert 2\n"}, "test first")
    commit(repo, {SOURCE: "x = 2\n"}, "impl")
    git(repo, "switch", "-q", "main")
    commit(repo, {"apps/api/tests/test_other.py": "def test_y():\n    assert True\n"}, "main")
    git(repo, "switch", "-q", "feat/x")
    git(repo, "merge", "-q", "--no-edit", "main")
    assert check(repo, body()).returncode == 0


def test_protected_change_not_listed_in_checks_fails(repo: Path) -> None:
    commit(repo, {".github/workflows/ci.yml": "name: CI\n"})
    # 寫在「摘要」不算: 要列進「檢查」, 審查者才會逐項確認。
    pr_body = body().replace("- 改了 x", "- 改了 `.github/workflows/ci.yml`")
    result = check(repo, pr_body)
    assert result.returncode != 0
    assert ".github/workflows/ci.yml" in result.stderr


@pytest.mark.parametrize("listed", [".github/workflows/ci.yml", ".github/workflows/"])
def test_protected_change_listed_by_file_or_directory_passes(repo: Path, listed: str) -> None:
    commit(repo, {".github/workflows/ci.yml": "name: CI\n"})
    checks = f"- [ ] 動到 `{listed}`：多了一個步驟"
    assert check(repo, body(checks=checks)).returncode == 0


@pytest.mark.parametrize("path", ["AGENTS.md", ".agents/skills/feature-workflow/SKILL.md"])
def test_agent_instruction_change_must_be_listed(repo: Path, path: str) -> None:
    commit(repo, {path: "x\n"})
    assert check(repo, body()).returncode != 0
    assert check(repo, body(checks=f"- [ ] 改了 `{path}`")).returncode == 0


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
    for name in ("BASE_SHA", "HEAD_SHA", "PR_BODY"):
        assert f"{name}:" in change_steps[0], f"執行 check-pr-changes.py 的步驟要帶 {name}"


# push 與改描述幾乎同時觸發時, pr.yml 的 cancel-in-progress 可能留下帶著舊描述的那一次。
# 所以腳本執行當下用 gh 讀 PR 目前的描述, 事件帶的 PR_BODY 只在讀不到時才用。
def fake_gh(tmp_path: Path, current_body: str | None) -> str:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "body.md").write_text(current_body or "", encoding="utf-8")
    command = f"cat '{bin_dir / 'body.md'}'" if current_body is not None else "exit 1"
    script = bin_dir / "gh"
    script.write_text(f"#!/bin/sh\n{command}\n", encoding="utf-8")
    script.chmod(0o755)
    return f"{bin_dir}:/usr/bin:/bin"


def check_with_gh(repo: Path, event_body: str, path: str) -> subprocess.CompletedProcess[str]:
    env = {
        "BASE_SHA": git(repo, "merge-base", "main", "HEAD"),
        "HEAD_SHA": git(repo, "rev-parse", "HEAD"),
        "PR_BODY": event_body,
        "PR_NUMBER": "34",
        "PATH": path,
    }
    return subprocess.run(  # noqa: S603 # 執行受測的腳本
        ["python3", SCRIPT],  # noqa: S607
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_current_pr_body_is_used_over_event_body(repo: Path, tmp_path: Path) -> None:
    commit(repo, {".github/workflows/ci.yml": "name: CI\n"})
    stale = body()
    current = body(checks="- [ ] 動到 `.github/workflows/ci.yml`")
    assert check_with_gh(repo, stale, fake_gh(tmp_path, current)).returncode == 0


def test_event_body_is_used_when_current_body_cannot_be_read(repo: Path, tmp_path: Path) -> None:
    commit(repo, {".github/workflows/ci.yml": "name: CI\n"})
    event_body = body(checks="- [ ] 動到 `.github/workflows/ci.yml`")
    assert check_with_gh(repo, event_body, fake_gh(tmp_path, None)).returncode == 0
    assert check_with_gh(repo, body(), fake_gh(tmp_path / "x", None)).returncode != 0


def test_pr_workflow_passes_pr_number_and_token() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    steps = re.split(r"\n\s*- (?=name:|uses:)", workflow)
    change_steps = [step for step in steps if "check-pr-changes.py" in step]
    assert change_steps, "pr.yml 要執行 .github/scripts/check-pr-changes.py"
    for name in ("PR_NUMBER", "GH_TOKEN"):
        assert f"{name}:" in change_steps[0], f"執行 check-pr-changes.py 的步驟要帶 {name}"
    assert re.search(r"pull-requests:\s*read", workflow), "讀 PR 描述要 pull-requests: read 權限"
