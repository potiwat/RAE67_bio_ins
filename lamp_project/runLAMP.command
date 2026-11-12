#!/bin/zsh
# Run the lamp: ESP32 + camera + GUI (+ iPad page). Double-click this file.
# Close the GUI window (this frees the USB port) before uploading new code to the ESP32.
setopt null_glob
cd "$(dirname "$0")/camera"
PORT=$(ls /dev/cu.usbserial-* /dev/cu.SLAB_USBtoUART /dev/cu.wchusbserial* 2>/dev/null | head -1)
if [ -z "$PORT" ]; then echo "ESP32 not found - plug in its USB cable"; read; exit; fi
echo "ESP32 on $PORT"
.venv/bin/python lamp_camera.py --cam -1 --port $PORT     # -1 = find the external USB camera
echo; echo "done - press Enter to close"; read
