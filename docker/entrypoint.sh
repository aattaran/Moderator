#!/bin/bash
set -e

echo "[moderator] Starting display environment..."

# Start Xvfb virtual display
/app/docker/xvfb_startup.sh &
sleep 2

# Wait for display to be ready
for i in $(seq 1 10); do
    if xdpyinfo -display :1 > /dev/null 2>&1; then
        echo "[moderator] Display :1 is ready"
        break
    fi
    echo "[moderator] Waiting for display... ($i/10)"
    sleep 1
done

# Start D-Bus (needed by Firefox)
eval $(dbus-launch --sh-syntax) 2>/dev/null || true

# Start window manager
mutter --display=:1 --replace &
sleep 1

# Start VNC server if enabled
if [ "${ENABLE_VNC}" = "true" ]; then
    echo "[moderator] Starting VNC server on port 5900..."
    x11vnc -display :1 -nopw -forever -shared -rfbport 5900 &
fi

# Start Firefox with persistent profile (auto-restarts on crash)
/app/docker/browser_startup.sh &
sleep 5

# Wait for Firefox to be ready
for i in $(seq 1 15); do
    if DISPLAY=:1 xdotool search --name "Mozilla Firefox" > /dev/null 2>&1 || \
       DISPLAY=:1 xdotool search --name "firefox" > /dev/null 2>&1; then
        echo "[moderator] Firefox is ready"
        break
    fi
    echo "[moderator] Waiting for Firefox... ($i/15)"
    sleep 2
done

echo "[moderator] Environment ready. Starting application..."

# Run the application as the main process
if [ $# -eq 0 ]; then
    exec python3 /app/main.py run
else
    exec python3 /app/main.py "$@"
fi
