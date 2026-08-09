"""Sync media assets from DigitalOcean Spaces to local data folders.
Run periodically to pull new videos/images uploaded by video-ad pipeline."""

import logging
import os

import boto3

logger = logging.getLogger(__name__)

SPACES_REGION = "nyc3"
SPACES_BUCKET = "moderator-media"
SPACES_ENDPOINT = f"https://{SPACES_REGION}.digitaloceanspaces.com"

LOCAL_VIDEOS_DIR = "data/product_videos"
LOCAL_IMAGES_DIR = "data/product_images"


def sync_media():
    """Download new media from Spaces that doesn't exist locally."""
    access_key = os.environ.get("DO_SPACES_KEY", "")
    secret_key = os.environ.get("DO_SPACES_SECRET", "")

    if not access_key or not secret_key:
        logger.warning("DO_SPACES_KEY/DO_SPACES_SECRET not set — skipping media sync")
        return 0

    session = boto3.session.Session()
    client = session.client(
        "s3",
        region_name=SPACES_REGION,
        endpoint_url=SPACES_ENDPOINT,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )

    os.makedirs(LOCAL_VIDEOS_DIR, exist_ok=True)
    os.makedirs(LOCAL_IMAGES_DIR, exist_ok=True)

    downloaded = 0

    # Sync videos
    try:
        response = client.list_objects_v2(Bucket=SPACES_BUCKET, Prefix="videos/")
        for obj in response.get("Contents", []):
            key = obj["Key"]
            filename = os.path.basename(key)
            if not filename:
                continue
            local_path = os.path.join(LOCAL_VIDEOS_DIR, filename)
            if not os.path.exists(local_path):
                logger.info("Downloading video: %s", filename)
                client.download_file(SPACES_BUCKET, key, local_path)
                downloaded += 1
    except Exception as e:
        logger.error("Failed to sync videos: %s", e)

    # Sync images
    try:
        response = client.list_objects_v2(Bucket=SPACES_BUCKET, Prefix="images/")
        for obj in response.get("Contents", []):
            key = obj["Key"]
            filename = os.path.basename(key)
            if not filename:
                continue
            local_path = os.path.join(LOCAL_IMAGES_DIR, filename)
            if not os.path.exists(local_path):
                logger.info("Downloading image: %s", filename)
                client.download_file(SPACES_BUCKET, key, local_path)
                downloaded += 1
    except Exception as e:
        logger.error("Failed to sync images: %s", e)

    logger.info("Media sync complete — %d new files downloaded", downloaded)
    return downloaded


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sync_media()
