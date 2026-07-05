from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import csv

from juara_station.config import (
    AudioConfig,
    BirdNetConfig,
    CameraConfig,
    ScheduleConfig,
    StationConfig,
    StorageConfig,
    TimeConfig,
)
from juara_station.paths import resolve_paths
from juara_station.paths import StationPaths
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
    assert "photos_taken" in rows[0]
    assert not list((tmp_path / "recordings").glob("**/*.wav"))
    assert not (tmp_path / "usb" / "media" / "audio").exists()
    assert (tmp_path / "usb" / "Photos").is_dir()


def test_scheduled_photo_is_saved(tmp_path: Path):
    config = _mock_config(tmp_path, schedule=ScheduleConfig(interval_seconds=300, sensor_sample_seconds=1))
    service = StationService(config, resolve_paths(config.storage), mock=True)
    local_start = datetime(2026, 7, 3, 9, 0, tzinfo=config.zoneinfo)
    period_start = local_start.astimezone(timezone.utc)

    service._capture_scheduled_photo(period_start)

    photos = list((tmp_path / "usb" / "Photos").glob("**/*.jpg"))
    assert len(photos) == 1
    rows = service.store.pending_photo_events()
    assert len(rows) == 1
    assert rows[0]["triggered_at_utc"] == "2026-07-03T13:00:00+00:00"


def test_fallback_sync_copies_logs_and_photos_to_usb(tmp_path: Path):
    config = _mock_config(tmp_path)
    service = StationService(config, resolve_paths(config.storage), mock=True)
    fallback_paths = StationPaths(
        root=tmp_path / "fallback",
        fallback_root=tmp_path / "fallback",
        state_root=tmp_path / "state",
        work_root=tmp_path / "work",
        recording_root=tmp_path / "recordings",
        logs_subdir=".",
        photos_subdir="Photos",
        fallback_active=True,
    )
    usb_paths = StationPaths(
        root=tmp_path / "usb",
        fallback_root=tmp_path / "fallback",
        state_root=tmp_path / "state",
        work_root=tmp_path / "work",
        recording_root=tmp_path / "recordings",
        logs_subdir=".",
        photos_subdir="Photos",
        fallback_active=False,
    )
    service.paths = fallback_paths
    fallback_paths.logs_dir.mkdir(parents=True)
    fallback_paths.photos_dir.mkdir(parents=True)
    (fallback_paths.logs_dir / "juara_environment_samples.csv").write_text("header\none\ntwo\n")
    (fallback_paths.photos_dir / "field.jpg").write_bytes(b"photo")
    usb_paths.logs_dir.mkdir(parents=True, exist_ok=True)
    (usb_paths.logs_dir / "juara_environment_samples.csv").write_text("header\n")

    service._copy_fallback_outputs_to_usb(usb_paths)

    assert (usb_paths.logs_dir / "juara_environment_samples.csv").read_text() == "header\none\ntwo\n"
    assert (usb_paths.photos_dir / "field.jpg").read_bytes() == b"photo"
