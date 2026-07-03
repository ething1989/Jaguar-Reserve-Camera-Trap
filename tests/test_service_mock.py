from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import csv

from juara_station.config import (
    AudioConfig,
    BirdNetConfig,
    CameraConfig,
    DriveSyncConfig,
    ScheduleConfig,
    StationConfig,
    StorageConfig,
    TimeConfig,
)
from juara_station.paths import resolve_paths
from juara_station.service import StationService


def _mock_config(tmp_path: Path, **overrides) -> StationConfig:
    config = StationConfig(
        storage=StorageConfig(
            root=tmp_path / "usb",
            fallback_root=tmp_path / "fallback",
            state_root=tmp_path / "state",
            work_root=tmp_path / "work",
            recording_root=tmp_path / "recordings",
            logs_subdir=".",
            photos_subdir="Photos",
            csv_filename="Jaguar Reserve Camera Trap.csv",
            csv_profile="jaguar_reserve_camera_trap",
        ),
        schedule=ScheduleConfig(interval_seconds=1, sensor_sample_seconds=1, startup_delay_seconds=0),
        time=TimeConfig(gps_enabled=False, rtc_read_command="/bin/false", rtc_write_enabled=False, coordinate_enabled=False),
        audio=AudioConfig(delete_recordings_after_ai=True),
        birdnet=BirdNetConfig(enabled=True, process_inline=False, batch_max_files=1),
        camera=CameraConfig(enabled=True, scheduled_capture_times=["09:00", "16:00"]),
        drive_sync=DriveSyncConfig(enabled=False),
    )
    return replace(config, **overrides) if overrides else config


def test_mock_interval_creates_csv_and_deletes_audio_without_usb_wavs(tmp_path: Path):
    config = _mock_config(tmp_path)
    paths = resolve_paths(config.storage)
    service = StationService(config, paths, mock=True)

    csv_path = service.run_interval(duration_seconds=1)

    assert csv_path == tmp_path / "usb" / "Jaguar Reserve Camera Trap.csv"
    rows = list(csv.DictReader(csv_path.open()))
    assert rows
    assert "Call 1" in rows[0]
    assert "Photos_Taken" in rows[0]
    assert not list((tmp_path / "recordings").glob("**/*.wav"))
    assert not (tmp_path / "usb" / "media" / "audio").exists()
    assert (tmp_path / "usb" / "Photos").is_dir()


def test_scheduled_photo_is_saved_once_per_slot(tmp_path: Path):
    config = _mock_config(tmp_path, schedule=ScheduleConfig(interval_seconds=300, sensor_sample_seconds=1))
    service = StationService(config, resolve_paths(config.storage), mock=True)
    local_start = datetime(2026, 7, 3, 9, 0, tzinfo=config.zoneinfo)
    period_start = local_start.astimezone(timezone.utc)
    period_end = period_start + timedelta(minutes=5)

    changed = service._capture_due_scheduled_photos(period_start, period_end)
    changed_again = service._capture_due_scheduled_photos(period_start, period_end)

    assert changed
    assert not changed_again
    photos = list((tmp_path / "usb" / "Photos").glob("*.jpg"))
    assert len(photos) == 1
    rows = service.store.list_photo_events()
    assert len(rows) == 1
    assert rows[0]["scheduled_for_local"] == "2026-07-03T09:00:00"


def test_drive_sync_trigger_is_nonblocking_and_uses_configured_command(tmp_path: Path, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))

    monkeypatch.setattr("juara_station.service.subprocess.run", fake_run)
    config = _mock_config(
        tmp_path,
        drive_sync=DriveSyncConfig(
            enabled=True,
            trigger_on_csv_export=True,
            trigger_command="/usr/bin/systemctl start --no-block juara-gdrive-sync.service",
        ),
    )
    service = StationService(config, resolve_paths(config.storage), mock=False, ai_only=True)

    service._trigger_drive_sync("test export")

    assert calls[0][0] == ["/usr/bin/systemctl", "start", "--no-block", "juara-gdrive-sync.service"]
    assert calls[0][1]["timeout"] == 10
