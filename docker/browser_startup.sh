#!/bin/bash
# Launch Firefox with the persistent profile (cookies/sessions preserved)
PROFILE_DIR="/home/computeruse/.mozilla/firefox/moderator-profile"

# Create profile directory if it doesn't exist
mkdir -p "$PROFILE_DIR"

# Launch Firefox in the virtual display
exec firefox-esr \
    --display=:1 \
    --profile "$PROFILE_DIR" \
    --no-remote \
    --width ${WIDTH:-1024} \
    --height ${HEIGHT:-768} \
    "https://x.com" &
