# Jaguar Reserve Camera Trap

Deployment source for the Jaguar Reserve Raspberry Pi Zero 2 W station.

This build has a scheduled camera, but no motion detector, no flash, and no image AI. It takes two photos per day, records BirdNET audio, logs BME280, VEML7700 lux, RTC time, MH-Z19C CO2, and uploads the CSV to Google Drive whenever internet is available.

## Hardware

- Raspberry Pi Zero 2 W.
- DS3231 RTC on I2C.
- BME280 on I2C.
- VEML7700 lux sensor on I2C.
- MH-Z19C CO2 sensor on hardware UART.
- Arducam OV5647 Day/Night IR-Cut camera.
- USB thumb drive.
- USB microphone.

There is intentionally no GPS, no PIR motion detector, no flash output, and no image AI.

## Field Behavior

- Writes one main CSV at `/mnt/juara_usb/Jaguar Reserve Camera Trap.csv`.
- Saves scheduled photos to `/mnt/juara_usb/Photos`.
- Captures photos at `09:00` and `16:00` local time.
- Uses fixed coordinates for BirdNET species filtering: `-17.10211, -56.94487`.
- Records five-minute audio intervals, processes them with BirdNET, then deletes the WAV files from the Pi.
- Never stores audio on the USB drive.
- Logs CO2 as a five-minute average like BME280 and lux values.
- Uploads CSV files only to Google Drive folder `Jaguar Reserve Camera Trap`.
- If internet is unavailable, Drive sync exits cleanly and retries later.

## Camera Settings

The camera uses Picamera2 at full OV5647 still resolution:

- `2592 x 1944`
- JPEG quality `92`
- auto exposure on
- exposure compensation `-0.3`
- auto white balance
- fast denoise
- exposure ceiling `50000 us`

That combination should give the highest chance of usable daylight scheduled photos without overexposing too aggressively.

## MH-Z19C Wiring

Default config uses `/dev/serial0`:

- Sensor TX -> Pi GPIO15/RXD0, physical pin 10.
- Sensor RX -> Pi GPIO14/TXD0, physical pin 8.
- Sensor GND -> Pi GND.
- Sensor power -> sensor-rated input.

Use a level shifter or voltage divider if the sensor TX line outputs 5V. Raspberry Pi GPIO is 3.3V only.

## Install On A Pi

The SD card should already be written by Raspberry Pi Imager to join:

- SSID: `JAGUAR LODGE`
- Password: none, open network

On the Pi:

```bash
git clone https://github.com/esmaby444/Jaguar-Reserve-Camera-Trap.git ~/Jaguar-Reserve-Camera-Trap
cd ~/Jaguar-Reserve-Camera-Trap
sudo scripts/install_jaguar_reserve_camera_trap.sh
```

Then do the one-time Google Drive login as the station user:

```bash
sudo -u "$USER" /usr/local/bin/juara_gdrive_auth_helper
sudo -u "$USER" rclone config reconnect juara-gdrive:
sudo -u "$USER" /usr/local/bin/juara_gdrive_sync
```

After setup:

```bash
sudo scripts/pi_preflight.sh
sudo systemctl start juara-station
sudo systemctl start juara-ai-worker
```

## Useful Commands

```bash
sudo journalctl -u juara-station -f
sudo journalctl -u juara-ai-worker -f
sudo journalctl -u juara-gdrive-sync.service -n 80 --no-pager
juara-station --config /etc/juara-station.toml doctor
juara-station --config /etc/juara-station.toml export-csv
```

## Local Smoke Test

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/juara-station --mock --config configs/local.mock.toml once --duration 1
.venv/bin/pytest
```
