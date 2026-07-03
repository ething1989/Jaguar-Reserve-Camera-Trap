# Field Checklist

1. Confirm the Pi boots and joins `JAGUAR LODGE`.
2. Confirm `/mnt/juara_usb` is mounted and writable.
3. Run `sudo scripts/pi_preflight.sh`.
4. Confirm I2C shows RTC plus BME280/lux addresses.
5. Confirm `/dev/serial0` exists for the MH-Z19C.
6. Confirm `arecord -l` sees the USB microphone.
7. Confirm `rpicam-hello --list-cameras` sees the OV5647 camera.
8. Confirm Google Drive login with `sudo -u "$USER" rclone about juara-gdrive:`.
9. Start services:

```bash
sudo systemctl restart juara-station juara-ai-worker
```

10. Watch logs for a few minutes:

```bash
sudo journalctl -u juara-station -f
```

11. Check the USB root. It should contain the CSV, a `Photos` folder, and no WAV files.
