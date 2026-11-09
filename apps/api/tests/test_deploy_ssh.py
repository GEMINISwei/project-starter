"""deploy.yml 連主機前的準備 (`.github/scripts/deploy-ssh.sh`)。

migration-check 與 deploy 都要連主機, 兩邊共用這支: 改連線方式時只改一處, 不會一個 job 過、
另一個 job 才在碰主機時失敗。

- 剛建好、還沒填 secrets 的 environment 在碰主機之前就停, 列出缺的名稱, 不寫任何檔案。
- 主機指紋事先登記在 known_hosts, 私鑰只有自己讀得到。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

from tests.test_docs import REPO_ROOT

SCRIPT = REPO_ROOT / ".github" / "scripts" / "deploy-ssh.sh"
BASH = shutil.which("bash") or "/bin/bash"
SECRETS = {
    "DEPLOY_HOST": "example.test",
    "DEPLOY_USER": "deploy",
    "DEPLOY_PATH": "/srv/app",
    "DEPLOY_SSH_KEY": "-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n-----END",
    "DEPLOY_KNOWN_HOSTS": "example.test ssh-ed25519 AAAAfake",
}


def run(home: Path, **secrets: str) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ["PATH"], "HOME": str(home), **secrets}
    # 參數是這支測試自己給的固定值, 不是外部輸入。
    return subprocess.run(  # noqa: S603
        [BASH, str(SCRIPT), "production-a"], env=env, capture_output=True, text=True, check=False
    )


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_deploy_ssh_with_all_secrets_writes_key_and_known_hosts(tmp_path: Path) -> None:
    result = run(tmp_path, **SECRETS)
    assert result.returncode == 0, result.stderr
    ssh = tmp_path / ".ssh"
    assert mode(ssh) == 0o700
    assert mode(ssh / "deploy_key") == 0o600
    assert (ssh / "deploy_key").read_text() == SECRETS["DEPLOY_SSH_KEY"] + "\n"
    assert (ssh / "known_hosts").read_text() == SECRETS["DEPLOY_KNOWN_HOSTS"] + "\n"


def test_deploy_ssh_missing_secrets_lists_them_and_writes_nothing(tmp_path: Path) -> None:
    secrets = {**SECRETS, "DEPLOY_PATH": "", "DEPLOY_KNOWN_HOSTS": ""}
    result = run(tmp_path, **secrets)
    assert result.returncode != 0
    assert "production-a" in result.stderr
    assert "DEPLOY_PATH" in result.stderr
    assert "DEPLOY_KNOWN_HOSTS" in result.stderr
    assert "DEPLOY_HOST" not in result.stderr
    assert not (tmp_path / ".ssh").exists()
