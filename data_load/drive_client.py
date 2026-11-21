"""
drive_client.py — Google Drive API auth, file discovery in Input folder,
downloading files, and moving files to Processed folder once processed.
"""

import os
import io
import re

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive"]
CREDENTIALS_PATH = "credentials.json"
TOKEN_PATH = "token.json"


def _clean_folder_id(raw_id: str | None) -> str | None:
    if not raw_id:
        return None
    match = re.search(r"folders/([a-zA-Z0-9_-]+)", raw_id)
    if match:
        return match.group(1)
    return raw_id.strip()


INPUT_FOLDER_ID = _clean_folder_id(os.environ.get("DRIVE_INPUT_FOLDER_ID"))
PROCESSED_FOLDER_ID = _clean_folder_id(os.environ.get("DRIVE_PROCESSED_FOLDER_ID"))


def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0, open_browser=False)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


def list_input_files(service) -> list[dict]:
    """Lists PDFs in the Input folder, returns Drive file metadata dicts."""
    folder_id = _clean_folder_id(os.environ.get("DRIVE_INPUT_FOLDER_ID")) or INPUT_FOLDER_ID
    if not folder_id:
        raise ValueError("DRIVE_INPUT_FOLDER_ID not set in environment")

    results = service.files().list(
        q=f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false",
        fields="files(id, name, modifiedTime)",
    ).execute()
    return results.get("files", [])


def download_file(service, file_id: str, dest_path: str) -> None:
    request = service.files().get_media(fileId=file_id)
    with io.FileIO(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def move_to_processed(service, file_id: str) -> None:
    processed_id = _clean_folder_id(os.environ.get("DRIVE_PROCESSED_FOLDER_ID")) or PROCESSED_FOLDER_ID
    if not processed_id:
        raise ValueError("DRIVE_PROCESSED_FOLDER_ID not set in environment")

    file = service.files().get(fileId=file_id, fields="parents").execute()
    previous_parents = ",".join(file.get("parents", []))

    service.files().update(
        fileId=file_id,
        addParents=processed_id,
        removeParents=previous_parents,
        fields="id, parents",
    ).execute()