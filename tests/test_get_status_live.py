"""
Live integration test for Driver.get_status() against the PL system SiLA server.

Requires a reachable SiLA server and SILA_DRY_RUN=false (typically via .env).
Set SILA_HOST, SILA_PORT, and TLS settings to match the lab server.
"""

from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from driver import Driver


class SilaLiveConfig(BaseSettings):
    sila_host: str = "127.0.0.1"
    sila_port: int = 50054
    sila_tls: bool = True
    sila_insecure: bool = False
    sila_root_cert_path: str = ""
    sila_dry_run: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


def _format_status(status: dict[str, Any]) -> str:
    return json.dumps(status, indent=2, default=str)


def _run_get_status_timed(driver: Driver) -> tuple[dict[str, Any], float]:
    start = time.perf_counter()
    status = driver.get_status()
    elapsed_s = time.perf_counter() - start
    return status, elapsed_s


@unittest.skipIf(SilaLiveConfig().sila_dry_run, "SILA_DRY_RUN=true; live SiLA test skipped")
class TestGetStatusLive(unittest.TestCase):
    """Exercise get_status() with dry_run=False against a real SiLA server."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = SilaLiveConfig()
        cls.driver = Driver(
            sila_host=cls.config.sila_host,
            sila_port=cls.config.sila_port,
            sila_tls=cls.config.sila_tls,
            sila_insecure=cls.config.sila_insecure,
            sila_root_cert_path=cls.config.sila_root_cert_path or None,
            dry_run=False,
        )
        try:
            cls.driver.startup()
        except Exception as exc:
            raise unittest.SkipTest(f"SiLA startup failed: {exc}") from exc

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "driver"):
            cls.driver.shutdown()

    def test_get_status_live_reports_timing_and_output(self) -> None:
        status, elapsed_s = _run_get_status_timed(self.driver)

        print(f"\nget_status() elapsed: {elapsed_s:.3f} s")
        print(_format_status(status))

        self.assertTrue(status["sila_connected"])
        self.assertIn(status["connection_status"], ("sila_connected", "connected"))
        self.assertEqual(status["sila_host"], self.config.sila_host)
        self.assertEqual(status["sila_port"], self.config.sila_port)
        for feature_name in Driver.PROPERTY_NAMES:
            self.assertIn(feature_name, status)
        self.assertIn("LACControl", status)
        self.assertIn("ShutterControl", status)
        self.assertIn("Mode", status["ShutterControl"])
        self.assertLess(elapsed_s, 120.0, "get_status() took longer than 120 s")


if __name__ == "__main__":
    unittest.main(verbosity=2)
