#!/usr/bin/env python3
"""
Interactive Google Drive OAuth 2.0 Setup Script.

Supports:
- Local interactive browser popup
- Headless / remote VM 2-step flow (--generate-url and --exchange)
"""

import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive"]
STATE_FILE = Path("state/oauth_pending.json")


def extract_code(raw_input: str) -> str:
    """Extract code parameter if full redirected URL was provided."""
    raw_input = raw_input.strip()
    if raw_input.startswith("http://") or raw_input.startswith("https://"):
        parsed = urlparse(raw_input)
        params = parse_qs(parsed.query)
        if "code" in params:
            return params["code"][0]
    return raw_input


def generate_auth_url(client_id: str, client_secret: str, redirect_uri: str = "http://localhost:8080/"):
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
    auth_url, state = flow.authorization_url(prompt="consent", access_type="offline")

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "state": state,
                "code_verifier": flow.code_verifier,
            },
            f,
            indent=2,
        )

    print("\n" + "=" * 70)
    print("  STEP 1: OPEN THIS AUTHORIZATION LINK IN YOUR BROWSER")
    print("=" * 70)
    print(f"\n{auth_url}\n")
    print("=" * 70)
    print("Instructions:")
    print("1. Click the link above to log in and allow Drive access.")
    print("2. Google will redirect your browser to a 'localhost:8080' address.")
    print("3. Your browser will say 'Cannot connect' or 'Site can't be reached' — THAT IS EXPECTED!")
    print("4. Copy the FULL URL from your browser address bar (or just the code) and paste it back.")
    print("=" * 70 + "\n")
    return auth_url


def complete_exchange(auth_input: str):
    if not STATE_FILE.exists():
        print(f"Error: Pending state file not found at {STATE_FILE}. Run with --generate-url first.")
        sys.exit(1)

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        saved_state = json.load(f)

    code = extract_code(auth_input)
    if not code:
        print("Error: Could not extract authorization code.")
        sys.exit(1)

    client_id = saved_state["client_id"]
    client_secret = saved_state["client_secret"]
    redirect_uri = saved_state.get("redirect_uri", "http://localhost:8080/")
    verifier = saved_state.get("code_verifier")

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
    flow.code_verifier = verifier

    print("[+] Exchanging authorization code for persistent refresh token...")
    flow.fetch_token(code=code)
    creds = flow.credentials

    refresh_token = creds.refresh_token
    if not refresh_token:
        print("\n[!] Warning: No refresh token returned. Ensure you selected offline access.")

    print("[✓] OAuth exchange successful!")

    # Verify Drive access and find/create folder
    import httplib2
    import google_auth_httplib2
    http = httplib2.Http(disable_ssl_certificate_validation=True)
    authorized_http = google_auth_httplib2.AuthorizedHttp(creds, http=http)
    service = build("drive", "v3", http=authorized_http)
    folder_name = "Gaza-Palestine-News-AI-Bot"

    folder_id = ""
    try:
        res = service.files().list(
            q=f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
            spaces="drive",
            fields="files(id, name)",
        ).execute()
        files = res.get("files", [])

        if files:
            folder_id = files[0]["id"]
            print(f"[✓] Connected to existing Drive folder '{folder_name}' (ID: {folder_id})")
        else:
            folder = service.files().create(
                body={"name": folder_name, "mimeType": "application/vnd.google-apps.folder"},
                fields="id",
            ).execute()
            folder_id = folder["id"]
            print(f"[✓] Created new Drive folder '{folder_name}' (ID: {folder_id})")
    except Exception as e:
        print(f"[!] Warning: Could not create folder automatically ({e}). You can provide a folder ID manually.")

    # Update .env
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

    if STATE_FILE.exists():
        STATE_FILE.unlink()

    print(f"\n[✓] Successfully configured {env_path.resolve()}")
    print("\n" + "=" * 70)
    print("  SAVE THESE CREDENTIALS FOR GITHUB SECRETS")
    print("=" * 70)
    print(f"GOOGLE_CLIENT_ID:      {client_id}")
    print(f"GOOGLE_CLIENT_SECRET:  {client_secret}")
    print(f"GOOGLE_REFRESH_TOKEN:  {refresh_token}")
    print(f"GOOGLE_DRIVE_FOLDER_ID:{folder_id}")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Google Drive OAuth Setup")
    parser.add_argument("--generate-url", action="store_true", help="Generate authorization URL and save state")
    parser.add_argument("--exchange", type=str, help="Complete authorization exchange with code or redirect URL")
    parser.add_argument("--client-id", type=str, default="")
    parser.add_argument("--client-secret", type=str, default="")
    args = parser.parse_args()

    client_id = args.client_id or os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = args.client_secret or os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()

    if args.generate_url:
        if not client_id or not client_secret:
            client_id = input("Enter GOOGLE_CLIENT_ID: ").strip()
            client_secret = input("Enter GOOGLE_CLIENT_SECRET: ").strip()
        generate_auth_url(client_id, client_secret)
    elif args.exchange:
        complete_exchange(args.exchange)
    else:
        # Default interactive
        if not client_id or not client_secret:
            client_id = input("Enter GOOGLE_CLIENT_ID: ").strip()
            client_secret = input("Enter GOOGLE_CLIENT_SECRET: ").strip()
        generate_auth_url(client_id, client_secret)
        code_input = input("Paste the redirected URL or authorization code: ").strip()
        complete_exchange(code_input)


if __name__ == "__main__":
    main()
