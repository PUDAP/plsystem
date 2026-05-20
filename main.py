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
    machine_id: str = "plsystem"
    nats_servers: str

    sila_host: str
    sila_port: int = 50054
    sila_tls: bool = True
    sila_insecure: bool = False
    sila_root_cert_path: str | None = None
    sila_dry_run: bool = False

    lac_min_percent: float = 0.0
    lac_max_percent: float = 100.0
    stage_x_min_mm: float | None = None
    stage_x_max_mm: float | None = None
    stage_y_min_mm: float | None = None
    stage_y_max_mm: float | None = None
    stage_z_min_voltage: float = 0.0
    stage_z_max_voltage: float = 150.0
    default_shutter_timeout: float = 5.0

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
        lac_min_percent=config.lac_min_percent,
        lac_max_percent=config.lac_max_percent,
        stage_x_min_mm=config.stage_x_min_mm,
        stage_x_max_mm=config.stage_x_max_mm,
        stage_y_min_mm=config.stage_y_min_mm,
        stage_y_max_mm=config.stage_y_max_mm,
        stage_z_min_voltage=config.stage_z_min_voltage,
        stage_z_max_voltage=config.stage_z_max_voltage,
        default_shutter_timeout=config.default_shutter_timeout,
    )
    driver.startup()

    edge_nats_client = EdgeNatsClient(
        servers=config.nats_server_list,
        machine_id=config.machine_id,
    )

    async def telemetry_handler() -> None:
        status = driver.get_status()
        await edge_nats_client.publish_heartbeat()
        await edge_nats_client.publish_position(driver.get_position())
        await edge_nats_client.publish_health(
            {
                "sila_host": config.sila_host,
                "sila_port": config.sila_port,
                "sila_connected": status["sila_connected"],
                "connection_status": status["connection_status"],
                "last_error": status["last_error"],
            }
        )

    runner = EdgeRunner(
        nats_client=edge_nats_client,
        machine_driver=driver,
        telemetry_handler=telemetry_handler,
        state_handler=driver.get_status,
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
