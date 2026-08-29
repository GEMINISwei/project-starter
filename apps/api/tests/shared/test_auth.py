from dataclasses import dataclass
from typing import Literal

import jwt
import pytest

from shared.auth.tokens import (
    WS_TICKET_TTL_SECONDS,
    create_token,
    create_ws_ticket,
    parse_token,
    parse_ws_ticket,
)
from shared.http.errors import LangException


@dataclass
class MockEnv:
    expire_hours: int = 8
    project_name: str = "test-project"
    version: str = "1.0.0"
    token_version: str = "1"
    # 至少 32 bytes：與 app/config.py 的 MIN_JWT_SECRET_LENGTH 對齊。PyJWT 會對過短的
    # HMAC 金鑰發出 InsecureKeyLengthWarning，而測試替身本來就不該比正牌設定寬鬆。
    jwt_secret_key: str = "test_secret_key_for_unit_test_at_least_32_chars"
    # 與 AppEnvProtocol 一樣收窄成 Literal —— 這裡若放寬成 str，mypy 就不會再檢查
    # 「MockEnv 是否真的滿足 shared 的契約」，測試替身會悄悄比正牌 env 寬鬆。
    jwt_algorithm: Literal["HS256"] = "HS256"


def test_create_token_returns_bearer():
    env = MockEnv()
    result = create_token({"username": "alice", "auth_version": 1}, env)
    assert "access_token" in result
    assert result["token_type"] == "bearer"
    assert isinstance(result["access_token"], str)
    assert len(result["access_token"]) > 0


def test_parse_token_returns_username():
    env = MockEnv()
    token_data = create_token({"username": "alice", "auth_version": 1}, env)
    result = parse_token(token_data["access_token"], env)
    assert result["username"] == "alice"


def test_parse_token_none_raises_401():
    env = MockEnv()
    with pytest.raises(LangException) as exc_info:
        parse_token(None, env)
    assert exc_info.value.status_code == 401


def test_parse_token_invalid_raises_401():
    env = MockEnv()
    with pytest.raises(LangException) as exc_info:
        parse_token("invalid.token.string", env)
    assert exc_info.value.status_code == 401


def test_parse_token_wrong_project_name_raises_401():
    env_a = MockEnv(project_name="project-a")
    env_b = MockEnv(project_name="project-b")
    token_data = create_token({"username": "alice", "auth_version": 1}, env_a)
    with pytest.raises(LangException) as exc_info:
        parse_token(token_data["access_token"], env_b)
    assert exc_info.value.status_code == 401


def test_parse_token_wrong_token_version_raises_401():
    env_v1 = MockEnv(token_version="1")
    env_v2 = MockEnv(token_version="2")
    token_data = create_token({"username": "alice", "auth_version": 1}, env_v1)
    with pytest.raises(LangException) as exc_info:
        parse_token(token_data["access_token"], env_v2)
    assert exc_info.value.status_code == 401


def test_parse_token_survives_app_version_bump():
    """改 app version 不應該讓既有 token 失效（token 只綁 token_version）。"""
    env_v1 = MockEnv(version="1.0.0")
    env_v2 = MockEnv(version="2.0.0")
    token_data = create_token({"username": "alice", "auth_version": 1}, env_v1)
    assert parse_token(token_data["access_token"], env_v2)["username"] == "alice"


# ── WebSocket ticket 與 session token 的用途隔離 ────────────────────────────────
#
# WS handshake 沒辦法帶自訂 header，憑證只能放在 query string（會進 nginx log 與瀏覽器
# 歷史）。因此 ticket 必須是短效、且**不能**被拿來當 session token 用。
# 下面幾個測試釘住的就是這個不變量 —— 一旦有人把兩者合而為一，這裡會立刻失敗。


def test_ws_ticket_round_trip():
    env = MockEnv()
    ticket = create_ws_ticket("alice", env, 1)

    assert parse_ws_ticket(ticket, env) == {"username": "alice", "auth_version": 1}


def test_session_token_is_rejected_as_ws_ticket():
    env = MockEnv()
    session_token = create_token({"username": "alice", "auth_version": 1}, env)["access_token"]

    with pytest.raises(LangException) as exc_info:
        parse_ws_ticket(session_token, env)

    assert exc_info.value.status_code == 401


def test_ws_ticket_is_rejected_as_session_token():
    """最重要的一條：ticket 外洩時不能被拿去當登入憑證使用。"""
    env = MockEnv()
    ticket = create_ws_ticket("alice", env, 1)

    with pytest.raises(LangException) as exc_info:
        parse_token(ticket, env)

    assert exc_info.value.status_code == 401


def test_ws_ticket_is_short_lived():
    """ticket 的有效期要遠短於 session token，外洩後可用的時間才夠小。"""
    env = MockEnv(expire_hours=8)
    payload = jwt.decode(
        create_ws_ticket("alice", env, 1),
        env.jwt_secret_key,
        algorithms=[env.jwt_algorithm],
    )
    session_payload = jwt.decode(
        create_token({"username": "alice", "auth_version": 1}, env)["access_token"],
        env.jwt_secret_key,
        algorithms=[env.jwt_algorithm],
    )

    assert WS_TICKET_TTL_SECONDS <= 300
    assert payload["exp"] < session_payload["exp"]


def test_ws_ticket_respects_token_version_revocation():
    """調高 TOKEN_VERSION 要能同時作廢已簽發的 ticket。"""
    ticket = create_ws_ticket("alice", MockEnv(token_version="1"), 1)

    with pytest.raises(LangException) as exc_info:
        parse_ws_ticket(ticket, MockEnv(token_version="2"))

    assert exc_info.value.status_code == 401


@pytest.mark.parametrize("missing_claim", ["typ", "uv"])
def test_parse_token_rejects_missing_required_claim(missing_claim: str):
    env = MockEnv()
    token = create_token({"username": "alice", "auth_version": 1}, env)["access_token"]
    payload = jwt.decode(token, env.jwt_secret_key, algorithms=[env.jwt_algorithm])
    del payload[missing_claim]
    malformed = jwt.encode(payload, env.jwt_secret_key, algorithm=env.jwt_algorithm)

    with pytest.raises(LangException) as exc_info:
        parse_token(malformed, env)

    assert exc_info.value.status_code == 401
