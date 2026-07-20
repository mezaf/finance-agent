"""
drive_client.py — Google Drive API auth (OAuth, local desktop flow),
file discovery in the Input folder, filename parsing, download, and
moving files to Processed once handled.

Setup (one-time):
    1. Google Cloud Console -> enable the Google Drive API
    2. Credentials -> OAuth client ID -> Desktop app -> download as credentials.json
       (place it in the project root)
    3. First run opens a browser for consent; a token.json is cached after that

Requires:
    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
"""

import os
import re

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

SCOPES = ["https://www.googleapis.com/auth/drive"]
CREDENTIALS_PATH = "credentials.json"
TOKEN_PATH = "token.json"

# Set these in .env once you know your actual Drive folder IDs
# (folder ID is the string after /folders/ in the Drive URL)
INPUT_FOLDER_ID = os.environ.get("DRIVE_INPUT_FOLDER_ID")
PROCESSED_FOLDER_ID = os.environ.get("DRIVE_PROCESSED_FOLDER_ID")

# bank_<account|tdc>_<visa|master>_statement.pdf, with santander_statement.pdf
# as the one exception (no account_type/card_network in the filename at all)
FILENAME_PATTERN = re.compile(
    r"^(?P<bank>bbva|galicia|bna|santander)"
    r"(?:_(?P<account_type>account|tdc))?"
    r"(?:_(?P<card_network>visa|master))?"
    r"_statement\.pdf$",
    re.IGNORECASE,
)


def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


def parse_filename(filename: str) -> dict | None:
    """
    Returns {"bank": ..., "account_type": ..., "card_network": ...} or None
    if the filename doesn't match the expected pattern.

    Note: for santander_statement.pdf, account_type/card_network will be None
    here — Santander's extractor determines those per-transaction instead,
    since one file holds multiple products.
    """
    match = FILENAME_PATTERN.match(filename.lower())
    if not match:
        return None
    return {
        "bank": match.group("bank"),
        "account_type": match.group("account_type"),
        "card_network": match.group("card_network"),
    }


def list_input_files(service) -> list[dict]:
    """Lists PDFs in the Input folder, returns Drive file metadata dicts."""
    if not INPUT_FOLDER_ID:
        raise ValueError("DRIVE_INPUT_FOLDER_ID not set in environment")

    results = service.files().list(
        q=f"'{INPUT_FOLDER_ID}' in parents and mimeType='application/pdf' and trashed=false",
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
    if not PROCESSED_FOLDER_ID:
        raise ValueError("DRIVE_PROCESSED_FOLDER_ID not set in environment")

    file = service.files().get(fileId=file_id, fields="parents").execute()
    previous_parents = ",".join(file.get("parents", []))

    service.files().update(
        fileId=file_id,
        addParents=PROCESSED_FOLDER_ID,
        removeParents=previous_parents,
        fields="id, parents",
    ).execute()