from httpx import AsyncClient

from app.server import app
from shared.auth.tokens import create_token


def token_for(username: str) -> str:
    return create_token({"username": username, "auth_version": 1}, app.state.env)["access_token"]


def authenticate(client: AsyncClient, username: str) -> None:
    client.cookies.set("access_token", token_for(username))
