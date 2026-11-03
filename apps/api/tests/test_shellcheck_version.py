"""shellcheck 的版本: 本機與 CI 用同一版, 規則才一致。

不同版本對同一份腳本的判斷不同 (例如 `A && B || C` 的 SC2015), 版本不一致時會本機綠、CI 紅。
版本只寫在 `scripts/lib/shellcheck.sh` 一處: CI 從那裡讀版本, 下載指定版本並核對 sha256;
`make check lint` 也拿它比對本機的 shellcheck —— 本機不同只提醒 (升級由各自的套件管理決定),
CI 上不同就失敗 (那代表安裝步驟沒有生效)。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

from tests.test_docs import REPO_ROOT

LIB = REPO_ROOT / "scripts" / "lib" / "shellcheck.sh"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
BASH = shutil.which("bash") or "/bin/bash"


def pinned_version() -> str:
    match = re.search(r'^SHELLCHECK_VERSION="([0-9.]+)"$', LIB.read_text(), flags=re.MULTILINE)
    assert match, "scripts/lib/shellcheck.sh 要定義 SHELLCHECK_VERSION"
    return match.group(1)


def check_version(
    tmp_path: Path, local_version: str, *, ci: bool
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "shellcheck"
    output = f"ShellCheck - shell script analysis tool\\nversion: {local_version}\\n"
    fake.write_text(f"#!/bin/sh\nprintf '{output}'\n")
    fake.chmod(0o755)
    env = {key: value for key, value in os.environ.items() if key != "CI"}
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    if ci:
        env["CI"] = "true"
    # 指令是這支測試自己給的固定值, 不是外部輸入。
    return subprocess.run(  # noqa: S603
        [BASH, "-c", f'source "{LIB}" && check_shellcheck_version'],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_shellcheck_version_check_passes_on_pinned_version(tmp_path: Path) -> None:
    result = check_version(tmp_path, pinned_version(), ci=True)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_shellcheck_version_check_warns_locally_on_other_version(tmp_path: Path) -> None:
    result = check_version(tmp_path, "0.1.0", ci=False)
    assert result.returncode == 0
    assert "0.1.0" in result.stderr
    assert pinned_version() in result.stderr


def test_shellcheck_version_check_fails_in_ci_on_other_version(tmp_path: Path) -> None:
    result = check_version(tmp_path, "0.1.0", ci=True)
    assert result.returncode != 0
    assert pinned_version() in result.stderr


def _check_job_steps() -> list[str]:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"^  check:\n(.*?)(?=^  \S|\Z)", workflow, flags=re.MULTILINE | re.DOTALL)
    assert match, "ci.yml 找不到 check job"
    return re.split(r"^      - ", match.group(1), flags=re.MULTILINE)[1:]


def test_ci_installs_pinned_shellcheck_before_make_check() -> None:
    steps = _check_job_steps()
    installs = [i for i, step in enumerate(steps) if "koalaman/shellcheck/releases" in step]
    assert len(installs) == 1, "check job 要有一個安裝指定版本 shellcheck 的步驟"
    install = steps[installs[0]]
    # 版本從 lib 讀, 不在 workflow 另抄一份; 下載的檔案核對 sha256;
    # 放在 PATH 最前面, 蓋過 runner 內建的那一版。
    assert "scripts/lib/shellcheck.sh" in install
    assert re.search(r"sha256sum (-c|--check)", install)
    assert "GITHUB_PATH" in install
    make_check = next(
        i for i, step in enumerate(steps) if re.match(r"run: make check$", step, re.MULTILINE)
    )
    assert installs[0] < make_check
