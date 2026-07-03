from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import logging
import time

from .config import CameraConfig, CameraModeConfig
from .storage import utc_now


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaptureResult:
    path: Path
    captured_at: datetime
    status: str
    error: str | None = None


class Camera:
    def capture(self, path: Path, mode: CameraModeConfig) -> CaptureResult:
        raise NotImplementedError

    def close(self) -> None:
        return None


class MockCamera(Camera):
    def capture(self, path: Path, mode: CameraModeConfig) -> CaptureResult:  # noqa: ARG002
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xff\xd8\xff\xe0mock-jpeg\xff\xd9")
        return CaptureResult(path, utc_now(), "kept")


class PiCamera2Camera(Camera):
    """Picamera2 still capture tuned for the Arducam OV5647 day/night module."""

    def __init__(self, config: CameraConfig):
        self.config = config
        self._picam2 = None

    def capture(self, path: Path, mode: CameraModeConfig) -> CaptureResult:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._start()
            self._apply_mode(mode)
            warmup = max(0.0, float(self.config.warmup_seconds))
            if warmup:
                time.sleep(warmup)
            self._capture_with_timeout(path)
            return CaptureResult(path, utc_now(), "kept")
        except Exception as exc:
            LOGGER.exception("Scheduled camera capture failed")
            self.close()
            return CaptureResult(path, utc_now(), "error", str(exc))
        finally:
            self.close()

    def _start(self) -> None:
        if self._picam2 is not None:
            return
        from picamera2 import Picamera2

        picam2 = Picamera2()
        config = picam2.create_still_configuration(
            main={"size": (self.config.width, self.config.height), "format": "RGB888"},
            buffer_count=2,
        )
        picam2.configure(config)
        picam2.options["quality"] = max(1, min(100, int(self.config.jpeg_quality)))
        picam2.start()
        self._picam2 = picam2

    def _apply_mode(self, mode: CameraModeConfig) -> None:
        if self._picam2 is None:
            return
        controls: dict[str, object] = {"AwbEnable": True}
        if mode.auto_exposure:
            controls["AeEnable"] = True
            controls["ExposureValue"] = float(mode.exposure_value)
            controls["FrameDurationLimits"] = (1000, max(1000, int(mode.max_exposure_us)))
        else:
            controls["AeEnable"] = False
            if mode.exposure_us is not None:
                controls["ExposureTime"] = max(1, min(int(mode.exposure_us), int(mode.max_exposure_us)))
            if mode.analogue_gain is not None:
                controls["AnalogueGain"] = max(1.0, float(mode.analogue_gain))
        awb_enum = _awb_mode(mode.awb_mode)
        if awb_enum is not None:
            controls["AwbMode"] = awb_enum
        denoise_enum = _noise_reduction_mode(mode.denoise)
        if denoise_enum is not None:
            controls["NoiseReductionMode"] = denoise_enum
        self._picam2.set_controls(controls)

    def _capture_with_timeout(self, path: Path) -> None:
        assert self._picam2 is not None
        timeout = max(1.0, float(self.config.capture_timeout_seconds))
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jaguar-camera-capture")
        future = executor.submit(self._picam2.capture_file, str(path))
        try:
            future.result(timeout=timeout)
        except TimeoutError as exc:
            raise TimeoutError(f"camera capture timed out after {timeout:.1f}s") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def close(self) -> None:
        if self._picam2 is None:
            return
        try:
            self._picam2.stop()
        except Exception:
            pass
        try:
            self._picam2.close()
        except Exception:
            pass
        self._picam2 = None


def create_camera(config: CameraConfig, mock: bool = False) -> Camera:
    if mock or not config.enabled:
        return MockCamera()
    if config.backend == "picamera2":
        return PiCamera2Camera(config)
    raise ValueError(f"Unsupported camera backend: {config.backend}")


def _awb_mode(value: str):
    try:
        from libcamera import controls
    except Exception:
        return None
    key = str(value or "auto").strip().lower()
    mapping = {
        "auto": "Auto",
        "daylight": "Daylight",
        "cloudy": "Cloudy",
        "tungsten": "Tungsten",
        "fluorescent": "Fluorescent",
        "indoor": "Indoor",
    }
    name = mapping.get(key)
    return getattr(controls.AwbModeEnum, name, None) if name else None


def _noise_reduction_mode(value: str):
    try:
        from libcamera import controls
    except Exception:
        return None
    key = str(value or "").strip().lower()
    mapping = {
        "off": "Off",
        "fast": "Fast",
        "cdn_fast": "Fast",
        "high_quality": "HighQuality",
        "cdn_hq": "HighQuality",
    }
    name = mapping.get(key)
    return getattr(controls.draft.NoiseReductionModeEnum, name, None) if name else None
