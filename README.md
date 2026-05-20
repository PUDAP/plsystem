# plsystem

PUDA edge driver for the PL system SiLA interface.

This repository is scaffolded from `PUDAP/machine-template`. It keeps the lab's
existing SiLA server as the hardware-facing boundary while exposing a PUDA/NATS
driver surface for agentic workflows.

## Architecture

```text
PUDA agent/workflow
  -> PUDA NATS subjects
  -> plsystem edge service
  -> SiLA 2 client
  -> lab PL system SiLA server
  -> PL system hardware
```

## Repository Contents

```text
plsystem/
  driver.py                                  # Multi-feature PL system PUDA driver
  main.py                                    # PUDA/NATS edge runtime
  features/*.sila.xml                        # Source SiLA feature contracts
  docs/PL_system_SiLA_summary.md             # Human-readable feature summary
  protocols/smoke_test.json                  # Dry-run command sequence
  .env.example                               # Runtime configuration template
  compose.yml                                # Container runner
```

## SiLA Features

The driver maps these feature XML contracts into public PUDA methods:

- `LACControl`: actuator `MoveTo`, `MoveToAlias`, `Configure`, `GetStatus`, `GetPosition`
- `LEDDriverControl`: `SwitchLedOutput` and LED status properties
- `PLStageControl`: `StageXYMove`, `StageXYHoming`, `StageXYToCatch`, `StageZSetVoltage`
- `ShutterControl`: `OpenShutter`, `CloseShutter`, `Identify`, `GetMode`, `SetMode`, `GetShutterState`
- `SpectrometerControl`: `SpectrometerMeasureOnce`
- `ThorlabsCameraControl`: `CaptureAndSave`, `DisposeThorlabsCameraSdk`

The XML files in `features/` are the source of truth. If the lab updates the
SiLA API, update `driver.py` and `docs/PL_system_SiLA_summary.md` together.

## Configuration

Create a local `.env`:

```powershell
Copy-Item .env.example .env
```

Minimum live configuration:

```env
MACHINE_ID=plsystem
NATS_SERVERS=nats://127.0.0.1:4222
SILA_HOST=127.0.0.1
SILA_PORT=50054
SILA_DRY_RUN=false
```

For local tests without hardware:

```env
SILA_DRY_RUN=true
```

Safety fields:

```env
LAC_MIN_PERCENT=0
LAC_MAX_PERCENT=100
STAGE_X_MIN_MM=
STAGE_X_MAX_MM=
STAGE_Y_MIN_MM=
STAGE_Y_MAX_MM=
STAGE_Z_MIN_VOLTAGE=0
STAGE_Z_MAX_VOLTAGE=150
DEFAULT_SHUTTER_TIMEOUT=5
```

## Run Locally

```powershell
uv sync
uv run python main.py
```

For a dry-run driver smoke test:

```powershell
uv run python -c "from driver import Driver; d=Driver('127.0.0.1', dry_run=True); d.startup(); print(d.StageXYHoming()); print(d.MoveToAlias('MID')); print(d.SwitchLedOutput(True)); print(d.OpenShutter(1)); print(d.SpectrometerMeasureOnce(50, 1)); print(d.CaptureAndSave(10)); print(d.get_status())"
```

## Run With Docker

```powershell
Copy-Item .env.example .env
docker compose -f compose.yml up -d --build
docker compose -f compose.yml logs -f
```

Stop:

```powershell
docker compose -f compose.yml down
```

## Validation

Before connecting hardware:

```powershell
python -m py_compile main.py driver.py
uv run python -c "from driver import Driver; d=Driver('127.0.0.1', dry_run=True); d.startup(); d.StageXYMove(0, 0); d.StageZSetVoltage(1); d.OpenShutter(1); d.CloseShutter(1); print(d.get_position())"
```

Then validate against the lab SiLA server:

1. Start the PL system SiLA server.
2. Set `SILA_HOST`, `SILA_PORT`, TLS/certificate settings, and safety limits.
3. Run `uv run python main.py`.
4. From PUDA, call `get_status`, then non-motion queries such as `Identify` and `GetMode`.
5. Only after lab approval, call bounded stage, actuator, shutter, spectrometer, and camera commands.

## Notes

- PUDA remains the orchestration/provenance layer.
- SiLA remains the hardware API boundary.
- NATS subject routing is controlled by `MACHINE_ID`.
- XY position readback is not present in the provided SiLA XML, so `get_position()` reports LAC position and Z-stage info from SiLA, with dry-run XY values only during offline tests.
