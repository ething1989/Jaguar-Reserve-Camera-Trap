from datetime import datetime, timedelta, timezone
from pathlib import Path
import csv

from juara_station.csv_exporter import CsvExportOptions, export_main_csv
from juara_station.storage import BirdCall, BirdCandidate, DataStore, SensorSample


def test_jaguar_csv_has_sensor_co2_photo_and_bird_calls(tmp_path: Path):
    store = DataStore(tmp_path / "station.sqlite3")
    start = datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=5)
    store.insert_sensor_sample(
        SensorSample(
            sampled_at=start,
            temperature_c=25.2,
            humidity_pct=71.0,
            pressure_mmhg=755.4,
            lux=1200.0,
            co2_ppm=612.0,
            cpu_temp_c=43.1,
        )
    )
    store.record_photo_event(
        start,
        "2026-07-03T08:00:00",
        start + timedelta(seconds=3),
        "/mnt/juara_usb/Photos/20260703_080000_pic1.jpg",
        "kept",
    )
    store.upsert_audio_event(start, "recorded", "/tmp/audio.wav", start, end, ai_status="done")
    store.save_bird_calls(
        start,
        [
            BirdCall(
                0.0,
                3.0,
                (
                    BirdCandidate("Hyacinth macaw", 0.82),
                    BirdCandidate("Blue-and-yellow macaw", 0.14),
                ),
            ),
            BirdCall(3.0, 6.0, (BirdCandidate("Hyacinth macaw", 0.64),)),
        ],
    )
    store.upsert_interval_summary(start, end, start, "rtc")

    csv_path = export_main_csv(
        store,
        tmp_path,
        timezone.utc,
        CsvExportOptions(
            filename="Jaguar Reserve Camera Trap.csv",
            profile="jaguar_reserve_camera_trap",
            latitude=-17.10211,
            longitude=-56.94487,
        ),
    )

    rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == 1
    assert rows[0]["Timestamp"] == "07/03/26 12:00.00"
    assert rows[0]["CO2"] == "612.000"
    assert rows[0]["mmHg"] == "755.400"
    assert rows[0]["Photos_Taken"] == "1"
    assert rows[0]["lat"] == "-17.102"
    assert rows[0]["lon"] == "-56.945"
    assert rows[0]["top_species"] == "Hyacinth macaw(Calls: 2, Conf: 73.0%)"
    assert rows[0]["Call 1"] == "Hyacinth macaw (82.0%)\nBlue-and-yellow macaw (14.0%)"
    assert rows[0]["Call 90"] == ""


def test_event_rows_coalesce_into_interval_without_sensor_data(tmp_path: Path):
    store = DataStore(tmp_path / "station.sqlite3")
    first = datetime(2026, 7, 3, 12, 1, tzinfo=timezone.utc)
    second = datetime(2026, 7, 3, 12, 2, tzinfo=timezone.utc)
    store.insert_system_event(first, "PI_RESTARTED")
    store.insert_system_event(second, "POSSIBLE_POWER_LOSS_RECOVERY")

    csv_path = export_main_csv(
        store,
        tmp_path,
        timezone.utc,
        CsvExportOptions(filename="Jaguar Reserve Camera Trap.csv", profile="jaguar_reserve_camera_trap"),
    )

    rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == 1
    assert rows[0]["Pi_Event"] == "Pi Restarted\nPower Loss"
