"""
מתכוני פתיחה למאגר המתכונים — נטענים אוטומטית באתחול השרת אם טבלת
recipes ריקה (אידמפוטנטי, לא יוצר כפילויות בהפעלות חוזרות).
12 מתכוני ארוחת ערב משפחתיים-ישראליים, מגוונים (בשרי/צמחוני/טבעוני,
קל/בינוני בהכנה) — נקודת התחלה למתכנן השבועי, לא רשימה סגורה.
"""
from sqlalchemy.orm import Session
from models.recipe import Recipe, MealType, RecipeSource

SEED_RECIPES = [
    {
        "title": "שניצל עוף עם פירה ושעועית ירוקה",
        "description": "קלאסיקה משפחתית שכל הילדים אוהבים.",
        "prep_time_minutes": 35,
        "servings": 4,
        "tags": ["מתאים לילדים", "קל הכנה"],
        "ingredients": [
            {"name": "שניצל עוף", "quantity": 8, "unit": "יחידות"},
            {"name": "תפוחי אדמה", "quantity": 1, "unit": "קג"},
            {"name": "שעועית ירוקה", "quantity": 400, "unit": "גרם"},
            {"name": "חלב", "quantity": 100, "unit": "מל"},
            {"name": "חמאה", "quantity": 30, "unit": "גרם"},
        ],
        "instructions": [
            "מטגנים או אופים את השניצלים עד הזהבה.",
            "מבשלים תפוחי אדמה במים רותחים עד שמתרככים, מועכים עם חלב וחמאה.",
            "מאדים את השעועית הירוקה כ-5 דקות.",
            "מגישים הכל יחד חם.",
        ],
    },
    {
        "title": "פסטה בולונז",
        "description": "רוטב עגבניות עשיר עם בקר טחון, ילדים ומבוגרים אוהבים.",
        "prep_time_minutes": 40,
        "servings": 5,
        "tags": ["מתאים לילדים", "מוקפא"],
        "ingredients": [
            {"name": "פסטה", "quantity": 500, "unit": "גרם"},
            {"name": "בקר טחון", "quantity": 400, "unit": "גרם"},
            {"name": "רסק עגבניות", "quantity": 2, "unit": "אריזות"},
            {"name": "בצל", "quantity": 1, "unit": "יחידות"},
            {"name": "שום", "quantity": 2, "unit": "יחידות"},
        ],
        "instructions": [
            "מטגנים בצל ושום קצוץ עד שקוף.",
            "מוסיפים בקר טחון ומטגנים עד השחמה.",
            "מוסיפים רסק עגבניות ומים, מבשלים על אש קטנה 20 דקות.",
            "מבשלים פסטה לפי ההוראות ומגישים עם הרוטב.",
        ],
    },
    {
        "title": "עוף בתנור עם תפוחי אדמה ובצל",
        "description": "ארוחת ערב פשוטה שמתבשלת לבד בתנור.",
        "prep_time_minutes": 70,
        "servings": 5,
        "tags": ["קל הכנה", "פרווה לסירוגין"],
        "ingredients": [
            {"name": "חזה עוף", "quantity": 1, "unit": "קג"},
            {"name": "תפוחי אדמה", "quantity": 1, "unit": "קג"},
            {"name": "בצל", "quantity": 2, "unit": "יחידות"},
            {"name": "שמן זית", "quantity": 50, "unit": "מל"},
        ],
        "instructions": [
            "חוצים תפוחי אדמה ובצל לקוביות, מניחים בתבנית עם העוף.",
            "מתבלים בשמן זית, מלח ופפריקה.",
            "אופים ב-200 מעלות כ-50 דקות עד שמשחים.",
        ],
    },
    {
        "title": "שקשוקה עם סלט וחומוס",
        "description": "ארוחת ערב קלה וטבעונית-חלבית, מוכנה ברבע שעה.",
        "prep_time_minutes": 20,
        "servings": 4,
        "tags": ["צמחוני", "קל הכנה", "מהיר"],
        "ingredients": [
            {"name": "ביצים", "quantity": 8, "unit": "יחידות"},
            {"name": "עגבניות", "quantity": 6, "unit": "יחידות"},
            {"name": "בצל", "quantity": 1, "unit": "יחידות"},
            {"name": "פלפל אדום", "quantity": 1, "unit": "יחידות"},
            {"name": "פיתות", "quantity": 4, "unit": "יחידות"},
        ],
        "instructions": [
            "מטגנים בצל ופלפל, מוסיפים עגבניות קצוצות ומבשלים לרוטב.",
            "שוברים ביצים מעל הרוטב ומכסים עד שמתבשלות.",
            "מגישים עם פיתות חמות וסלט.",
        ],
    },
    {
        "title": "אורז עם עדשים וירקות מוקפצים",
        "description": "מנה טבעונית מזינה ומלאה בטעמים.",
        "prep_time_minutes": 35,
        "servings": 4,
        "tags": ["טבעוני", "בריא"],
        "ingredients": [
            {"name": "אורז", "quantity": 2, "unit": "אריזות"},
            {"name": "עדשים", "quantity": 1, "unit": "אריזות"},
            {"name": "גזר", "quantity": 3, "unit": "יחידות"},
            {"name": "קישוא", "quantity": 2, "unit": "יחידות"},
        ],
        "instructions": [
            "מבשלים אורז ועדשים בנפרד לפי ההוראות.",
            "מוקפצים גזר וקישוא קצוצים בשמן עם תבלינים.",
            "מגישים הכל יחד בקערה.",
        ],
    },
    {
        "title": "קציצות בקר ברוטב עגבניות עם אורז",
        "description": "ארוחת ערב חמה וביתית, נהדרת גם להקפאה.",
        "prep_time_minutes": 45,
        "servings": 5,
        "tags": ["מתאים לילדים", "מוקפא"],
        "ingredients": [
            {"name": "בקר טחון", "quantity": 500, "unit": "גרם"},
            {"name": "ביצים", "quantity": 1, "unit": "יחידות"},
            {"name": "רסק עגבניות", "quantity": 1, "unit": "אריזות"},
            {"name": "אורז", "quantity": 2, "unit": "אריזות"},
        ],
        "instructions": [
            "מעצבים קציצות מהבקר הטחון עם ביצה ותבלינים.",
            "מטגנים קלות מכל הצדדים.",
            "מוסיפים רסק עגבניות ומים ומבשלים 20 דקות.",
            "מגישים עם אורז מבושל.",
        ],
    },
    {
        "title": "פלאפל ושווארמה בפיתה עם סלט",
        "description": "ארוחת רחוב ביתית, מהירה וטבעונית.",
        "prep_time_minutes": 25,
        "servings": 4,
        "tags": ["טבעוני", "מהיר"],
        "ingredients": [
            {"name": "פלאפל קפוא", "quantity": 1, "unit": "אריזות"},
            {"name": "פיתות", "quantity": 4, "unit": "יחידות"},
            {"name": "חומוס", "quantity": 1, "unit": "אריזות"},
            {"name": "מלפפון", "quantity": 3, "unit": "יחידות"},
            {"name": "עגבניות", "quantity": 3, "unit": "יחידות"},
        ],
        "instructions": [
            "מטגנים או אופים את הפלאפל לפי ההוראות על האריזה.",
            "קוצצים סלט ירקות טרי.",
            "ממלאים פיתות עם פלאפל, חומוס וסלט.",
        ],
    },
    {
        "title": "מרק ירקות עם כדורי בשר",
        "description": "מרק מחמם ומשביע לימי חורף.",
        "prep_time_minutes": 50,
        "servings": 5,
        "tags": ["מוקפא", "בריא"],
        "ingredients": [
            {"name": "בקר טחון", "quantity": 300, "unit": "גרם"},
            {"name": "גזר", "quantity": 3, "unit": "יחידות"},
            {"name": "תפוחי אדמה", "quantity": 3, "unit": "יחידות"},
            {"name": "סלרי", "quantity": 1, "unit": "יחידות"},
        ],
        "instructions": [
            "מעצבים כדורי בשר קטנים מהבקר הטחון.",
            "מרתיחים ירקות חתוכים בסיר מים עם תבלינים.",
            "מוסיפים את כדורי הבשר ומבשלים 25 דקות.",
        ],
    },
    {
        "title": "פסטה ברוטב שמנת עם פטריות",
        "description": "מנה צמחונית עשירה שמוכנה תוך חצי שעה.",
        "prep_time_minutes": 30,
        "servings": 4,
        "tags": ["צמחוני", "מהיר"],
        "ingredients": [
            {"name": "פסטה", "quantity": 500, "unit": "גרם"},
            {"name": "שמנת מתבשלת", "quantity": 250, "unit": "מל"},
            {"name": "פטריות", "quantity": 300, "unit": "גרם"},
            {"name": "שום", "quantity": 2, "unit": "יחידות"},
        ],
        "instructions": [
            "מטגנים שום ופטריות חתוכות בחמאה.",
            "מוסיפים שמנת ומבשלים 5 דקות.",
            "מערבבים עם פסטה מבושלת ומגישים.",
        ],
    },
    {
        "title": "סלמון אפוי עם ירקות בתנור",
        "description": "ארוחת ערב קלה ובריאה, הכל בתבנית אחת.",
        "prep_time_minutes": 35,
        "servings": 4,
        "tags": ["בריא", "קל הכנה"],
        "ingredients": [
            {"name": "פילה סלמון", "quantity": 4, "unit": "יחידות"},
            {"name": "ברוקולי", "quantity": 1, "unit": "אריזות"},
            {"name": "תפוחי אדמה", "quantity": 600, "unit": "גרם"},
            {"name": "לימון", "quantity": 1, "unit": "יחידות"},
        ],
        "instructions": [
            "מניחים סלמון וירקות בתבנית עם שמן זית ולימון.",
            "אופים ב-200 מעלות 25 דקות.",
        ],
    },
    {
        "title": "בורגול עם ירקות ועוף בגריל",
        "description": "מנה מאוזנת עם בורגול מבושל וחזה עוף.",
        "prep_time_minutes": 35,
        "servings": 4,
        "tags": ["בריא"],
        "ingredients": [
            {"name": "בורגול", "quantity": 1, "unit": "אריזות"},
            {"name": "חזה עוף", "quantity": 600, "unit": "גרם"},
            {"name": "פלפל אדום", "quantity": 2, "unit": "יחידות"},
            {"name": "בצל", "quantity": 1, "unit": "יחידות"},
        ],
        "instructions": [
            "מבשלים בורגול לפי ההוראות.",
            "צולים חזה עוף חתוך לקוביות עם ירקות במחבת.",
            "מערבבים הכל יחד ומגישים.",
        ],
    },
    {
        "title": "פיצה ביתית עם ירקות",
        "description": "ערב פיצה משפחתי — כל אחד בוחר תוספות.",
        "prep_time_minutes": 45,
        "servings": 5,
        "tags": ["מתאים לילדים", "צמחוני"],
        "ingredients": [
            {"name": "בסיס פיצה", "quantity": 2, "unit": "יחידות"},
            {"name": "רסק עגבניות", "quantity": 1, "unit": "אריזות"},
            {"name": "גבינה צהובה", "quantity": 300, "unit": "גרם"},
            {"name": "פטריות", "quantity": 200, "unit": "גרם"},
            {"name": "פלפל אדום", "quantity": 1, "unit": "יחידות"},
        ],
        "instructions": [
            "מורחים רסק עגבניות על הבסיסים.",
            "מפזרים גבינה וירקות לפי הטעם.",
            "אופים ב-220 מעלות כ-12 דקות עד שהגבינה נמסה.",
        ],
    },
]


def seed_recipes_if_empty(db: Session) -> int:
    """טוען את מתכוני הפתיחה רק אם טבלת recipes ריקה לחלוטין —
    אידמפוטנטי, בטוח להריץ בכל עליית שרת. מחזיר כמה מתכונים נוספו."""
    existing_count = db.query(Recipe).count()
    if existing_count > 0:
        return 0

    for data in SEED_RECIPES:
        recipe = Recipe(
            title=data["title"],
            description=data["description"],
            meal_type=MealType.DINNER,
            prep_time_minutes=data["prep_time_minutes"],
            servings=data["servings"],
            ingredients=data["ingredients"],
            instructions=data["instructions"],
            tags=data["tags"],
            source=RecipeSource.SEED,
        )
        db.add(recipe)
    db.commit()
    return len(SEED_RECIPES)
