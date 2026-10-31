"""產生檔與 lock 檔不出現在 AI agent 的搜尋結果裡。

這些檔案要進版控, 不能放 `.gitignore`; Claude 與 Codex 的搜尋底層都是 ripgrep, 它另外讀 `.ignore`。
lock 檔與 OpenAPI 契約動輒幾十到幾百 KB, 搜一個端點名稱就會撞進去, 整段結果都要讀進上下文。
`.ignore` 被刪掉或改壞時不會有任何東西報錯, 只是每次搜尋都變貴。

`.ignore` 與 `.gitignore` 同語法, 用 `git check-ignore --no-index` 拿它當排除清單來判斷,
不必另外安裝 ripgrep。
"""

import re
import shutil
import subprocess

from tests.test_docs import REPO_ROOT

GIT = shutil.which("git") or "/usr/bin/git"
IGNORE = REPO_ROOT / ".ignore"
COMMON_SH = REPO_ROOT / "scripts" / "lib" / "common.sh"


def generated_paths() -> list[str]:
    """`make gen-types` 寫進 repo 的兩份, 路徑以 common.sh 為準。"""
    text = COMMON_SH.read_text(encoding="utf-8")
    return re.findall(r'^readonly (?:CONTRACT|WEB_SCHEMA)="([^"]+)"', text, flags=re.MULTILINE)


def lock_files() -> list[str]:
    tracked = subprocess.run(  # noqa: S603
        [GIT, "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, check=True, text=True
    ).stdout.split("\0")
    return [name for name in tracked if name.endswith(("package-lock.json", "uv.lock"))]


def test_generated_and_lock_files_are_hidden_from_agent_search() -> None:
    expected = generated_paths() + lock_files()
    assert len(generated_paths()) == 2, "common.sh 找不到 CONTRACT 與 WEB_SCHEMA"
    assert IGNORE.exists(), ".ignore 不存在"
    result = subprocess.run(  # noqa: S603
        [GIT, "-c", f"core.excludesFile={IGNORE}", "check-ignore", "--no-index", *expected],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    ignored = set(result.stdout.split())
    missing = [path for path in expected if path not in ignored]
    assert not missing, f".ignore 沒有排除: {missing}"
