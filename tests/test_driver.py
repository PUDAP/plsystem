"""Tests for Driver position telemetry."""

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


if __name__ == "__main__":
    unittest.main()
