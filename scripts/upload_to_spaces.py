"""Upload new videos/images to DigitalOcean Spaces.
Run from your laptop after video-ad pipeline generates new content.

Usage:
  python scripts/upload_to_spaces.py                    # upload all from default dir
  python scripts/upload_to_spaces.py /path/to/videos    # upload from custom dir
"""

import glob
import os
import sys

import boto3

SPACES_REGION = "nyc3"
SPACES_BUCKET = "moderator-media"
SPACES_ENDPOINT = f"https://{SPACES_REGION}.digitaloceanspaces.com"
ACCESS_KEY = os.environ.get("DO_SPACES_KEY", "")
SECRET_KEY = os.environ.get("DO_SPACES_SECRET", "")
if not ACCESS_KEY or not SECRET_KEY:
    raise ValueError("DO_SPACES_KEY and DO_SPACES_SECRET must be set in environment")

DEFAULT_VIDEO_DIR = r"C:\Users\User\.cursor\workspaces\video-ad\video-ad\output\to_post"


def upload_all(source_dir: str):
    session = boto3.session.Session()
    client = session.client(
        "s3",
        region_name=SPACES_REGION,
        endpoint_url=SPACES_ENDPOINT,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
    )

    # List existing files in Spaces
    existing = set()
    try:
        response = client.list_objects_v2(Bucket=SPACES_BUCKET, Prefix="videos/")
        for obj in response.get("Contents", []):
            existing.add(os.path.basename(obj["Key"]))
    except Exception:
        pass

    # Find local videos
    videos = glob.glob(os.path.join(source_dir, "*.mp4"))
    new_count = 0

    for v in videos:
        name = os.path.basename(v)
        if name in existing:
            continue

        size_mb = os.path.getsize(v) / 1024 / 1024
        print(f"Uploading {name} ({size_mb:.1f} MB)...")
        client.upload_file(v, SPACES_BUCKET, f"videos/{name}")
        new_count += 1

    print(f"\nDone — {new_count} new videos uploaded ({len(videos) - new_count} already existed)")


if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VIDEO_DIR
    upload_all(source)
