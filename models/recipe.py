"""
הצעת מתכונים — cache להצעה היומית האוטומטית בקיוסק.
הצעת "מה לבשל הערב?" (לחיצת כפתור) לא נשמרת — היא תמיד טרייה.
"""
from sqlalchemy import Column, Integer, String, Date, Text, JSON, DateTime
from sqlalchemy.sql import func
from database import Base


class RecipeSuggestion(Base):
    __tablename__ = "recipe_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    suggestion_date = Column(Date, unique=True, index=True)  # אחת ליום — לא משתנה ברענון
    title = Column(String)
    description = Column(Text)
    prep_time_minutes = Column(Integer)
    servings = Column(Integer)
    ingredients = Column(JSON, default=[])  # [{name, quantity, unit, have_in_inventory}]
    instructions = Column(JSON, default=[])  # [str, str, ...]

    created_at = Column(DateTime(timezone=True), server_default=func.now())
