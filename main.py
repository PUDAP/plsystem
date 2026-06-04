"""
Main entry point for the PL system PUDA edge service.

The service connects PUDA/NATS to the lab's existing SiLA server. PUDA owns
agent orchestration and provenance; SiLA owns instrument access.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time

from pydantic_settings import BaseSettings, SettingsConfigDict
from puda import EdgeNatsClient, EdgeRunner

from driver import Driver


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)


class Config(BaseSettings):
    machine_id: str
    nats_servers: str

    sila_host: str
    sila_port: int
    sila_tls: bool
    sila_insecure: bool
    sila_root_cert_path: str
    sila_dry_run: bool

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def nats_server_list(self) -> list[str]:
        return [s.strip() for s in self.nats_servers.split(",") if s.strip()]


def load_config() -> Config:
    """Load and validate configuration; exit process on failure."""
    try:
        return Config()
    except Exception as exc:
        logger.error("Failed to load configuration: %s", exc, exc_info=True)
        sys.exit(1)


async def main() -> None:
    """Initialize the PL system driver and run the PUDA edge service."""
    config = load_config()
    logger.info("Config loaded for machine_id=%s", config.machine_id)

    driver = Driver(
        sila_host=config.sila_host,
        sila_port=config.sila_port,
        sila_tls=config.sila_tls,
        sila_insecure=config.sila_insecure,
        sila_root_cert_path=config.sila_root_cert_path,
        dry_run=config.sila_dry_run,
    )
    driver.startup()

    edge_nats_client = EdgeNatsClient(
        servers=config.nats_server_list,
        machine_id=config.machine_id,
    )

    async def telemetry_handler() -> None:
        #status = driver.get_status()
        await edge_nats_client.publish_heartbeat()
        
        #await edge_nats_client.publish_position(driver.get_position())
        #await edge_nats_client.publish_health(
        #    {
        #        "sila_host": config.sila_host,
        #        "sila_port": config.sila_port,
        #        "sila_connected": status["sila_connected"],
        #        "connection_status": status["connection_status"],
        #        "last_error": status["last_error"],
        #    }
        #)

    runner = EdgeRunner(
        nats_client=edge_nats_client,
        machine_driver=driver,
        telemetry_handler=telemetry_handler,
        state_handler=None,
    )
    await runner.connect()
    logger.info("==================== %s Edge Service Ready ====================", config.machine_id)
    await runner.run()


if __name__ == "__main__":
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            logger.warning("Gracefully stopping...")
            sys.exit(0)
        except Exception as exc:
            logger.error("Fatal error: %s", exc, exc_info=True)
            time.sleep(5)
