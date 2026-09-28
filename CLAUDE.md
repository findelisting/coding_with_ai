# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Monorepo with a Python/FastAPI backend and a React + Vite + TypeScript frontend. Early scaffold stage: the backend exposes only `/` and `/health`, and the frontend is the Vite starter.

## Layout

- `backend/` — FastAPI app. Entry point `backend/app/main.py` (`app = FastAPI(...)`). Config via `.env` (see `backend/.env.example`, `PORT=8000`).
- `frontend/` — React 19 + Vite 8 + TypeScript 6. Source in `frontend/src/`, linted with oxlint (`.oxlintrc.json`).
- `test/` — pytest tests (e.g. `test_user_name.py`). Uses relative imports, so run from the repo root as a package.

## Commands

Backend (Windows, from `backend/`):
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload     # http://127.0.0.1:8000/health
```

Frontend (from `frontend/`):
```
npm install
npm run dev       # dev server
npm run build     # tsc -b && vite build
npm run lint      # oxlint
npm run preview
```

Tests (from repo root):
```
python -m pytest test
```

## Conventions

- Plan work as user stories broken into Features, then Tasks, then implementation. For each feature, note what is being built underneath it.
- Keep backend and frontend dependencies separate: `backend/requirements.txt` and `frontend/package.json`.
- Never commit `.env`, `.venv/`, `node_modules/` or `dist/` (covered by `.gitignore`).
- Development shell is Windows (PowerShell / Git Bash); use Windows venv paths in docs.
- Default branch on GitHub is `main`; local work currently happens on `master`.

## Related context

- The Finde app uses Supabase auth. Confirmation emails depend on Supabase's default sender (about 2 emails/hour). Custom SMTP on thefindeapp.com is a blocker before promotion. See `fix the email issue.txt`.
