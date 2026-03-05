# Paper Local (V1)

Local-first literature management and reading system.

## Features

- Local PDF drag-and-drop import.
- Metadata candidate extraction (filename + first-page text) with manual confirmation.
- Paper library management with tags.
- Full-text search via SQLite FTS5 (`title/authors/abstract/notes/content`).
- Reader view + note extraction.
- Duplicate candidate detection (title/author fuzzy matching).
- Citation export (`BibTeX`, `APA`).
- Scheduled auto-backup (daily + weekly) and restore.

## Stack

- Backend: FastAPI + SQLAlchemy + SQLite (WAL, FTS5) + APScheduler.
- Frontend: React + Vite + TypeScript + TanStack Query + react-pdf (pdf.js).
- Deployment: Docker Compose (`api` + `web`).

## Quick start

```bash
docker compose up -d --build
```

- API: http://localhost:8000/docs
- Web: http://localhost:5173

## macOS app packaging (.app)

Build a standalone macOS app with an embedded backend and frontend.

```bash
./scripts/build_mac_app.sh
```

After build, open:

```bash
open /Users/jinlunzhang/Documents/doc/dist/PaperLocal.app
```

Notes:

- The app stores data in `~/Library/Application Support/PaperLocal/storage`.
- Build requires `node/npm` and `python3`.
- If Gatekeeper blocks first launch, right-click `PaperLocal.app` and choose `Open`.

Run desktop mode directly from source (without packaging):

```bash
./scripts/run_mac_app_dev.sh
```

## Local development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Important directories

- `backend/app/api/routes.py`: all required V1 APIs.
- `backend/app/models.py`: core data model.
- `backend/app/services/`: PDF parse, FTS update, duplicate detection, citation, backup.
- `frontend/src/pages/LibraryPage.tsx`: import/search/library page.
- `frontend/src/pages/PaperDetailPage.tsx`: reader/notes/citation/backup page.
- `storage/`: local data (`app.db`, attachments, backups).

## Backend tests

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. pytest app/tests -q
```

## API summary (V1)

- `POST /api/v1/import/pdf`
- `POST /api/v1/papers/confirm`
- `GET /api/v1/papers`
- `GET /api/v1/papers/{id}`
- `POST /api/v1/papers/{id}`
- `GET /api/v1/search`
- `POST /api/v1/papers/{id}/notes`
- `GET /api/v1/papers/{id}/notes`
- `DELETE /api/v1/notes/{note_id}`
- `GET /api/v1/papers/{id}/duplicates`
- `POST /api/v1/papers/{id}/duplicates/resolve`
- `GET /api/v1/papers/{id}/citation?style=bibtex|apa`
- `POST /api/v1/citation/batch`
- `POST /api/v1/backup/run`
- `GET /api/v1/backup/list`
- `POST /api/v1/backup/restore`
