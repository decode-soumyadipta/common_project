"""Server entrypoint for centralized API node."""

import uvicorn

from platform_core.config import settings
from server_gateway.api.app import app


def main() -> None:
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_level="info")


if __name__ == "__main__":
    main()
