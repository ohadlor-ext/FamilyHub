"""
Family Hub — Backend API
FastAPI + PostgreSQL + Google APIs + Claude AI
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

load_dotenv()

from contextlib import asynccontextmanager
from routers import auth, calendar, tasks, inventory, weather, ai
from database import engine, Base
from models import user, task, inventory as inv_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    # יצירת טבלאות ב-DB בזמן startup — עם טיפול בשגיאות
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created/verified")
    except Exception as e:
        print(f"⚠️ DB init warning (will retry on first request): {e}")
    yield


app = FastAPI(
    title="Family Hub API",
    description="לוח בקרה משפחתי חכם — Backend API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS — מאפשר גישה מ-Lovable ומהנייד
# הערה: ל-CORSMiddleware של Starlette אין תמיכה ב-wildcard (*) בתוך allow_origins —
# רשימת מחרוזות נבדקת בהשוואה מדויקת בלבד, אז "https://*.lovable.app" לעולם לא תואם
# לאף Origin אמיתי. לכן השתמשנו ב-allow_origin_regex לתת-דומיינים של lovable.
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_origin_regex=r"https://([a-zA-Z0-9-]+\.)*lovable\.app|https://([a-zA-Z0-9-]+\.)*lovableproject\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(calendar.router)
app.include_router(tasks.router)
app.include_router(inventory.router)
app.include_router(weather.router)
app.include_router(ai.router)


@app.get("/")
def root():
    return {
        "app": "Family Hub API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    """בדיקת תקינות — Railway משתמש בזה"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
