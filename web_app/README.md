# Finance Agent Web App

This folder contains the Flask + React web application for the Finance Agent project.

## Running the backend

From the project root:

```bash
pip install -r web_app/requirements.txt
export FLASK_APP=web_app/app.py
flask run
```

## Running the frontend

From `web_app/frontend`:

```bash
npm install
npm start
```

The frontend is designed to talk to the Flask backend on `/api` endpoints.

## Notes

- Uploaded PDFs are stored in `web_app/uploaded_pdfs`.
- Processed uploads are moved to `web_app/uploaded_pdfs/processed`.
- The backend reuses the existing statement ingestion and categorization modules.
- The React app includes a dashboard with interactive chart foundations and a chat panel for LLM-based interaction.
