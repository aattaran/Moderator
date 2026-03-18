FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# System packages: display server, window manager, browser, input tools
RUN apt-get update && apt-get install -y \
    xvfb \
    x11-utils \
    mutter \
    scrot \
    xdotool \
    firefox-esr \
    x11vnc \
    python3.11 \
    python3-pip \
    dbus-x11 \
    fonts-liberation \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Display config — matches what we report to the Computer Use API
ENV DISPLAY_NUM=1
ENV DISPLAY=:1
ENV WIDTH=1024
ENV HEIGHT=768

# Create non-root user
RUN useradd -m -s /bin/bash computeruse && \
    echo "computeruse ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Create data directory
RUN mkdir -p /app/data && chown computeruse:computeruse /app/data

# Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt

# Application code
COPY . /app
WORKDIR /app

# Make docker scripts executable
RUN chmod +x /app/docker/*.sh

# Browser profile mount point
VOLUME /home/computeruse/.mozilla/firefox/moderator-profile

# Data mount point (SQLite DB persists here)
VOLUME /app/data

USER computeruse
ENTRYPOINT ["/app/docker/entrypoint.sh"]
