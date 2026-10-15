FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# System deps for Playwright browsers
RUN apt-get update && apt-get install -y \
    fonts-liberation \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -s /bin/bash moderator && \
    echo "moderator ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Create data directory
RUN mkdir -p /app/data /app/data/media /app/browser-profile && \
    chown -R moderator:moderator /app

# Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Install Playwright Chromium browser (as moderator user so it's in their home)
USER moderator
RUN playwright install chromium
USER root
RUN playwright install-deps chromium

# Application code
COPY . /app
WORKDIR /app
RUN chown -R moderator:moderator /app

# Browser profile mount point
VOLUME /app/browser-profile

# Data mount point
VOLUME /app/data

USER moderator
ENTRYPOINT ["python", "/app/main.py"]
CMD ["run"]
