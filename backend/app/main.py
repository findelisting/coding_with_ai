from dotenv import load_dotenv
from fastapi import FastAPI

from app.errors import register_error_handlers
from app.locations import router as locations_router
from app.signup import router as signup_router

load_dotenv()  # SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET from backend/.env

app = FastAPI(title="Backend API")
register_error_handlers(app)
app.include_router(locations_router)
app.include_router(signup_router)


@app.get("/")
def root():
    return {"message": "Backend running"}


@app.get("/health")
def health():
    return {"status": "ok"}
