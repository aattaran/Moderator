#!/bin/bash
# Launch Firefox with the persistent profile (cookies/sessions preserved)
PROFILE_DIR="/home/computeruse/.mozilla/firefox/moderator-profile"

# Create profile directory if it doesn't exist
mkdir -p "$PROFILE_DIR"

# Launch Firefox in the virtual display with sandbox disabled (Docker container)
export MOZ_DISABLE_CONTENT_SANDBOX=1
export MOZ_DISABLE_GMP_SANDBOX=1
export DISPLAY=:1

# Run Firefox in a restart loop so it recovers from crashes
while true; do
    firefox \
        --profile "$PROFILE_DIR" \
        --no-remote \
        --width ${WIDTH:-1024} \
        --height ${HEIGHT:-768} \
        "https://x.com" 2>/dev/null
    echo "[browser] Firefox exited, restarting in 3 seconds..."
    sleep 3
done
