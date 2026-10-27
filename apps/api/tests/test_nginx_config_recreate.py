"""nginx 的模板變了, `make start` 一定要重建 nginx。

模板是 bind mount 的, 內容變了 compose 看不出來; 官方 image 又只在啟動時展開模板。少了
內容雜湊的 label, 改了模板的發版會安靜地沿用舊設定, 直到哪天重開機才突然換成新的。
值由 `scripts/lib/compose.sh` 算; 用 `:?` 是為了沒帶到時 compose 直接失敗, 而不是展開成
空字串、讓 label 永遠不變。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import re

from tests.test_nginx_trusted_proxy import COMPOSE, nginx_service


def test_nginx_label_tracks_template_hash() -> None:
    labels = re.search(r"labels:\n((?:\s+\S+: .*\n)+)", nginx_service(COMPOSE))
    assert labels
    assert re.search(
        r"^\s+project\.nginx-config-hash: \$\{NGINX_CONFIG_HASH:\?\}$", labels.group(1), re.M
    )
