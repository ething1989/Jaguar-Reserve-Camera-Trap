from datetime import datetime, timedelta, timezone
from pathlib import Path
import csv

from juara_station.csv_exporter import CsvExportOptions, export_main_csv
from juara_station.storage import BirdCall, BirdCandidate, DataStore, SensorSample, SoundDetection


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
    photo_id = store.create_photo_event(
        start,
        start,
        start + timedelta(seconds=3),
    )
    store.update_photo_event(
        photo_id,
        captured_at_utc=start + timedelta(seconds=3),
        path="/mnt/juara_usb/Photos/20260703_080000_pic1.jpg",
        status="kept",
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
    store.save_sound_detections(
        start,
        "yamnet",
        [
            SoundDetection("Bird vocalization, bird call, bird song", 0.88, category="bird"),
            SoundDetection("Frog", 0.41, category="frog"),
        ],
    )
    store.save_sound_detections(
        start,
        "perch",
        [
            SoundDetection("Hyacinth macaw", 0.74, source="perch", category="bird"),
            SoundDetection("Blue-and-yellow macaw", 0.22, source="perch", category="bird"),
        ],
    )
    store.upsert_interval_summary(start, end, start, "rtc")
    species_list = tmp_path / "species.txt"
    species_list.write_text(
        "\n".join(
            [
                "Anodorhynchus hyacinthinus_Hyacinth macaw",
                "Ara ararauna_Blue-and-yellow macaw",
            ]
        )
        + "\n"
    )

    csv_path = export_main_csv(
        store,
        tmp_path,
        timezone.utc,
        CsvExportOptions(
            filename="Jaguar Reserve Camera Trap.csv",
            latitude=-17.10211,
            longitude=-56.94487,
            birdnet_species_list_path=str(species_list),
        ),
    )

    rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == 1
    assert rows[0]["timestamp"] == "2026-07-03T12:00:00"
    assert rows[0]["co2_ppm_avg"] == "612.000"
    assert rows[0]["pressure_inhg_avg"] == "29.740"
    assert rows[0]["photos_taken"] == "1"
    assert rows[0]["bird_top_species"] == "Hyacinth macaw(Calls: 2, Conf: 73.0%)"
    assert rows[0]["bird_top_genus"] == "Anodorhynchus(Calls: 2, Support: 73.0%)"
    assert rows[0]["bird_top_family"] == "Psittacidae(Calls: 2, Support: 80.0%)"
    assert rows[0]["bird_top_group"] == "macaw(Calls: 2, Support: 80.0%)"
    assert rows[0]["yamnet_top_label"] == "Bird vocalization, bird call, bird song"
    assert rows[0]["yamnet_bird_score"] == "0.880"
    assert rows[0]["yamnet_frog_score"] == "0.410"
    assert rows[0]["perch_top_label"] == "Hyacinth macaw"
    assert rows[0]["perch_bird_score"] == "0.740"
    assert rows[0]["perch_top_family"] == "Psittacidae(Calls: 2, Support: 74.0%)"
    assert rows[0]["perch_top_group"] == "macaw(Calls: 2, Support: 74.0%)"
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
    assert rows[0]["system_event"] == "PI_RESTARTED;POSSIBLE_POWER_LOSS_RECOVERY"
