# PL System SiLA Summary

This summary was derived from the XML files in `features/`.

## LACControl

- `MoveTo(TargetPercent: Real 0..100)` -> `StartPercent`, `StartAdc`, `EndPercent`, `EndAdc`, `TravelPercent`
- `MoveToAlias(Alias: String)` -> same movement response
- `Configure(SpeedPercent, AccuracyPercent, RetractLimitPercent, ExtendLimitPercent)` -> `Message`
- `GetStatus()` -> connection, position, speed, accuracy, retract/extend limits
- `GetPosition()` -> `CurrentPercent`, `CurrentAdc`

Valid aliases: `LASER`, `WHITE_LIGHT`, `RETRACTED`, `EXTENDED`, `MID`.

## LEDDriverControl

- `SwitchLedOutput(EnableLedOutput: Boolean)` -> `Status`
- Properties: `LedInfo`, `LedCurrentSetpoint`, `LastError`

## PLStageControl

- `StageXYMove(XPos: Real, YPos: Real)` -> `Success`, `Message`
- `StageXYHoming()` -> `Success`, `Message`
- `StageXYToCatch()` -> `Success`, `Message`
- `StageZSetVoltage(Voltage: Real)` -> `Success`, `SetVoltage`, `Message`
- Properties: `StageXYDeviceInfo`, `StageZDeviceInfo`

## ShutterControl

- `OpenShutter(Channel: Integer 1..2, Timeout: Real)` -> `Success`, `Message`
- `CloseShutter(Channel: Integer 1..2, Timeout: Real)` -> `Success`, `Message`
- `Identify()` -> `DeviceId`
- `GetMode()` -> `Mode`
- `SetMode(Mode: Integer 0..3)` -> `Reply`
- `GetShutterState(Channel: Integer 1..2)` -> `IsOpen`, `RawState`

Mode values: `0=Manual`, `1=External`, `2=Internal`, `3=Triggered`.

## SpectrometerControl

- `SpectrometerMeasureOnce(IntegrationTimeMs: Real, Averages: Integer)` -> `Success`, `PlotFilePath`
- Property: `SpectrometerDeviceInfo`

## ThorlabsCameraControl

- `DisposeThorlabsCameraSdk()` -> `Success`, `Message`
- `CaptureAndSave(ExposureMs, FileFormat, GainDb, BinX, BinY, FrameRateFps, OutputBitDepth, UseRoi, RoiUpperLeftX, RoiUpperLeftY, RoiLowerRightX, RoiLowerRightY)` -> `Success`, `FilePath`, `ErrorMessage`
- Property: `ThorlabsCameraDeviceInfo`
