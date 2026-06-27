"""
הצעת מתכונים — cache להצעה היומית האוטומטית בקיוסק.
הצעת "מה לבשל הערב?" (לחיצת כפתור) לא נשמרת — היא תמיד טרייה.

בנוסף: מאגר מתכונים מבני (Recipe) + תכנון ארוחות שבועי (MealPlan) —
שונה מההצעה היומית למעלה: מתכון פה הוא קבוע וניתן לשימוש חזור,
לא נוצר ונשכח בכל פעם מחדש.
"""
import enum
from sqlalchemy import (
    Column, Integer, String, Date, Text, JSON, DateTime, Boolean,
    Enum, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship
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


class MealType(str, enum.Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"


class RecipeSource(str, enum.Enum):
    SEED = "seed"  # מתכון פתיחה שהוטען מראש
    AI_GENERATED = "ai_generated"  # מתכון שקלוד הציע ונשמר למאגר לשימוש חזור
    FAMILY = "family"  # מתכון שהמשפחה הוסיפה בעצמה


class Recipe(Base):
    """מאגר מתכונים מבני וקבוע — בסיס לתכנון הארוחות השבועי וליצירת רשימת קניות
    אוטומטית. שונה מ-RecipeSuggestion: זה לא נעלם, אפשר לשבץ אותו שוב ושוב."""
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    meal_type = Column(Enum(MealType), default=MealType.DINNER, nullable=False)
    prep_time_minutes = Column(Integer)
    servings = Column(Integer, default=4)
    ingredients = Column(JSON, default=[])  # [{name, quantity, unit}]
    instructions = Column(JSON, default=[])  # [str, str, ...]
    tags = Column(JSON, default=[])  # למשל: ["קל הכנה", "מתאים לילדים", "צמחוני", "מוקפא"]
    source = Column(Enum(RecipeSource), default=RecipeSource.FAMILY, nullable=False)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class MealPlan(Base):
    """שיבוץ מתכון מסוים לתאריך + סוג ארוחה. כרגע בפועל רק dinner בשימוש
    (גרסה ראשונה — ארוחות ערב בלבד), אבל meal_type לא קשיח בכוונה כדי
    שיהיה אפשר להרחיב לבוקר/צהריים בלי לשנות סכמה."""
    __tablename__ = "meal_plans"
    __table_args__ = (UniqueConstraint("plan_date", "meal_type", name="uq_meal_plan_date_type"),)

    id = Column(Integer, primary_key=True, index=True)
    plan_date = Column(Date, nullable=False, index=True)
    meal_type = Column(Enum(MealType), default=MealType.DINNER, nullable=False)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=True)
    notes = Column(Text)  # טקסט חופשי כתחליף למתכון מהמאגר (למשל "אוכלים בחוץ")

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    recipe = relationship("Recipe")
