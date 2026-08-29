import uvicorn

from app.config import env

if __name__ == "__main__":
    uvicorn.run(
        "app.server:app",
        # 服務跑在容器裡，必須綁 0.0.0.0 才能被 compose 網路內的 nginx 連到；
        # 對外只有 nginx 那個 port 是 publish 的（見 infra/docker/docker-compose.yml）。
        host="0.0.0.0",  # noqa: S104
        port=8000,
        reload=env.mode == "development",
        access_log=False,
    )
