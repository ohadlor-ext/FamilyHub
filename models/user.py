from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Enum, ForeignKey
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
    tasks = relationship("Task", back_populates="assigned_to_user")
    inventory_items = relationship("InventoryItem", back_populates="added_by_user")


class ChildProfile(Base):
    __tablename__ = "child_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    age = Column(Integer)
    grade = Column(String)
    school = Column(String)
    subjects = Column(JSON, default=[])
    homework_level = Column(String, default="standard")
    avatar_emoji = Column(String, default="🧒")
    color_theme = Column(String, default="#6C63FF")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="child_profile")
