"""
Family Hub — Backend API
FastAPI + PostgreSQL + Google APIs + Claude AI
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

load_dotenv()

from routers import auth, calendar, tasks, inventory, weather, ai
from database import engine
from models import user, task, inventory as inv_model

# יצירת טבלאות ב-DB
user.Base.metadata.create_all(bind=engine)
task.Base.metadata.create_all(bind=engine)
inv_model.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Family Hub API",
    description="לוח בקרה משפחתי חכם — Backend API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — מאפשר גישה מ-Lovable ומהנייד
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "http://localhost:3000",
        "http://localhost:5173",
        "https://*.lovable.app",
        "https://*.lovableproject.com",
    ],
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
