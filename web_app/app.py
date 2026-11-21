import logging
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

# Configure verbose debugging & structured logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("web_app")

from processor import (
    get_all_chart_data,
    get_analysis_data,
    get_dashboard_summary,
    get_recent_transactions,
    get_uploaded_pdf_info,
    init_db,
    process_uploaded_pdf,
    save_uploaded_pdf,
)
from chat import simple_intent_matches

load_dotenv()

UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "uploaded_pdfs")
Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
Path(UPLOAD_FOLDER, "processed").mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder="frontend_static", static_url_path="/")
app.debug = True
CORS(app)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

init_db()


@app.before_request
def log_request_info():
    logger.debug(f"--> Incoming {request.method} {request.path} | Args: {dict(request.args)}")


@app.route("/api/upload", methods=["POST"])
def upload_file():
    logger.info("Received /api/upload request.")
    if "file" not in request.files:
        logger.warning("Upload failed: No file part in request.")
        return jsonify({"error": "No file part in the request."}), 400

    file = request.files["file"]
    if file.filename == "":
        logger.warning("Upload failed: Empty filename.")
        return jsonify({"error": "No file selected for upload."}), 400

    try:
        file_id = str(uuid.uuid4())
        saved_path = save_uploaded_pdf(file, file_id)
        info = get_uploaded_pdf_info(file_id)

        logger.info(f"Successfully saved uploaded file: {info['file_name']} (ID: {file_id}) at {saved_path}")
        return jsonify({
            "fileId": file_id,
            "fileName": info["file_name"],
            "status": "uploaded",
            "message": f"File '{info['file_name']}' uploaded successfully.",
        })
    except Exception as exc:
        logger.exception(f"Exception during /api/upload: {exc}")
        return jsonify({"error": f"Failed to upload file: {str(exc)}"}), 500


@app.route("/api/process_upload/<file_id>", methods=["POST"])
def process_upload(file_id):
    logger.info(f"Received request to process uploaded file_id={file_id}")
    try:
        result = process_uploaded_pdf(file_id)
        return jsonify(result)
    except Exception as exc:
        logger.exception(f"Exception during /api/process_upload/{file_id}: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/charts", methods=["GET"])
def charts():
    month = request.args.get("month")
    macro_group = request.args.get("macro_group")
    logger.info(f"Fetching /api/charts with month={month}, macro_group={macro_group}")
    return jsonify(get_all_chart_data(month=month, macro_group=macro_group))


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    file_id = data.get("fileId")

    logger.info(f"Received /api/chat message: '{message}' | fileId: {file_id}")

    if not message:
        return jsonify({"error": "Message text is required."}), 400

    if file_id and simple_intent_matches(message):
        logger.info(f"Detected processing intent for fileId={file_id}. Running Intake Orchestrator...")
        result = process_uploaded_pdf(file_id)
        logger.info(f"Intake processing result for fileId={file_id}: {result}")
        return jsonify({
            "reply": result["message"],
            "action": result.get("action", "processed"),
            "fileId": file_id,
            "charts": result.get("charts") or get_all_chart_data(),
        })

    try:
        from data_analysis.analysis import answer_chat_query
        from db import db as db_mod

        with db_mod.fresh_connection() as conn:
            result = answer_chat_query(conn, message, data.get("history"))
        return jsonify(result)
    except Exception as exc:
        logger.exception(f"Exception during /api/chat: {exc}")
        return jsonify({"reply": "I couldn't query the transaction data just now. Please try again."}), 500


@app.route("/api/summary", methods=["GET"])
def summary():
    return jsonify(get_dashboard_summary())


@app.route("/api/transactions", methods=["GET"])
def transactions():
    limit = int(request.args.get("limit", 20))
    return jsonify(get_recent_transactions(limit=limit))


@app.route("/api/analysis", methods=["GET"])
def analysis():
    month = request.args.get("month")
    macro_group = request.args.get("macro_group")
    return jsonify(get_analysis_data(month, macro_group))


@app.route("/api/analysis_query", methods=["POST"])
def analysis_query():
    data = request.get_json(force=True)
    prompt = data.get("prompt") or data.get("message") or ""
    logger.info(f"Received /api/analysis_query prompt: '{prompt}'")
    from data_analysis import query_insights
    from db import db as db_mod

    try:
        with db_mod.fresh_connection() as conn:
            result = query_insights(conn, prompt)
        return jsonify(result)
    except Exception as exc:
        logger.exception(f"Exception during /api/analysis_query: {exc}")
        return jsonify({"error": f"Query execution failed: {str(exc)}"}), 500


@app.route("/api/pdf/<file_id>", methods=["GET"])
def serve_pdf(file_id):
    """Serve the original uploaded PDF file."""
    logger.info(f"Received request to serve PDF file_id={file_id}")
    try:
        info = get_uploaded_pdf_info(file_id)
        file_path = info["file_path"]

        logger.info(f"Serving PDF file: {info['file_name']} from {file_path}")
        return send_file(file_path, as_attachment=True)
    except Exception as exc:
        logger.exception(f"Exception during serve_pdf for file_id={file_id}: {exc}")
        return jsonify({"error": "Failed to retrieve the PDF file."}), 500


@app.route("/api/source_pdf", methods=["GET"])
def source_pdf():
    requested = (request.args.get("name") or "").strip()
    if not requested:
        return jsonify({"error": "Source filename is required."}), 400

    safe_name = Path(requested).name
    project_root = Path(__file__).resolve().parent.parent
    roots = [
        project_root / "local_processed",
        project_root / "uploaded_pdfs",
        project_root / "uploaded_pdfs" / "processed",
    ]
    matches = []
    for root in roots:
        if root.is_file():
            matches.append(root)
        elif root.is_dir():
            matches.extend(path for path in root.rglob(safe_name) if path.is_file())
            matches.extend(path for path in root.rglob(f"*_{safe_name}") if path.is_file())

    unique_matches = list(dict.fromkeys(matches))
    if not unique_matches:
        return jsonify({"error": "Source PDF not found."}), 404

    return send_file(unique_matches[0], mimetype="application/pdf", as_attachment=False, download_name=safe_name)


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_static(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    logger.info("Starting Flask application with DEBUG=True...")
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
