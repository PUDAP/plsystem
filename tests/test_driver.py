"""Tests for Driver position and status telemetry."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from driver import Driver


class TestDriverGetPosition(unittest.TestCase):
    def test_get_position_dry_run_returns_last_commanded_values(self) -> None:
        drv = Driver("127.0.0.1", dry_run=True)
        drv._lac_position_percent = 42.5
        drv._stage_x_mm = 1.25
        drv._stage_y_mm = -0.75
        drv._stage_z_voltage = 10.5

        self.assertEqual(
            drv.get_position(),
            {
                "lac_percent": 42.5,
                "stage_x_mm": 1.25,
                "stage_y_mm": -0.75,
                "stage_z_voltage": 10.5,
            },
        )

    @patch.object(Driver, "_safe_property")
    @patch.object(Driver, "_safe_command")
    def test_get_position_live_returns_sila_readbacks_via_safe_helpers(
        self,
        mock_safe_command: MagicMock,
        mock_safe_property: MagicMock,
    ) -> None:
        mock_safe_command.return_value = {"success": True, "CurrentPercent": 10.0}
        mock_safe_property.return_value = {"Connected": True, "CurrentVoltage": 5.0}

        drv = Driver("127.0.0.1", dry_run=False)
        position = drv.get_position()

        mock_safe_command.assert_called_once_with("LACControl", "GetPosition")
        mock_safe_property.assert_called_once_with("PLStageControl", "StageZDeviceInfo")
        self.assertEqual(position["LACControl"], mock_safe_command.return_value)
        self.assertEqual(position["StageZDeviceInfo"], mock_safe_property.return_value)


class TestDriverGetStatus(unittest.TestCase):
    def test_get_status_dry_run_includes_connection_and_feature_properties(self) -> None:
        drv = Driver("127.0.0.1", sila_port=50054, dry_run=True)
        drv.startup()
        drv._last_command = "MoveTo"
        drv._last_error = "none"

        status = drv.get_status()

        self.assertEqual(status["sila_host"], "127.0.0.1")
        self.assertEqual(status["sila_port"], 50054)
        self.assertTrue(status["sila_connected"])
        self.assertEqual(status["connection_status"], "dry_run")
        self.assertEqual(status["last_command"], "MoveTo")
        self.assertEqual(status["last_error"], "none")
        self.assertIn("LEDDriverControl", status)
        self.assertEqual(
            status["LEDDriverControl"]["LedInfo"]["LEDName"],
            "dry-run LED",
        )
        self.assertIn("PLStageControl", status)
        self.assertIn("SpectrometerControl", status)
        self.assertIn("ThorlabsCameraControl", status)
        self.assertNotIn("LACControl", status)

    def test_get_status_live_without_client_returns_connection_fields_only(self) -> None:
        drv = Driver("127.0.0.1", dry_run=False)

        status = drv.get_status()

        self.assertFalse(status["sila_connected"])
        self.assertEqual(status["connection_status"], "not_started")
        self.assertNotIn("LEDDriverControl", status)

    @patch.object(Driver, "_safe_property")
    @patch.object(Driver, "_safe_command")
    def test_get_status_live_queries_properties_and_safe_commands(
        self,
        mock_safe_command: MagicMock,
        mock_safe_property: MagicMock,
    ) -> None:
        mock_safe_property.return_value = {"Connected": True}
        mock_safe_command.return_value = {"success": True, "IsOpen": False}

        drv = Driver("127.0.0.1", dry_run=False)
        drv._client = object()
        drv._connection_status = "connected"

        status = drv.get_status()

        self.assertTrue(status["sila_connected"])
        self.assertEqual(status["connection_status"], "connected")
        for feature_name, property_names in Driver.PROPERTY_NAMES.items():
            for property_name in property_names:
                mock_safe_property.assert_any_call(feature_name, property_name)
        mock_safe_command.assert_any_call("LACControl", "GetStatus")
        mock_safe_command.assert_any_call("ShutterControl", "GetMode")
        mock_safe_command.assert_any_call("ShutterControl", "GetShutterState", Channel=1)
        mock_safe_command.assert_any_call("ShutterControl", "GetShutterState", Channel=2)
        self.assertEqual(status["LACControl"], mock_safe_command.return_value)
        self.assertEqual(status["ShutterControl"]["Mode"], mock_safe_command.return_value)
        self.assertEqual(status["ShutterControl"]["Channel1"], mock_safe_command.return_value)


if __name__ == "__main__":
    unittest.main()
