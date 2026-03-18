#!/bin/bash
# Start Xvfb virtual framebuffer at 1024x768 (matches API display dimensions)
exec Xvfb :1 -ac -screen 0 ${WIDTH:-1024}x${HEIGHT:-768}x24 -retro -dpi 96 -nolisten tcp
