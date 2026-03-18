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

# Start window manager
mutter --display=:1 --replace &
sleep 1

# Start VNC server if enabled
if [ "${ENABLE_VNC}" = "true" ]; then
    echo "[moderator] Starting VNC server on port 5900..."
    x11vnc -display :1 -nopw -forever -shared -rfbport 5900 &
fi

# Start Firefox with persistent profile
/app/docker/browser_startup.sh &
sleep 3

echo "[moderator] Environment ready. Starting application..."

# Run the application — pass all arguments through
exec python3 /app/main.py "$@"
