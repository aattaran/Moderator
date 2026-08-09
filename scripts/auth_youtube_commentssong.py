"""One-time YouTube OAuth2 setup — comments-song Shorts pipeline channel.

Sibling of scripts/youtube_auth.py. Same OAuth client (moderator-491715 GCP
project), DIFFERENT YouTube channel — a dedicated brand-account-backed
channel for the comments-song -> Shorts pipeline.

Writes credentials to data/youtube_credentials_commentssong.json so they
NEVER overlap with data/youtube_credentials.json (which authorizes the
moderator's tiktokshopnature@gmail.com health-supplements channel).

Run once on the local machine. The browser will open Google's consent flow
twice:
  1. Pick the Google account (e.g. aliyar.attaran@gmail.com) that owns the
     comments-song brand channel.
  2. Pick the channel (e.g. "Comments Song Shorts" — the new brand-account
     channel, NOT the moderator's tiktokshopnature channel).

Usage:
    python scripts/auth_youtube_commentssong.py
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRETS = "data/youtube_client_secrets.json"
CREDENTIALS_FILE = "data/youtube_credentials_commentssong.json"


def main():
    if not os.path.exists(CLIENT_SECRETS):
        print(f"ERROR: {CLIENT_SECRETS} not found.")
        print("Download it from Google Cloud Console -> Credentials -> OAuth 2.0 Client ID")
        return

    print("Opening browser for YouTube authorization (comments-song channel)...")
    print("CRITICAL: pick the comments-song channel, NOT the moderator's tiktokshopnature one.\n")

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
    credentials = flow.run_local_server(port=8080, prompt="consent")

    with open(CREDENTIALS_FILE, "w") as f:
        f.write(credentials.to_json())

    print(f"\nCredentials saved to {CREDENTIALS_FILE}")
    print(f"Refresh token: {credentials.refresh_token[:20]}...")
    print("\nNext: run the pipeline. The channel-identity probe in")
    print("upload_existing_mp4.py / run_shorts_pipeline.py will print the channel")
    print("title before any upload, so you can confirm the right channel was authorized.")


if __name__ == "__main__":
    main()
