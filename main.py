"""
main.py — monthly run entry point.

Flow:
    1. List PDFs in Drive Input folder
    2. Skip files already processed (tracked in the DB, not just by moving them)
    3. Parse filename -> determine bank (and account_type/card_network, except Santander)
    4. Download PDF, run the matching bank extractor (Claude API)
    5. Categorize each transaction (20/70/10)
    6. Embed + insert into SQLite (structured + vector)
    7. Move the file to Processed in Drive
    8. On any failure for a given file: log it and continue to the next file
       (one bad statement should never block the rest of the batch)

Run:
    python main.py
"""

import os
import tempfile

from dotenv import load_dotenv

import db
import drive_client
from categorize import categorize_transaction
from embeddings import encode_text, build_embedding_text

from extractors import bbva, galicia, bna, santander

load_dotenv()

EXTRACTOR_MAP = {
    "bbva": bbva.extract,
    "galicia": galicia.extract,
    "bna": bna.extract,
    "santander": santander.extract,
}


def process_file(conn, service, file_meta: dict) -> None:
    file_id = file_meta["id"]
    file_name = file_meta["name"]

    if db.is_file_processed(conn, file_id):
        print(f"skip (already processed): {file_name}")
        return

    parsed = drive_client.parse_filename(file_name)
    if parsed is None:
        db.log_error(conn, file_name, "filename_parse",
                     f"Filename doesn't match expected pattern: {file_name}")
        print(f"⚠️  skipped, unrecognized filename: {file_name}")
        return

    bank = parsed["bank"]
    extractor_fn = EXTRACTOR_MAP.get(bank)
    if extractor_fn is None:
        db.log_error(conn, file_name, "extractor_lookup", f"No extractor registered for bank: {bank}")
        print(f"⚠️  skipped, no extractor for bank: {bank}")
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = os.path.join(tmp_dir, file_name)

        try:
            drive_client.download_file(service, file_id, pdf_path)
        except Exception as e:
            db.log_error(conn, file_name, "download", str(e))
            print(f"❌ download failed: {file_name} — {e}")
            return

        try:
            raw_transactions = extractor_fn(pdf_path)
        except Exception as e:
            db.log_error(conn, file_name, "extraction", str(e))
            print(f"❌ extraction failed: {file_name} — {e}")
            return

        inserted = 0
        for raw_txn in raw_transactions:
            try:
                # For all banks except Santander, account_type/card_network come
                # from the filename. Santander's extractor supplies them per-line.
                account_type = raw_txn.get("account_type") or parsed.get("account_type")
                card_network = raw_txn.get("card_network") or parsed.get("card_network")

                cat = categorize_transaction(raw_txn["description"], raw_txn["amount"])

                txn = {
                    "date": raw_txn["date"],
                    "bank": bank,
                    "account_type": account_type,
                    "card_network": card_network,
                    "description": raw_txn["description"],
                    "amount": raw_txn["amount"],
                    "currency": raw_txn["currency"],
                    "installment": raw_txn.get("installment"),
                    "bucket": cat["bucket"],
                    "source_file_id": file_id,
                }

                embedding_text = build_embedding_text(txn)
                embedding = encode_text(embedding_text)
                db.insert_transaction(conn, txn, embedding)
                inserted += 1

                if cat["low_confidence"]:
                    print(f"   ⚠️  low-confidence categorization: '{txn['description']}' -> spend (review)")

            except Exception as e:
                db.log_error(conn, file_name, "categorization_or_insert", f"{e} — txn: {raw_txn}")
                continue  # one bad row shouldn't drop the whole file

        print(f"✅ {file_name}: {inserted}/{len(raw_transactions)} transactions stored")

        try:
            drive_client.move_to_processed(service, file_id)
            db.mark_file_processed(conn, file_id, file_name)
        except Exception as e:
            db.log_error(conn, file_name, "drive_move", str(e))
            print(f"⚠️  stored but failed to move file in Drive: {file_name} — {e}")


def main():
    conn = db.get_connection()
    db.init_db(conn)

    service = drive_client.get_drive_service()
    files = drive_client.list_input_files(service)

    if not files:
        print("No files found in Input folder.")
        return

    print(f"Found {len(files)} file(s) in Input folder.")
    for file_meta in files:
        process_file(conn, service, file_meta)

    conn.close()


if __name__ == "__main__":
    main()