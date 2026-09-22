# coding_with_ai

Monorepo: Python/FastAPI backend + React/Vite/TypeScript frontend.

## Layout

- `/backend` — FastAPI app. See `backend/README.md`.
- `/frontend` — React + Vite + TypeScript app. See `frontend/README.md`.

## Quickstart

Backend:
```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:
```
cd frontend
npm install
npm run dev
```
