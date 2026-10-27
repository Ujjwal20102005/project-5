"""Entry point: `python -m hpapp.main`."""
from __future__ import annotations

import asyncio
import logging
import signal

from .api.server import ApiServer
from .app import Application
from .config import Settings
from .monitoring.logging_config import configure_logging


async def serve() -> None:  # pragma: no cover - exercised via container/e2e
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    app = Application(settings)
    server = ApiServer(app, settings.host, settings.port)
    port = await server.start()
    logging.getLogger("hpapp").info("listening on %s:%s strategy=%s",
                                    settings.host, port, settings.strategy)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass  # Windows: Ctrl+C is handled by asyncio.run / KeyboardInterrupt
    try:
        await stop.wait()               # graceful shutdown on SIGTERM (k8s)
    finally:
        await server.stop()
        app.close()


def main() -> None:  # pragma: no cover
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        logging.getLogger("hpapp").info("shutdown complete")


if __name__ == "__main__":  # pragma: no cover
    main()