# Jaguar Reserve Software Manual

## Services

- `juara-station.service`: records audio, samples sensors, checks scheduled photo times, writes SQLite, exports CSV.
- `juara-ai-worker.service`: processes pending audio with BirdNET and refreshes affected CSV rows.
- `juara-gdrive-sync.timer`: starts Drive sync every five minutes.
- `juara-gdrive-sync.service`: uploads CSV files to Google Drive and exits cleanly if offline.
- `juara-daily-reboot.timer`: planned reboot schedule.

## Time And Coordinates

No GPS is used. Time comes from the DS3231 RTC first, then estimated time if the RTC fails.

BirdNET coordinates are fixed:

```text
-17.10211, -56.94487
```

At startup the station builds the active BirdNET species list from those coordinates and the 100-mile species pack.

## Storage

SQLite:

```text
/var/lib/juara-station/state/station.sqlite3
```

CSV:

```text
/mnt/juara_usb/Jaguar Reserve Camera Trap.csv
```

Photos:

```text
/mnt/juara_usb/Photos
```

Temporary WAV files:

```text
/var/lib/juara-station/audio_recordings
```

WAV files are deleted after BirdNET finishes or when interrupted recordings are recovered after reboot.

## CSV

The Jaguar CSV profile includes:

- Timestamp, time source, Pi event.
- Temperature, humidity, lux, CO2, pressure in mmHg, CPU temperature.
- Photos taken in that interval.
- Fixed latitude and longitude.
- Bird diversity metrics.
- Top bird formatted as `Species(Calls: #, Conf: #%)`.
- Audio status.
- `Call 1` through `Call 90`.
- Errors.

## Camera

The camera is scheduled only. There is no motion loop and no flash logic.

If the Pi is on during a scheduled interval and that day/time has not already been captured, the service saves a JPEG and records the event in SQLite. If capture fails, the station logs `Camera Capture Failed` in the CSV error column and keeps running.

## CO2

The MH-Z19C is read on `/dev/serial0` at 9600 baud. The station averages readings across the same five-minute interval as BME280, lux, and CPU temperature.

## Google Drive

Drive sync uses `rclone` remote `juara-gdrive` and folder:

```text
Jaguar Reserve Camera Trap
```

Only CSV files are uploaded. Photos stay on the USB unless copied manually.
