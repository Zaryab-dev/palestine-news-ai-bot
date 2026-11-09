#!/usr/bin/env python3
"""
Interactive Google Drive OAuth 2.0 Setup Script.

This script helps you authenticate your personal Google account with Google Drive API,
obtains a persistent refresh token, sets up the target folder, and writes the credentials
to your .env file and outputs them for GitHub Secrets.
"""

import os
from pathlib import Path
import sys

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive"]


def main():
    print("=" * 70)
    print("  GOOGLE DRIVE OAUTH 2.0 SETUP HELPER")
    print("=" * 70)
    print("\nBefore starting, make sure you have created an OAuth 2.0 Client ID in:")
    print("https://console.cloud.google.com/apis/credentials")
    print("(Application type: 'Desktop app')\n")

    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()

    if not client_id:
        client_id = input("Enter your GOOGLE_CLIENT_ID: ").strip()
    else:
        print(f"Found GOOGLE_CLIENT_ID in environment: {client_id[:12]}...")

    if not client_secret:
        client_secret = input("Enter your GOOGLE_CLIENT_SECRET: ").strip()
    else:
        print("Found GOOGLE_CLIENT_SECRET in environment.")

    if not client_id or not client_secret:
        print("Error: Both Client ID and Client Secret are required. Aborting.")
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost", "http://localhost:8080/"],
        }
    }

    print("\n[+] Launching browser for Google authentication...")
    print("If your browser doesn't open automatically, copy the link shown below.\n")

    try:
        flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
        # Try local server first, fallback to console if in headless/remote VM
        try:
            creds = flow.run_local_server(port=8080, open_browser=True)
        except Exception:
            print("\nCould not start local web server. Switching to manual authorization code flow:\n")
            auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
            print(f"1. Open this URL in your browser:\n\n{auth_url}\n")
            auth_code = input("2. Enter the authorization code from the browser: ").strip()
            flow.fetch_token(code=auth_code)
            creds = flow.credentials

        refresh_token = creds.refresh_token
        if not refresh_token:
            print("\n[!] Warning: No refresh token returned.")
            print("Make sure you revoked prior access or configured 'access_type=offline' & 'prompt=consent'.")

        print("\n[✓] Successfully authenticated with Google Drive!")

        # Initialize Drive service and create root folder
        service = build("drive", "v3", credentials=creds)
        folder_name = "Gaza-Palestine-News-AI-Bot"

        # Search existing
        res = service.files().list(
            q=f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
            spaces="drive",
            fields="files(id, name)",
        ).execute()
        files = res.get("files", [])

        if files:
            folder_id = files[0]["id"]
            print(f"[✓] Found existing Drive folder '{folder_name}' (ID: {folder_id})")
        else:
            folder = service.files().create(
                body={"name": folder_name, "mimeType": "application/vnd.google-apps.folder"},
                fields="id",
            ).execute()
            folder_id = folder["id"]
            print(f"[✓] Created new Drive folder '{folder_name}' (ID: {folder_id})")

        # Update or append to .env
        env_path = Path(".env")
        env_lines = []
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                env_lines = f.readlines()

        keys_to_update = {
            "GOOGLE_CLIENT_ID": client_id,
            "GOOGLE_CLIENT_SECRET": client_secret,
            "GOOGLE_REFRESH_TOKEN": refresh_token or "",
            "GOOGLE_DRIVE_FOLDER_ID": folder_id,
        }

        updated_keys = set()
        new_lines = []
        for line in env_lines:
            matched = False
            for k, v in keys_to_update.items():
                if line.startswith(f"{k}="):
                    new_lines.append(f"{k}={v}\n")
                    updated_keys.add(k)
                    matched = True
                    break
            if not matched:
                new_lines.append(line)

        for k, v in keys_to_update.items():
            if k not in updated_keys:
                new_lines.append(f"{k}={v}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        print(f"\n[✓] Updated credentials in {env_path.resolve()}")
        print("\n" + "=" * 70)
        print("  SAVE THESE CREDENTIALS FOR GITHUB SECRETS")
        print("=" * 70)
        print(f"GOOGLE_CLIENT_ID:      {client_id}")
        print(f"GOOGLE_CLIENT_SECRET:  {client_secret}")
        print(f"GOOGLE_REFRESH_TOKEN:  {refresh_token}")
        print(f"GOOGLE_DRIVE_FOLDER_ID:{folder_id}")
        print("=" * 70 + "\n")

    except Exception as e:
        print(f"\n[!] Setup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
