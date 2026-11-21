"""
main.py — monthly run entry point using IntakeOrchestrator.

Flow:
    Runs the 5-step Intake Orchestrator (Task 0 -> 1 -> 2 -> 3 -> 4) for all
    input statement PDFs.
"""

import argparse
import os
import shutil
import tempfile

from dotenv import load_dotenv

from data_load import drive_client, local_client, run_intake
from db import db

load_dotenv()

DATA_SOURCE = os.environ.get("DATA_SOURCE", "drive").lower()
source = local_client if DATA_SOURCE == "local" else drive_client

LOCAL_INPUT_DIR = "local_input"
LOCAL_PROCESSED_DIR = "local_processed"


def ensure_local_dirs() -> None:
    os.makedirs(LOCAL_INPUT_DIR, exist_ok=True)
    os.makedirs(LOCAL_PROCESSED_DIR, exist_ok=True)


def process_single_file(service, file_meta: dict) -> None:
    file_id = file_meta["id"]
    file_name = file_meta["name"]

    with db.fresh_connection() as conn:
        db.init_db(conn)
        if db.is_file_processed(conn, file_id):
            print(f"[SKIP] Already loaded: {file_name}")
            return

    if DATA_SOURCE == "drive":
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = os.path.join(tmp_dir, file_name)
            try:
                source.download_file(service, file_id, pdf_path)
            except Exception as e:
                with db.fresh_connection() as conn:
                    db.log_error(conn, file_name, "download", str(e))
                print(f"[ERROR] Download failed for {file_name}: {e}")
                return

            try:
                result = run_intake(pdf_path, file_id=file_id, filename=file_name)
                print(f"[OK] Processed {file_name}: {result['transactions_written']} transactions ({result['status']})")
            except Exception as e:
                with db.fresh_connection() as conn:
                    db.log_error(conn, file_name, "intake_orchestrator", str(e))
                print(f"[ERROR] Intake failed for {file_name}: {e}")
                return

            try:
                source.move_to_processed(service, file_id)
            except Exception as e:
                with db.fresh_connection() as conn:
                    db.log_error(conn, file_name, "drive_move", str(e))
                print(f"[WARN] Loaded but failed to move file in Drive: {file_name}: {e}")
                return
    else:
        ensure_local_dirs()
        local_path = os.path.join(LOCAL_INPUT_DIR, file_name)
        if not os.path.exists(local_path):
            with db.fresh_connection() as conn:
                db.log_error(conn, file_name, "local_file_missing", f"Local file missing: {local_path}")
            print(f"[WARN] Skipped missing local file: {file_name}")
            return

        try:
            result = run_intake(local_path, file_id=file_id, filename=file_name)
            print(f"[OK] Processed {file_name}: {result['transactions_written']} transactions ({result['status']})")
        except Exception as e:
            with db.fresh_connection() as conn:
                db.log_error(conn, file_name, "intake_orchestrator", str(e))
            print(f"[ERROR] Intake failed for {file_name}: {e}")
            return

        try:
            shutil.move(local_path, os.path.join(LOCAL_PROCESSED_DIR, file_name))
        except Exception as e:
            with db.fresh_connection() as conn:
                db.log_error(conn, file_name, "local_move", str(e))
            print(f"[WARN] Loaded but failed to move local file: {file_name}: {e}")
            return


def load_files(service) -> None:
    ensure_local_dirs()
    files = source.list_input_files(service)
    if not files:
        print(f"No files found to load ({DATA_SOURCE} mode).")
        return

    print(f"Found {len(files)} file(s) to load ({DATA_SOURCE} mode).")
    for file_meta in files:
        process_single_file(service, file_meta)


def main() -> None:
    parser = argparse.ArgumentParser(description="Finance Agent Intake Runner")
    parser.add_argument(
        "mode",
        nargs="?",
        default="load",
        choices=["load", "all"],
        help="Run mode: load statement files into DB",
    )
    args = parser.parse_args()

    # Ensure database file & tables are initialized unconditionally on start
    with db.fresh_connection() as conn:
        db.init_db(conn)

    service = source.get_drive_service() if DATA_SOURCE == "drive" else None
    load_files(service)


if __name__ == "__main__":
    main()
