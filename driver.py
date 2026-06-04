"""
PUDA driver for the PL system SiLA feature set.

PUDA/NATS is the agent-facing orchestration layer. The lab's existing SiLA
server remains the instrument-facing boundary for the PL actuator, LED, stage,
shutter, spectrometer, and Thorlabs camera components.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Driver:
    """PL system driver exposed to PUDA through public methods."""

    FEATURE_NAMES = (
        "LACControl",
        "LEDDriverControl",
        "PLStageControl",
        "ShutterControl",
        "SpectrometerControl",
        "ThorlabsCameraControl",
    )

    PROPERTY_NAMES = {
        "LEDDriverControl": ("LedInfo", "LedCurrentSetpoint", "LastError"),
        "PLStageControl": ("StageXYDeviceInfo", "StageZDeviceInfo"),
        "SpectrometerControl": ("SpectrometerDeviceInfo",),
        "ThorlabsCameraControl": ("ThorlabsCameraDeviceInfo",),
    }

    # ThorlabsCameraControl.CaptureAndSave — values match SiLA server semantics.
    CAPTURE_AND_SAVE_DEFAULTS: dict[str, Any] = {
        "ExposureMs": 30.0,
        "FileFormat": "png",
        "GainDb": -1.0,
        "BinX": 1,
        "BinY": 1,
        "FrameRateFps": -1.0,
        "OutputBitDepth": 8,
        "UseRoi": False,
        "RoiUpperLeftX": 0,
        "RoiUpperLeftY": 0,
        "RoiLowerRightX": 0,
        "RoiLowerRightY": 0,
        "BlackLevel": -1,
        "HotPixelThreshold": -1,
        "PollTimeoutMs": 0,
        "LedOn": False,
        "OutputColorSpace": "sRGB",
    }

    def __init__(
        self,
        sila_host: str,
        sila_port: int = 50054,
        *,
        sila_tls: bool = True,
        sila_insecure: bool = False,
        sila_root_cert_path: str | None = None,
        dry_run: bool = False,
        lac_min_percent: float = 0.0,
        lac_max_percent: float = 100.0,
        stage_x_min_mm: float | None = None,
        stage_x_max_mm: float | None = None,
        stage_y_min_mm: float | None = None,
        stage_y_max_mm: float | None = None,
        stage_z_min_voltage: float = 0.0,
        stage_z_max_voltage: float = 150.0,
        default_shutter_timeout: float = 5.0,
    ) -> None:
        self.sila_host = sila_host
        self.sila_port = int(sila_port)
        self.sila_tls = bool(sila_tls)
        self.sila_insecure = bool(sila_insecure)
        self.sila_root_cert_path = sila_root_cert_path
        self.dry_run = bool(dry_run)

        self.lac_min_percent = float(lac_min_percent)
        self.lac_max_percent = float(lac_max_percent)
        self.stage_x_min_mm = None if stage_x_min_mm is None else float(stage_x_min_mm)
        self.stage_x_max_mm = None if stage_x_max_mm is None else float(stage_x_max_mm)
        self.stage_y_min_mm = None if stage_y_min_mm is None else float(stage_y_min_mm)
        self.stage_y_max_mm = None if stage_y_max_mm is None else float(stage_y_max_mm)
        self.stage_z_min_voltage = float(stage_z_min_voltage)
        self.stage_z_max_voltage = float(stage_z_max_voltage)
        self.default_shutter_timeout = float(default_shutter_timeout)

        self._client: Any | None = None
        self._connection_status = "not_started"
        self._last_command = ""
        self._last_response: dict[str, Any] = {}
        self._last_error = ""
        self._lac_position_percent = 0.0
        self._stage_x_mm = 0.0
        self._stage_y_mm = 0.0
        self._stage_z_voltage = 0.0
        self._led_enabled = False
        self._shutter_states: dict[int, bool] = {1: False, 2: False}

    def startup(self) -> dict[str, Any]:
        """
        Connect to the PL system SiLA server.

        Returns:
            Dictionary with connection status. This connects to the SiLA server,
            not directly to each hardware transport.
        """
        if self.dry_run:
            self._connection_status = "dry_run"
            return self._result(True, "startup")

        try:
            from sila2.client import SilaClient

            root_certs = self._read_root_certs()
            insecure = self.sila_insecure or not self.sila_tls
            self._client = SilaClient(
                self.sila_host,
                self.sila_port,
                root_certs=root_certs,
                insecure=insecure,
            )
            self._connection_status = "sila_connected"
            self._last_error = ""
            return self._result(True, "startup")
        except Exception as exc:
            self._last_error = str(exc)
            self._connection_status = "error"
            logger.exception("Failed to connect to PL system SiLA server")
            raise RuntimeError(f"Failed to connect to PL system SiLA server: {exc}") from exc

    def shutdown(self) -> dict[str, Any]:
        """
        Close the SiLA client connection.

        Returns:
            Dictionary with shutdown status.
        """
        try:
            if self._client is not None and hasattr(self._client, "close"):
                self._client.close()
            self._client = None
            self._connection_status = "closed"
            return self._result(True, "shutdown")
        except Exception as exc:
            self._last_error = str(exc)
            raise RuntimeError(f"Failed to close PL system SiLA client: {exc}") from exc

    def connect(self) -> dict[str, Any]:
        """
        Report SiLA server connectivity for PUDA generic connect semantics.

        Returns:
            Dictionary with connection status.
        """
        if self._client is None and not self.dry_run:
            return self.startup()
        return self._result(True, "connect")

    def disconnect(self) -> dict[str, Any]:
        """
        Disconnect from the SiLA server for PUDA generic disconnect semantics.

        Returns:
            Dictionary with connection status.
        """
        return self.shutdown()

    def reset(self) -> dict[str, Any]:
        """
        Software reset of the edge connection.

        Returns:
            Dictionary with startup status after reconnect.
        """
        self.shutdown()
        return self.startup()

    def home(self) -> dict[str, Any]:
        """
        Home the XY stage using the SiLA `StageXYHoming` command.

        Returns:
            Dictionary containing the SiLA homing response.
        """
        return self.StageXYHoming()

    def get_status(self) -> dict[str, Any]:
        """
        Read non-motion status from all available PL system SiLA features.

        Returns:
            Dictionary with edge status, safe SiLA properties, and LAC status.
        """
        status = {
            "sila_host": self.sila_host,
            "sila_port": self.sila_port,
            "sila_connected": self._client is not None or self.dry_run,
            "connection_status": self._connection_status,
            "last_command": self._last_command,
            "last_response": self._last_response,
            "last_error": self._last_error,
        }
        if self.dry_run:
            status.update(self._dry_run_properties())
            return status

        if self._client is None:
            return status

        for feature_name, property_names in self.PROPERTY_NAMES.items():
            feature_status = {}
            for property_name in property_names:
                feature_status[property_name] = self._safe_property(feature_name, property_name)
            status[feature_name] = feature_status
        status["LACControl"] = self._safe_command("LACControl", "GetStatus")
        status["ShutterControl"] = {
            "Mode": self._safe_command("ShutterControl", "GetMode"),
            "Channel1": self._safe_command("ShutterControl", "GetShutterState", Channel=1),
            "Channel2": self._safe_command("ShutterControl", "GetShutterState", Channel=2),
        }
        return status

    def get_position(self) -> dict[str, Any]:
        """
        Return PUDA telemetry-compatible position data.

        The SiLA XML provides LAC position and Z voltage. It does not expose XY
        readback, so XY values are the last commanded values in dry-run mode and
        otherwise omitted unless later added to the SiLA feature.
        """
        if self.dry_run:
            return {
                "lac_percent": self._lac_position_percent,
                "stage_x_mm": self._stage_x_mm,
                "stage_y_mm": self._stage_y_mm,
                "stage_z_voltage": self._stage_z_voltage,
            }
        return {
            "LACControl": self._safe_command("LACControl", "GetPosition"),
            "StageZDeviceInfo": self._safe_property("PLStageControl", "StageZDeviceInfo"),
        }

    # LACControl
    def MoveTo(self, TargetPercent: float) -> dict[str, Any]:
        """Move LAC actuator to target percent of full stroke, 0 to 100."""
        target = self._validate_range("TargetPercent", TargetPercent, self.lac_min_percent, self.lac_max_percent)
        return self._call("LACControl", "MoveTo", TargetPercent=target)

    def MoveToAlias(self, Alias: str) -> dict[str, Any]:
        """Move LAC actuator to alias: LASER, WHITE_LIGHT, RETRACTED, EXTENDED, or MID."""
        alias = str(Alias).upper()
        if alias not in {"LASER", "WHITE_LIGHT", "RETRACTED", "EXTENDED", "MID"}:
            raise ValueError("Alias must be LASER, WHITE_LIGHT, RETRACTED, EXTENDED, or MID")
        return self._call("LACControl", "MoveToAlias", Alias=alias)

    def Configure(
        self,
        SpeedPercent: float,
        AccuracyPercent: float,
        RetractLimitPercent: float,
        ExtendLimitPercent: float,
    ) -> dict[str, Any]:
        """Configure LAC speed, accuracy, and travel limits as percentages."""
        return self._call(
            "LACControl",
            "Configure",
            SpeedPercent=self._validate_percent("SpeedPercent", SpeedPercent),
            AccuracyPercent=self._validate_percent("AccuracyPercent", AccuracyPercent),
            RetractLimitPercent=self._validate_percent("RetractLimitPercent", RetractLimitPercent),
            ExtendLimitPercent=self._validate_percent("ExtendLimitPercent", ExtendLimitPercent),
        )

    def GetStatus(self) -> dict[str, Any]:
        """Get LAC actuator connection, position, speed, accuracy, and limits."""
        return self._call("LACControl", "GetStatus")

    def GetPosition(self) -> dict[str, Any]:
        """Get LAC actuator current percent and ADC position."""
        return self._call("LACControl", "GetPosition")

    # LEDDriverControl
    def SwitchLedOutput(self, EnableLedOutput: bool) -> dict[str, Any]:
        """Switch LED output on or off."""
        self._led_enabled = bool(EnableLedOutput)
        return self._call("LEDDriverControl", "SwitchLedOutput", EnableLedOutput=self._led_enabled)

    # PLStageControl
    def StageXYMove(self, XPos: float, YPos: float) -> dict[str, Any]:
        """Move XY stage to X/Y coordinates in millimeters."""
        x_pos = self._validate_optional_range("XPos", XPos, self.stage_x_min_mm, self.stage_x_max_mm)
        y_pos = self._validate_optional_range("YPos", YPos, self.stage_y_min_mm, self.stage_y_max_mm)
        self._stage_x_mm = x_pos
        self._stage_y_mm = y_pos
        return self._call("PLStageControl", "StageXYMove", XPos=x_pos, YPos=y_pos)

    def StageXYHoming(self) -> dict[str, Any]:
        """Home the XY stage and move it to its center position."""
        self._stage_x_mm = 0.0
        self._stage_y_mm = 0.0
        return self._call("PLStageControl", "StageXYHoming")

    def StageXYToCatch(self) -> dict[str, Any]:
        """Move XY stage to the catch position, X=0 mm and Y=75 mm."""
        self._stage_x_mm = 0.0
        self._stage_y_mm = 75.0
        return self._call("PLStageControl", "StageXYToCatch")

    def StageZSetVoltage(self, Voltage: float) -> dict[str, Any]:
        """Set Z stage output voltage in volts."""
        voltage = self._validate_range("Voltage", Voltage, self.stage_z_min_voltage, self.stage_z_max_voltage)
        self._stage_z_voltage = voltage
        return self._call("PLStageControl", "StageZSetVoltage", Voltage=voltage)

    # ShutterControl
    def OpenShutter(self, Channel: int, Timeout: float | None = None) -> dict[str, Any]:
        """Open shutter channel 1 or 2 with a timeout in seconds."""
        channel = self._validate_channel(Channel)
        timeout = self._validate_timeout(Timeout)
        self._shutter_states[channel] = True
        return self._call("ShutterControl", "OpenShutter", Channel=channel, Timeout=timeout)

    def CloseShutter(self, Channel: int, Timeout: float | None = None) -> dict[str, Any]:
        """Close shutter channel 1 or 2 with a timeout in seconds."""
        channel = self._validate_channel(Channel)
        timeout = self._validate_timeout(Timeout)
        self._shutter_states[channel] = False
        return self._call("ShutterControl", "CloseShutter", Channel=channel, Timeout=timeout)

    def Identify(self) -> dict[str, Any]:
        """Query the SC30 shutter controller identification string."""
        return self._call("ShutterControl", "Identify")

    def GetMode(self) -> dict[str, Any]:
        """Query shutter operating mode."""
        return self._call("ShutterControl", "GetMode")

    def SetMode(self, Mode: int) -> dict[str, Any]:
        """Set shutter mode: 0=Manual, 1=External, 2=Internal, 3=Triggered."""
        mode = int(Mode)
        if mode < 0 or mode > 3:
            raise ValueError("Mode must be 0, 1, 2, or 3")
        return self._call("ShutterControl", "SetMode", Mode=mode)

    def GetShutterState(self, Channel: int) -> dict[str, Any]:
        """Query shutter channel 1 or 2 state."""
        channel = self._validate_channel(Channel)
        return self._call("ShutterControl", "GetShutterState", Channel=channel)

    # SpectrometerControl
    def SpectrometerMeasureOnce(self, IntegrationTimeMs: float, Averages: int) -> dict[str, Any]:
        """Run one AvaSpec spectrometer measurement and return the saved plot path."""
        integration_time_ms = float(IntegrationTimeMs)
        averages = int(Averages)
        if integration_time_ms <= 0:
            raise ValueError("IntegrationTimeMs must be positive")
        if averages < 1:
            raise ValueError("Averages must be at least 1")
        return self._call(
            "SpectrometerControl",
            "SpectrometerMeasureOnce",
            IntegrationTimeMs=integration_time_ms,
            Averages=averages,
        )

    # ThorlabsCameraControl
    def DisposeThorlabsCameraSdk(self) -> dict[str, Any]:
        """Release shared Thorlabs camera SDK handles."""
        return self._call("ThorlabsCameraControl", "DisposeThorlabsCameraSdk")

    def CaptureAndSave(self) -> dict[str, Any]:
        """Acquire one Thorlabs camera frame and save it using SiLA default parameters."""
        params = dict(self.CAPTURE_AND_SAVE_DEFAULTS)
        exposure_ms = float(params["ExposureMs"])
        if exposure_ms <= 0:
            raise ValueError("ExposureMs must be positive")
        file_format = str(params["FileFormat"]).lower().lstrip(".")
        if file_format not in {"jpg", "jpeg", "png", "tif", "tiff"}:
            raise ValueError("FileFormat must be jpg, jpeg, png, tif, or tiff")
        if int(params["OutputBitDepth"]) not in {8, 16}:
            raise ValueError("OutputBitDepth must be 8 or 16")
        color_space = str(params["OutputColorSpace"])
        if color_space not in {"sRGB", "linear"}:
            raise ValueError('OutputColorSpace must be "sRGB" or "linear"')
        params["ExposureMs"] = exposure_ms
        params["FileFormat"] = file_format
        params["OutputColorSpace"] = color_space
        return self._call("ThorlabsCameraControl", "CaptureAndSave", **params)

    # Pythonic aliases for protocol authors that prefer snake_case.
    def lac_move_to(self, target_percent: float) -> dict[str, Any]:
        return self.MoveTo(TargetPercent=target_percent)

    def lac_move_to_alias(self, alias: str) -> dict[str, Any]:
        return self.MoveToAlias(Alias=alias)

    def led_output(self, enable: bool) -> dict[str, Any]:
        return self.SwitchLedOutput(EnableLedOutput=enable)

    def stage_xy_move(self, x_mm: float, y_mm: float) -> dict[str, Any]:
        return self.StageXYMove(XPos=x_mm, YPos=y_mm)

    def stage_z_set_voltage(self, voltage: float) -> dict[str, Any]:
        return self.StageZSetVoltage(Voltage=voltage)

    def open_shutter(self, channel: int, timeout: float | None = None) -> dict[str, Any]:
        return self.OpenShutter(Channel=channel, Timeout=timeout)

    def close_shutter(self, channel: int, timeout: float | None = None) -> dict[str, Any]:
        return self.CloseShutter(Channel=channel, Timeout=timeout)

    def spectrometer_measure_once(self, integration_time_ms: float, averages: int) -> dict[str, Any]:
        return self.SpectrometerMeasureOnce(IntegrationTimeMs=integration_time_ms, Averages=averages)

    def camera_capture_and_save(self) -> dict[str, Any]:
        return self.CaptureAndSave()

    def _call(self, feature_name: str, command_name: str, **kwargs: Any) -> dict[str, Any]:
        self._last_command = f"{feature_name}.{command_name}"
        if self.dry_run:
            response = self._dry_run_response(feature_name, command_name, kwargs)
            self._last_response = response
            self._last_error = ""
            return self._result(True, command_name, feature=feature_name, **response)

        self._require_client()
        try:
            command = getattr(self._feature(feature_name), command_name)
            response = self._jsonify(command(**kwargs))
            if not isinstance(response, dict):
                response = {"value": response}
            self._last_response = response
            self._last_error = self._response_error(response)
            if self._last_error:
                raise RuntimeError(self._last_error)
            return self._result(True, command_name, feature=feature_name, **response)
        except Exception as exc:
            self._last_error = str(exc)
            raise RuntimeError(f"PL system SiLA command {feature_name}.{command_name} failed: {exc}") from exc

    def _safe_command(self, feature_name: str, command_name: str, **kwargs: Any) -> dict[str, Any]:
        try:
            return self._call(feature_name, command_name, **kwargs)
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _safe_property(self, feature_name: str, property_name: str) -> Any:
        try:
            if self.dry_run:
                return self._dry_run_properties().get(feature_name, {}).get(property_name, {})
            prop = getattr(self._feature(feature_name), property_name)
            return self._jsonify(prop.get())
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _feature(self, feature_name: str) -> Any:
        self._require_client()
        return getattr(self._client, feature_name)

    def _require_client(self) -> None:
        if self._client is None:
            raise RuntimeError("SiLA client is not connected. Check startup or enable SILA_DRY_RUN.")

    def _read_root_certs(self) -> bytes | None:
        if not self.sila_tls or self.sila_insecure:
            return None
        if not self.sila_root_cert_path:
            return None
        return Path(self.sila_root_cert_path).read_bytes()

    def _result(self, success: bool, command: str, **fields: Any) -> dict[str, Any]:
        return {
            "success": bool(success),
            "command": command,
            **fields,
            "connection_status": self._connection_status,
            "last_error": self._last_error,
        }

    def _dry_run_response(self, feature_name: str, command_name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        if feature_name == "LACControl":
            return self._dry_run_lac(command_name, kwargs)
        if feature_name == "LEDDriverControl":
            return {"Status": 0}
        if feature_name == "PLStageControl":
            return self._dry_run_stage(command_name)
        if feature_name == "ShutterControl":
            return self._dry_run_shutter(command_name, kwargs)
        if feature_name == "SpectrometerControl":
            return {"Success": True, "PlotFilePath": "dry-run/spectrum.png"}
        if feature_name == "ThorlabsCameraControl":
            if command_name == "CaptureAndSave":
                return {"Success": True, "FilePath": f"dry-run/camera_capture.{kwargs['FileFormat']}", "ErrorMessage": ""}
            return {"Success": True, "Message": "dry-run camera sdk disposed"}
        return {}

    def _dry_run_lac(self, command_name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        if command_name == "MoveTo":
            start = self._lac_position_percent
            end = float(kwargs["TargetPercent"])
            self._lac_position_percent = end
            return {
                "StartPercent": start,
                "StartAdc": int(start / 100.0 * 1023),
                "EndPercent": end,
                "EndAdc": int(end / 100.0 * 1023),
                "TravelPercent": end - start,
            }
        if command_name == "MoveToAlias":
            aliases = {"LASER": 95.0, "WHITE_LIGHT": 35.0, "RETRACTED": 15.0, "EXTENDED": 85.0, "MID": 50.0}
            return self._dry_run_lac("MoveTo", {"TargetPercent": aliases[kwargs["Alias"]]})
        if command_name == "Configure":
            return {"Message": "dry-run LAC configured"}
        if command_name == "GetStatus":
            return {
                "IsConnected": True,
                "CurrentPercent": self._lac_position_percent,
                "CurrentAdc": int(self._lac_position_percent / 100.0 * 1023),
                "SpeedPercent": 50.0,
                "AccuracyPercent": 5.0,
                "RetractLimitAdc": 0,
                "ExtendLimitAdc": 1023,
            }
        if command_name == "GetPosition":
            return {
                "CurrentPercent": self._lac_position_percent,
                "CurrentAdc": int(self._lac_position_percent / 100.0 * 1023),
            }
        return {}

    def _dry_run_stage(self, command_name: str) -> dict[str, Any]:
        if command_name == "StageZSetVoltage":
            return {"Success": True, "SetVoltage": self._stage_z_voltage, "Message": "dry-run Z voltage set"}
        return {"Success": True, "Message": f"dry-run {command_name}"}

    def _dry_run_shutter(self, command_name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        if command_name == "Identify":
            return {"DeviceId": "dry-run SC30"}
        if command_name == "GetMode":
            return {"Mode": "0 Manual"}
        if command_name == "SetMode":
            return {"Reply": f"dry-run mode {kwargs['Mode']}"}
        if command_name == "GetShutterState":
            channel = int(kwargs["Channel"])
            is_open = self._shutter_states[channel]
            return {"IsOpen": is_open, "RawState": "OPEN" if is_open else "CLOSED"}
        return {"Success": True, "Message": f"dry-run {command_name}"}

    def _dry_run_properties(self) -> dict[str, Any]:
        return {
            "LEDDriverControl": {
                "LedInfo": {
                    "LEDName": "dry-run LED",
                    "LEDSerialNumber": "dry-run",
                    "LEDCurrentLimit": 1.0,
                    "LEDForwardVoltage": 3.2,
                    "LEDWavelength": 405.0,
                },
                "LedCurrentSetpoint": 0.0,
                "LastError": {"ErrorCode": 0, "ErrorMessage": ""},
            },
            "PLStageControl": {
                "StageXYDeviceInfo": {
                    "Connected": True,
                    "Description": "dry-run XY stage",
                    "SerialNumber": "dry-run",
                    "FirmwareVersion": "dry-run",
                    "Error": "",
                },
                "StageZDeviceInfo": {
                    "Connected": True,
                    "Description": "dry-run Z stage",
                    "SerialNumber": "dry-run",
                    "MaxVoltage": self.stage_z_max_voltage,
                    "CurrentVoltage": self._stage_z_voltage,
                    "Error": "",
                },
            },
            "SpectrometerControl": {
                "SpectrometerDeviceInfo": {
                    "Connected": True,
                    "Description": "dry-run AvaSpec spectrometer",
                    "SerialNumber": "dry-run",
                    "Error": "",
                }
            },
            "ThorlabsCameraControl": {
                "ThorlabsCameraDeviceInfo": {
                    "SdkAvailable": True,
                    "Connected": True,
                    "Description": "dry-run Thorlabs camera",
                    "SerialNumber": "dry-run",
                    "Model": "dry-run",
                    "FirmwareVersion": "dry-run",
                    "SensorType": "MONOCHROME",
                    "ResolutionWidth": 0,
                    "ResolutionHeight": 0,
                    "PixelSizeUmX": 0.0,
                    "PixelSizeUmY": 0.0,
                    "BitDepth": 8,
                    "AvailableCamerasCsv": "dry-run",
                    "Error": "",
                }
            },
        }

    def _response_error(self, response: dict[str, Any]) -> str:
        if response.get("Success") is False:
            return str(response.get("Message") or response.get("ErrorMessage") or "Success=False")
        if "Status" in response and int(response["Status"]) != 0:
            return f"Status={response['Status']}"
        if response.get("ErrorMessage"):
            return str(response["ErrorMessage"])
        return ""

    @staticmethod
    def _jsonify(value: Any) -> Any:
        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, dict):
            return {str(k): Driver._jsonify(v) for k, v in value.items()}
        if isinstance(value, list | tuple):
            if hasattr(value, "_asdict"):
                return {str(k): Driver._jsonify(v) for k, v in value._asdict().items()}
            return [Driver._jsonify(v) for v in value]
        if hasattr(value, "_asdict"):
            return {str(k): Driver._jsonify(v) for k, v in value._asdict().items()}
        if hasattr(value, "__dict__"):
            data = {k: v for k, v in vars(value).items() if not k.startswith("_")}
            if data:
                return {str(k): Driver._jsonify(v) for k, v in data.items()}
        return str(value)

    @staticmethod
    def _validate_percent(name: str, value: float) -> float:
        return Driver._validate_range(name, value, 0.0, 100.0)

    @staticmethod
    def _validate_range(name: str, value: float, minimum: float, maximum: float) -> float:
        value = float(value)
        if value < minimum or value > maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        return value

    @staticmethod
    def _validate_optional_range(
        name: str,
        value: float,
        minimum: float | None,
        maximum: float | None,
    ) -> float:
        value = float(value)
        if minimum is not None and value < minimum:
            raise ValueError(f"{name} must be >= {minimum}")
        if maximum is not None and value > maximum:
            raise ValueError(f"{name} must be <= {maximum}")
        return value

    @staticmethod
    def _validate_channel(channel: int) -> int:
        channel = int(channel)
        if channel not in {1, 2}:
            raise ValueError("Channel must be 1 or 2")
        return channel

    def _validate_timeout(self, timeout: float | None) -> float:
        value = self.default_shutter_timeout if timeout is None else float(timeout)
        if value <= 0:
            raise ValueError("Timeout must be positive")
        return value
