# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Online platform where friends compete with each other on physical activity from different locations. This is a separate product from the Finde app.

Competitors use health watches, fitness bands and other devices. The platform builds a baseline for each person and sets fair parameters for competing, using GPS, AI and other measures to level differences in location, terrain, device and fitness.

Core concerns:
- **Device data ingestion** — pull activity data (heart rate, steps, pace, distance) from wearables and phone sensors.
- **Baselines** — per-user baseline and normalization so friends of different fitness levels and environments compete fairly.
- **GPS/location** — verify activity and adjust for terrain, elevation and conditions.
- **AI fairness and integrity** — model-driven handicaps and detection of spoofed or implausible data.
- **Social competition** — friends, challenges, leaderboards.

Stack: FastAPI backend, React + TypeScript (Vite) frontend, Supabase for auth, Postgres database and storage.

Status: early scaffold. The backend exposes only `/` and `/health`, and the frontend is the Vite starter. Supabase is not wired in yet.

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
- Treat health and location data as sensitive: never log raw GPS traces or health metrics, keep Supabase service keys server-side only, and enforce Row Level Security on user data tables.
- Fairness logic (baselines, handicaps, anti-cheat) lives in the backend, never only in the frontend.
- Keep backend and frontend dependencies separate: `backend/requirements.txt` and `frontend/package.json`.
- Never commit `.env`, `.venv/`, `node_modules/` or `dist/` (covered by `.gitignore`).
- Development shell is Windows (PowerShell / Git Bash); use Windows venv paths in docs.
- Default branch on GitHub is `main`; local work currently happens on `master`.
