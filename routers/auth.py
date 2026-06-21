"""
Authentication Router — כניסה דרך Google OAuth
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
from models.user import User, UserRole
from services.google_auth import (
    get_google_auth_url,
    exchange_code_for_tokens,
    get_google_user_info,
    create_jwt_token,
    verify_jwt_token,
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


@router.get("/google/login")
def google_login():
    """מפנה את המשתמש לאימות Google"""
    auth_url = get_google_auth_url()
    return RedirectResponse(url=auth_url)


@router.get("/google/callback")
def google_callback(code: str, db: Session = Depends(get_db)):
    """קבלת callback מ-Google לאחר אימות"""
    try:
        tokens = exchange_code_for_tokens(code)
        user_info = get_google_user_info(tokens["access_token"])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"שגיאת אימות Google: {str(e)}")

    user = db.query(User).filter(User.google_id == user_info["id"]).first()

    if not user:
        # ילד שכבר יש לו פרופיל (נוצר ע"י הורה ב-הגדרות, עם ה-Gmail האמיתי שלו) —
        # כניסה ראשונה עם Google משייכת את החשבון לפרופיל הקיים, במקום ליצור הורה חדש.
        pending_child = (
            db.query(User)
            .filter(User.email == user_info["email"], User.role == UserRole.CHILD)
            .first()
        )
        if pending_child:
            pending_child.google_id = user_info["id"]
            pending_child.picture = pending_child.picture or user_info.get("picture")
            user = pending_child
        else:
            user = User(
                google_id=user_info["id"],
                email=user_info["email"],
                name=user_info["name"],
                picture=user_info.get("picture"),
                role=UserRole.PARENT,
            )
            db.add(user)

    user.google_access_token = tokens["access_token"]
    user.google_refresh_token = tokens.get("refresh_token", user.google_refresh_token)
    user.google_token_expiry = tokens.get("expiry")
    db.commit()
    db.refresh(user)

    jwt_token = create_jwt_token(user.id)
    # /auth/success לא קיים כ-route בפרונט (Lovable) — /login הוא שכבר קולט ?token=
    # ושומר אותו ב-localStorage (ראה src/routes/login.tsx)
    return RedirectResponse(url=f"{FRONTEND_URL}/login?token={jwt_token}")


@router.get("/me")
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    """מידע על המשתמש המחובר"""
    user_id = verify_jwt_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="טוקן לא תקין")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="משתמש לא נמצא")

    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "picture": user.picture,
        "role": user.role,
    }


def get_current_user_dep(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Dependency לקבלת המשתמש המחובר"""
    user_id = verify_jwt_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="טוקן לא תקין")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="משתמש לא נמצא")
    return user
