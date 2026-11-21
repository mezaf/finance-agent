import logging
import os
import shutil
import sys
from pathlib import Path

from werkzeug.utils import secure_filename

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

logger = logging.getLogger("web_app.processor")

from data_load import run_intake
from data_analysis import (
    get_category_sunburst,
    get_macro_groups,
    get_monthly_expenses,
    get_installments,
    query_insights,
)
from db import db

UPLOAD_FOLDER = Path(os.environ.get("UPLOAD_FOLDER", "uploaded_pdfs"))
PROCESSED_FOLDER = UPLOAD_FOLDER / "processed"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
PROCESSED_FOLDER.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    logger.info("Initializing database connection & schemas...")
    with db.fresh_connection() as conn:
        db.init_db(conn)


def save_uploaded_pdf(file_storage, file_id: str) -> str:
    filename = secure_filename(file_storage.filename)
    dest_filename = f"{file_id}_{filename}"
    dest_path = UPLOAD_FOLDER / dest_filename
    file_storage.save(dest_path)
    logger.info(f"Saved PDF '{filename}' to path: {dest_path}")
    return str(dest_path)


def get_uploaded_pdf_path(file_id: str) -> Path:
    matches = list(UPLOAD_FOLDER.glob(f"{file_id}_*"))
    if not matches:
        logger.error(f"File ID {file_id} not found in upload directory: {UPLOAD_FOLDER}")
        raise FileNotFoundError(f"Uploaded file with ID {file_id} not found.")
    return matches[0]


def get_uploaded_pdf_name(file_id: str) -> str:
    path = get_uploaded_pdf_path(file_id)
    return path.name.split("_", 1)[1]


def get_uploaded_pdf_info(file_id: str) -> dict:
    path = get_uploaded_pdf_path(file_id)
    filename = path.name.split("_", 1)[1]
    return {
        "file_name": filename,
        "status": "pending",
    }


def process_uploaded_pdf(file_id: str) -> dict:
    try:
        pdf_path = get_uploaded_pdf_path(file_id)
        filename = get_uploaded_pdf_name(file_id)
        logger.info(f"Executing 5-step Intake Orchestrator for PDF: {filename} ({pdf_path})...")
        
        result = run_intake(str(pdf_path), file_id=file_id, filename=filename)
        logger.info(f"Intake Orchestrator completed for {filename}: {result['transactions_written']} transactions committed.")

        try:
            destination = PROCESSED_FOLDER / pdf_path.name
            shutil.move(str(pdf_path), destination)
            logger.info(f"Moved processed PDF to: {destination}")
        except Exception as move_err:
            logger.warning(f"Could not move PDF to processed folder: {move_err}")

        charts = get_all_chart_data()

        return {
            "success": True,
            "action": "processed",
            "message": f"Successfully processed {filename}: {result['transactions_written']} transactions committed.",
            "transactions_written": result.get("transactions_written", 0),
            "result": result,
            "charts": charts,
        }
    except Exception as exc:
        logger.exception(f"Intake Orchestrator failed for file_id {file_id}: {exc}")
        return {
            "success": False,
            "message": f"Failed to process statement: {exc}",
        }


def get_all_chart_data(month: str | None = None, macro_group: str | None = None) -> dict:
    with db.fresh_connection() as conn:
        monthly = get_monthly_expenses(conn, month=month, macro_group=macro_group)
        macro = get_macro_groups(conn, month=month)
        sunburst = get_category_sunburst(conn, month=month, macro_group=macro_group)
        installments = get_installments(conn, month=month)

        return {
            "monthly_expenses": monthly,
            "macro_groups": macro,
            "category_sunburst": sunburst,
            "installments": installments,
            "filter_applied": {"month": month, "macro_group": macro_group},
        }


def get_dashboard_summary() -> dict:
    with db.fresh_connection() as conn:
        macro = get_macro_groups(conn)
        monthly = get_monthly_expenses(conn)
        return {
            "macro_groups": macro,
            "monthly_expenses": monthly,
        }


def get_recent_transactions(limit: int = 20) -> list[dict]:
    with db.fresh_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE excluded_from_budget = 0 AND account_type = 'tdc' ORDER BY date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_analysis_data(month: str | None = None, macro_group: str | None = None) -> dict:
    with db.fresh_connection() as conn:
        return get_category_sunburst(conn, month=month, macro_group=macro_group)
