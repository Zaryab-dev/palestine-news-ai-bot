"""Google Drive Uploader for archiving news batches, CSV drafts, and generated images."""

import csv
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class DriveUploader:
    def __init__(self, root_folder_name: str = "Gaza-Palestine-News-AI-Bot"):
        self.root_folder_name = root_folder_name
        self.client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
        self.client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
        self.refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN", "").strip()
        self.target_folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()

        self.service = None
        if self.is_configured():
            try:
                self.service = self._init_service()
                logger.info("Google Drive service successfully initialized via OAuth 2.0.")
            except Exception as e:
                logger.warning(f"Could not initialize Google Drive service: {e}")

    def is_configured(self) -> bool:
        """Check if required OAuth environment variables are present."""
        return bool(self.client_id and self.client_secret and self.refresh_token)

    def _init_service(self):
        """Build Google Drive API v3 client using OAuth refresh token."""
        import httplib2
        import google_auth_httplib2
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            None,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        http = httplib2.Http(disable_ssl_certificate_validation=True)
        authorized_http = google_auth_httplib2.AuthorizedHttp(creds, http=http)
        return build("drive", "v3", http=authorized_http)

    def _find_or_create_folder(self, folder_name: str, parent_id: Optional[str] = None) -> str:
        """Find folder by name under parent or create it."""
        from googleapiclient.http import MediaFileUpload

        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if parent_id:
            query += f" and '{parent_id}' in parents"

        results = self.service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
        files = results.get("files", [])

        if files:
            return files[0]["id"]

        metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            metadata["parents"] = [parent_id]

        folder = self.service.files().create(body=metadata, fields="id").execute()
        return folder["id"]

    def upload_file(self, local_path: Path, parent_id: str, mime_type: str) -> Optional[str]:
        """Upload a single file to Google Drive."""
        from googleapiclient.http import MediaFileUpload

        if not self.service or not local_path.exists():
            return None

        file_metadata = {
            "name": local_path.name,
            "parents": [parent_id],
        }
        media = MediaFileUpload(str(local_path), mimetype=mime_type, resumable=True)
        uploaded = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, webViewLink",
        ).execute()

        logger.info(f"Uploaded to Drive: {local_path.name} (ID: {uploaded.get('id')})")
        return uploaded.get("webViewLink")

    def archive_batch(
        self,
        batch_id: str,
        posts: List[Dict[str, Any]],
        batch_dir: Path,
    ) -> Dict[str, Any]:
        """
        Archive a batch to local storage and sync to Google Drive if configured.
        """
        batch_dir.mkdir(parents=True, exist_ok=True)
        images_dir = batch_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        # 1. Write posts.jsonl
        jsonl_path = batch_dir / "posts.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for p in posts:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")

        # 2. Write posts.csv (spreadsheet for easy copy-pasting to X)
        csv_path = batch_dir / "posts.csv"
        csv_columns = [
            "batch_id",
            "story_id",
            "topic",
            "headline",
            "source_name",
            "published_at_utc",
            "x_post",
            "source_urls",
            "image_filename",
            "image_status",
            "verification_status",
            "priority",
            "review_status",
        ]
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=csv_columns, extrasaction="ignore")
            writer.writeheader()
            for p in posts:
                row = dict(p)
                row["source_urls"] = " | ".join(p.get("source_urls", []))
                writer.writerow(row)

        # 3. Write batch_summary.md
        summary_path = batch_dir / "batch_summary.md"
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(f"# Batch Summary — {batch_id}\n\n")
            f.write(f"- **Total Posts:** {len(posts)}\n")
            f.write(f"- **Generated Images:** {sum(1 for p in posts if p.get('image_status') == 'GENERATED')}\n")
            f.write(f"- **Review Status:** READY_FOR_REVIEW\n\n")
            f.write("## Drafted Posts for Manual Publishing\n\n")
            for idx, p in enumerate(posts, 1):
                f.write(f"### {idx}. {p.get('headline')}\n")
                f.write(f"- **Topic:** `{p.get('topic')}` | **Source:** {p.get('source_name')}\n")
                f.write(f"- **Status:** `{p.get('verification_status')}`\n")
                f.write(f"- **Draft:**\n> {p.get('x_post')}\n\n")
                f.write(f"- **Source Links:** {', '.join(p.get('source_urls', []))}\n")
                f.write(f"- **Image:** `{p.get('image_filename')}` ({p.get('image_status')})\n\n")

        # If Drive not configured, return local result
        if not self.service:
            logger.info(f"Drive OAuth not configured. Batch archived locally at: {batch_dir}")
            return {
                "synced_to_drive": False,
                "local_dir": str(batch_dir),
                "drive_link": None,
                "message": "Saved to local output directory. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN to sync with Google Drive.",
            }

        # Sync to Google Drive
        try:
            root_id = self.target_folder_id or self._find_or_create_folder(self.root_folder_name)
            date_str = batch_id.split("_")[0]  # e.g., 20261109
            formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            date_folder_id = self._find_or_create_folder(formatted_date, root_id)
            batch_folder_id = self._find_or_create_folder(f"batch_{batch_id}", date_folder_id)

            # Upload files
            self.upload_file(jsonl_path, batch_folder_id, "application/json")
            self.upload_file(csv_path, batch_folder_id, "text/csv")
            summary_link = self.upload_file(summary_path, batch_folder_id, "text/markdown")

            # Upload images
            images_folder_id = self._find_or_create_folder("images", batch_folder_id)
            for img_file in images_dir.glob("*.png"):
                self.upload_file(img_file, images_folder_id, "image/png")

            logger.info(f"Batch {batch_id} fully synced to Google Drive folder ID: {batch_folder_id}")
            return {
                "synced_to_drive": True,
                "local_dir": str(batch_dir),
                "drive_folder_id": batch_folder_id,
                "summary_link": summary_link,
            }

        except Exception as e:
            logger.error(f"Error syncing batch to Google Drive: {e}")
            return {
                "synced_to_drive": False,
                "local_dir": str(batch_dir),
                "drive_link": None,
                "error": str(e),
            }
