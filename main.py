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
from zoneinfo import ZoneInfo
from sqlalchemy import text
from apscheduler.schedulers.background import BackgroundScheduler
from routers import auth, calendar, tasks, inventory, weather, ai, family, recipes
from database import engine, Base
from models import user, task, inventory as inv_model, recipe as recipe_model
from services.notifications import send_morning_summary, send_recipe_notification

scheduler = BackgroundScheduler(timezone=ZoneInfo("Asia/Jerusalem"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # יצירת טבלאות ב-DB בזמן startup — עם טיפול בשגיאות
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created/verified")
    except Exception as e:
        print(f"⚠️ DB init warning (will retry on first request): {e}")

    # create_all לא משנה טבלאות שכבר קיימות — עמודות חדשות שמתוספות למודל
    # (כמו birth_date/interests/notes ב-ChildProfile) צריכות ALTER TABLE ידני.
    # IF NOT EXISTS הופך את זה לאידמפוטנטי — בטוח להריץ בכל עליית שרת.
    try:
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE child_profiles ADD COLUMN IF NOT EXISTS birth_date DATE"
            ))
            conn.execute(text(
                "ALTER TABLE child_profiles ADD COLUMN IF NOT EXISTS interests JSON DEFAULT '[]'"
            ))
            conn.execute(text(
                "ALTER TABLE child_profiles ADD COLUMN IF NOT EXISTS notes TEXT"
            ))
            conn.execute(text(
                "ALTER TABLE child_profiles ADD COLUMN IF NOT EXISTS food_preferences JSON DEFAULT '[]'"
            ))
            conn.commit()
        print("✅ Schema columns (birth_date/interests/notes/food_preferences) verified")
    except Exception as e:
        print(f"⚠️ Schema migration warning: {e}")

    # התראות טלגרם יזומות — בוקר טוב ב-07:30, הצעת מתכון ב-16:00 (שעון ישראל).
    # אם אין TELEGRAM_BOT_TOKEN/TELEGRAM_FAMILY_CHAT_ID ב-env, ה-jobs ירוצו אבל
    # send_message_sync ידלג בשקט (רושם warning ללוג) — לא יקרוס שום דבר.
    scheduler.add_job(send_morning_summary, "cron", hour=7, minute=30, id="morning_summary", replace_existing=True)
    scheduler.add_job(send_recipe_notification, "cron", hour=16, minute=0, id="daily_recipe", replace_existing=True)
    scheduler.start()
    print("✅ Scheduler מופעל — בוקר טוב 07:30, מתכון יומי 16:00")

    yield

    scheduler.shutdown(wait=False)


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
app.include_router(family.router)
app.include_router(recipes.router)


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
