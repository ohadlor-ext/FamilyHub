from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Text, JSON, Enum, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from database import Base


class UserRole(str, enum.Enum):
    PARENT = "parent"
    CHILD = "child"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    google_id = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    picture = Column(String)
    role = Column(Enum(UserRole), default=UserRole.CHILD)
    is_active = Column(Boolean, default=True)

    # Google OAuth tokens
    google_access_token = Column(String)
    google_refresh_token = Column(String)
    google_token_expiry = Column(DateTime)

    # Telegram
    telegram_chat_id = Column(String)

    # הגדרות משתמש
    settings = Column(JSON, default={})

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relations
    child_profile = relationship("ChildProfile", back_populates="user", uselist=False)
    tasks = relationship("Task", foreign_keys="Task.assigned_to", back_populates="assigned_to_user")
    inventory_items = relationship("InventoryItem", back_populates="added_by_user")


class ChildProfile(Base):
    __tablename__ = "child_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    age = Column(Integer)  # ישן/גיבוי — אם יש birth_date, הגיל מחושב ממנו ולא מהשדה הזה
    birth_date = Column(Date)  # תאריך לידה — מאפשר חישוב גיל מדויק שמתעדכן מעצמו
    grade = Column(String)
    school = Column(String)
    subjects = Column(JSON, default=[])
    homework_level = Column(String, default="standard")
    interests = Column(JSON, default=[])  # תחומי עניין/תחביבים
    food_preferences = Column(JSON, default=[])  # מאכלים אהובים — לפיצ'ר הצעת מתכונים
    notes = Column(Text)  # הערה חופשית — כל מידע נוסף שלא מתאים לשדה ייעודי
    avatar_emoji = Column(String, default="🧒")
    color_theme = Column(String, default="#6C63FF")
    # הרשאות תצוגה — מה הילד רואה כשמתחבר עם ה-Gmail שלו במכשיר האישי.
    # ברירת מחדל: כל הקטעים פתוחים (אין regression לפרופילים קיימים).
    # הורה יכול לכבות/להדליק כל קטע בנפרד דרך PATCH /family/children/{id}/permissions.
    # payments/maintenance תמיד כבויים לילד — ניהול כספים/תחזוקה הוא domain של הורה בלבד.
    visible_sections = Column(JSON, default=lambda: {
        "calendar": True,
        "tasks": True,
        "routines": True,
        "points": True,
        "homework": True,
        "meals": True,
        "ai_corner": True,
        "payments": False,
        "maintenance": False,
    })

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="child_profile")
