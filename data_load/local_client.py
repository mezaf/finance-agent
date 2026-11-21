"""
local_client.py — drop-in replacement for drive_client for local folder testing.

Mirrors drive_client's function signatures (list_input_files, download_file,
move_to_processed).
"""

import os
import shutil

LOCAL_INPUT_DIR = "local_input"
LOCAL_PROCESSED_DIR = "local_processed"


def get_drive_service():
    """No-op for local mode."""
    os.makedirs(LOCAL_INPUT_DIR, exist_ok=True)
    os.makedirs(LOCAL_PROCESSED_DIR, exist_ok=True)
    return None


def list_input_files(service=None) -> list[dict]:
    """Mimics Drive file metadata shape: {"id": ..., "name": ...}."""
    files = []
    if not os.path.exists(LOCAL_INPUT_DIR):
        return files
    for name in os.listdir(LOCAL_INPUT_DIR):
        if name.lower().endswith(".pdf"):
            files.append({"id": name, "name": name})
    return files


def download_file(service, file_id: str, dest_path: str) -> None:
    src_path = os.path.join(LOCAL_INPUT_DIR, file_id)
    shutil.copy(src_path, dest_path)


def move_to_processed(service, file_id: str) -> None:
    src_path = os.path.join(LOCAL_INPUT_DIR, file_id)
    dest_path = os.path.join(LOCAL_PROCESSED_DIR, file_id)
    shutil.move(src_path, dest_path)