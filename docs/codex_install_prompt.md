# Prompt For Another Codex

You are setting up the `Jaguar-Reserve-Camera-Trap` Raspberry Pi station. The target system has RTC, BME280, VEML7700, USB thumb drive, USB microphone, MH-Z19C CO2 sensor, and an Arducam OV5647 Day/Night IR-Cut camera. It has no GPS, no motion detector, no flash, and no image AI.

Use this repository:

```bash
git clone https://github.com/esmaby444/Jaguar-Reserve-Camera-Trap.git ~/Jaguar-Reserve-Camera-Trap
cd ~/Jaguar-Reserve-Camera-Trap
sudo scripts/install_jaguar_reserve_camera_trap.sh
```

The SD card should already connect to Wi-Fi:

```text
SSID: JAGUAR LODGE
Password: none; open network
```

The station uses fixed BirdNET coordinates:

```text
17.10211 S, 56.94487 W
```

The MH-Z19C default wiring is:

```text
Sensor TX -> Pi GPIO15/RXD0, physical pin 10
Sensor RX -> Pi GPIO14/TXD0, physical pin 8
Sensor GND -> Pi GND
Sensor power -> sensor-rated power input
```

Use level shifting if the sensor TX line outputs 5V.

After install, complete Google Drive login with the human present:

```bash
sudo -u "$USER" /usr/local/bin/juara_gdrive_auth_helper
sudo -u "$USER" rclone config reconnect juara-gdrive:
sudo -u "$USER" /usr/local/bin/juara_gdrive_sync
```

Expected Drive folder:

```text
Jaguar Reserve Camera Trap
```

Run checks:

```bash
sudo scripts/pi_preflight.sh
sudo systemctl restart juara-station juara-ai-worker
sleep 20
sudo journalctl -u juara-station -n 120 --no-pager
sudo journalctl -u juara-ai-worker -n 120 --no-pager
ls -lh /mnt/juara_usb
```

Confirm these before deployment:

- `/mnt/juara_usb/Jaguar Reserve Camera Trap.csv` exists after a field interval or manual export.
- `/mnt/juara_usb/Photos` exists and is writable.
- No audio folder exists on the USB.
- `/etc/juara-station.toml` has camera enabled with `scheduled_capture_times = ["09:00", "16:00"]`.
- `/etc/juara-station.toml` has `gps_enabled = false`.
- `/etc/juara-station.toml` has `uart_co2_enabled = true` and `uart_co2_device = "/dev/serial0"`.
- `systemctl is-enabled juara-station juara-ai-worker juara-gdrive-sync.timer juara-daily-reboot.timer` reports enabled.
- `rclone listremotes` includes `juara-gdrive:`.
- If internet is disconnected, station logging still continues and Drive sync exits without breaking the service.
