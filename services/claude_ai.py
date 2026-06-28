"""
Claude AI — בוט שיעורי בית חכם
מוביל ילדים להבנה בלי לתת תשובות מוכנות
"""
import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT_TEMPLATE = """אתה מורה פרטי חכם ואוהב לילד בשם {name}, בן/בת {age} שלומד/ת בכיתה {grade}{school_note}.
מקצועות הלימוד שלו/שלה: {subjects}.
{level_note}{interests_note}
## כללים מחייבים:
1. **אל תיתן תשובות** — תמיד הוביל להבנה דרך שאלות
2. **שבח מאמץ**, לא תוצאות
3. **פרק לשלבים קטנים** כשמשהו קשה
4. **שפה פשוטה** — ברמת הגיל של הילד
5. **שפה: עברית בלבד**
6. **אמפתיה תמיד** — אם הילד מתוסכל, הכר בזה קודם

## כשמבקשים תרגילים לתרגול (לא עזרה בבעיה ספציפית שהילד/ה כבר מנסה לפתור):
זה מצב שונה מ"עזרה בשיעורי בית" — כשמבקשים ממך לייצר תרגילים בנושא, אתה כן נותן תרגילים מוכנים (לא שואל שאלה מנחה במקום תרגיל):
- תן 3-5 תרגילים, מהקל לקשה
- חזותי וקל להבנה, בסגנון שאלות מילוליות אמריקאיות לבית ספר יסודי: הקשר חיי יומיום מוכר (פיצה, שוקולד, עוגה, צעצועים), עם אימוג'ים שמייצגים את הכמויות בפועל (למשל 🍕🍕🍕 מתוך 🍕🍕🍕🍕 בשביל השבר 3/4)
- כל תרגיל בשורה נפרדת ומסומן במספר (1. 2. 3...) — לא פסקה רצופה אחת
- כשמתאים לרמה (בעיקר ברמה רגילה/בסיסית) — אפשר להוסיף אפשרויות תשובה (א/ב/ג/ד), בלי לסמן איזו נכונה
- בסוף, בקש מהילד/ה לנסות לפתור ולשלוח תשובות — ואז תן משוב לפי הכללים הרגילים (בלי לפתור בעצמך)

## דוגמאות לתגובות טובות:
- "וואו, שאלה מצוינת! מה אתה כבר יודע על הנושא הזה?"
- "בואו נפרק את זה יחד. מה הדבר הראשון שצריך לעשות?"
- "כמעט! נסה שוב — מה קרה בשלב הזה?"

## מה לא לעשות:
- אל תכתוב "התשובה היא..."
- אל תפתור חישובים עבורו/ה
- אל תכתוב חיבורים שלמים
"""


_LEVEL_NOTES = {
    "easy": "ההורה ציין/ה שהילד/ה צריך/ה הסברים פשוטים מאוד ומדורגים בצעדים קטנים, בלי לדלג על שום שלב.\n",
    "advanced": "ההורה ציין/ה שהילד/ה מתקדם/ת — אפשר לאתגר יותר ולקצר בהסברים בסיסיים.\n",
}


def get_homework_help(
    question: str,
    child_name: str,
    child_age: int,
    child_grade: str,
    subjects: list,
    conversation_history: list = None,
    homework_level: str = "standard",
    interests: list = None,
    school: str = None,
) -> dict:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        name=child_name,
        age=child_age,
        grade=child_grade,
        school_note=f" בבית ספר {school}" if school else "",
        subjects=", ".join(subjects) if subjects else "כללי",
        level_note=_LEVEL_NOTES.get(homework_level, ""),
        interests_note=(
            f"כשרלוונטי, אפשר לקשר הסברים לתחומי העניין שלו/שלה: {', '.join(interests)}.\n"
            if interests
            else ""
        ),
    )

    messages = conversation_history or []
    messages.append({"role": "user", "content": question})

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )

    ai_response = response.content[0].text
    return {
        "response": ai_response,
        "tokens_used": response.usage.input_tokens + response.usage.output_tokens,
        "updated_history": messages + [{"role": "assistant", "content": ai_response}],
    }


def get_smart_schedule_suggestion(
    family_events: list,
    tasks: list,
    user_name: str,
) -> str:
    events_text = "\n".join([f"- {e['title']} ב-{e['start']}" for e in family_events[:5]])
    tasks_text = "\n".join([f"- {t['title']}" for t in tasks[:5]])

    prompt = f"""המשפחה של {user_name} קיבלה אירועים ומשימות.

אירועים קרובים:
{events_text}

משימות פתוחות:
{tasks_text}

תן עצה קצרה ועוזרת (2-3 משפטים) בעברית לתכנון השבוע. תהיה חם ותומך."""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


# ---------- זיהוי תמונות עבור מלאי (תחליף לסריקת ברקוד) ----------

PRODUCT_IDENTIFY_PROMPT = """אתה מזהה מוצרי מזון/בית מתוך תמונה עבור אפליקציית ניהול מלאי משפחתית.
הסתכל בתמונה וזהה את המוצר. החזר JSON בלבד (בלי טקסט נוסף, בלי markdown) במבנה הזה:
{"name": "<שם המוצר בעברית, קצר וברור>", "category": "<אחת מ: מזון יבש, מוצרי חלב, ירקות ופירות, בשר ודגים, ניקיון, היגיינה, משקאות, חטיפים, קפואים, כללי>", "unit": "<אחת מ: יחידות, קג, גרם, ליטר, מל, אריזות>", "confidence": "<high/medium/low>"}
אם אינך מצליח לזהות מוצר בבירור, החזר {"name": null, "category": null, "unit": null, "confidence": "low"}"""


def identify_product_from_photo(image_b64: str, media_type: str) -> dict:
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                {"type": "text", "text": PRODUCT_IDENTIFY_PROMPT},
            ],
        }],
    )
    return _parse_json_response(response.content[0].text, default={
        "name": None, "category": None, "unit": None, "confidence": "low"
    })


RECEIPT_PARSE_PROMPT_TEMPLATE = """אתה שולף פריטים מתוך תמונה של קבלת קניות, עבור אפליקציית ניהול מלאי משפחתית.
הסתכל בתמונה וזהה כל פריט מזון/בית שנרכש, עם הכמות שלו.
פריטי מלאי קיימים במערכת (להתאמה אם זה כנראה אותו פריט): {existing_names}

החזר JSON בלבד (בלי טקסט נוסף, בלי markdown) — מערך של אובייקטים:
[{{"name": "<שם המוצר בעברית>", "quantity": <מספר>, "unit": "<אחת מ: יחידות, קג, גרם, ליטר, מל, אריזות>", "matched_existing": "<שם מדויק מתוך הרשימה הקיימת אם זה כנראה אותו פריט, אחרת null>"}}]
אם הקבלה לא ברורה או לא ניתן לקרוא פריטים, החזר מערך ריק []."""


def parse_receipt_photo(image_b64: str, media_type: str, existing_names: list) -> list:
    prompt = RECEIPT_PARSE_PROMPT_TEMPLATE.format(
        existing_names=", ".join(existing_names) if existing_names else "אין"
    )
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return _parse_json_response(response.content[0].text, default=[])


# ---------- זיהוי פריטי תחזוקת בית / מסמכים מתוך תמונה ----------

MAINTENANCE_IDENTIFY_PROMPT = """אתה מזהה פריט תחזוקת בית או מסמך/ביטוח מתוך תמונה (תווית מכשיר, מדבקת
דגם, תעודת אחריות, פוליסת ביטוח, רישיון רכב), עבור אפליקציית ניהול בית משפחתית.
הסתכל בתמונה וחלץ מה שאתה יכול. החזר JSON בלבד (בלי טקסט נוסף, בלי markdown) במבנה הזה:
{"name": "<שם קצר וברור לפריט בעברית, למשל 'מזגן סלון - LG' או 'ביטוח דירה - הראל'>", "category": "<אחת מ: מכשיר, רכב, ביטוח, מסמך, אחר>", "next_due_date": "<תאריך תפוגה/חידוש/טיפול הבא בפורמט YYYY-MM-DD אם מצאת בתמונה, אחרת null>", "provider_name": "<שם החברה/יצרן/טכנאי אם מצוין, אחרת null>", "confidence": "<high/medium/low>"}
אם אינך מצליח לזהות פריט בבירור, החזר {"name": null, "category": null, "next_due_date": null, "provider_name": null, "confidence": "low"}"""


def identify_maintenance_item_from_photo(image_b64: str, media_type: str) -> dict:
    """תחליף להקלדה ידנית בתחזוקת הבית — תמונת תווית/מסמך → הצעה לטופס.
    לא שומר את התמונה עצמה (אותו עיקרון כמו identify_product_from_photo למלאי)."""
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                {"type": "text", "text": MAINTENANCE_IDENTIFY_PROMPT},
            ],
        }],
    )
    return _parse_json_response(response.content[0].text, default={
        "name": None, "category": None, "next_due_date": None, "provider_name": None, "confidence": "low"
    })


# ---------- הצעת מתכונים לפי מלאי + העדפות משפחה ----------

RECIPE_SUGGEST_PROMPT_TEMPLATE = """אתה שף משפחתי שממליץ מה לבשל הערב למשפחה ישראלית, בהתבסס על המלאי שיש להם בבית כרגע.

המלאי הנוכחי בבית:
{inventory_text}

מה בני המשפחה אוהבים לאכול (לפי ילד, אם צוין):
{preferences_text}

המשימה שלך:
1. הצע מתכון אחד, מעשי וטעים, לארוחת ערב משפחתית.
2. השתדל להתבסס כמה שאפשר על המלאי הקיים — אבל זה בסדר אם חסר מצרך אחד-שניים, פשוט סמן אותם.
3. קח בחשבון את מה שהמשפחה אוהבת לאכול, אם צוינו העדפות — בלי להתעלם מהמלאי הקיים בשבילן.
4. לכל מצרך במתכון, קבע have_in_inventory לפי השוואה סבירה לרשימת המלאי שניתנה (גם אם השם לא זהה מילה במילה, כל עוד זה כנראה אותו מצרך).

החזר JSON בלבד (בלי טקסט נוסף, בלי markdown) במבנה הזה:
{{
  "title": "<שם המתכון בעברית>",
  "description": "<משפט אחד שמתאר את המתכון>",
  "prep_time_minutes": <מספר, זמן הכנה בדקות>,
  "servings": <מספר מנות>,
  "ingredients": [
    {{"name": "<שם מצרך בעברית>", "quantity": <מספר>, "unit": "<אחת מ: יחידות, קג, גרם, ליטר, מל, אריזות>", "have_in_inventory": <true/false>}}
  ],
  "instructions": ["<שלב 1>", "<שלב 2>", "..."]
}}"""

_DEFAULT_RECIPE = {
    "title": "לא הצלחנו להציע מתכון כרגע",
    "description": "נסו שוב בעוד כמה דקות.",
    "prep_time_minutes": None,
    "servings": None,
    "ingredients": [],
    "instructions": [],
}


def get_recipe_suggestion(inventory_items: list, preferences: list) -> dict:
    """inventory_items: [{"name","quantity","unit","category"}], preferences: ["<מאכל אהוב>", ...]"""
    inventory_text = "\n".join(
        f"- {i['name']} ({i['quantity']} {i['unit']}, {i['category']})" for i in inventory_items
    ) or "המלאי ריק כרגע"
    preferences_text = "\n".join(f"- {p}" for p in preferences) or "לא צוינו העדפות מיוחדות"

    prompt = RECIPE_SUGGEST_PROMPT_TEMPLATE.format(
        inventory_text=inventory_text,
        preferences_text=preferences_text,
    )
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json_response(response.content[0].text, default=_DEFAULT_RECIPE)


# ---------- ייבוא מתכון מעמוד אינטרנט בודד (URL) ----------

RECIPE_IMPORT_PROMPT_TEMPLATE = """אתה עוזר שמייבא מתכון אחד עבור משפחה ישראלית, מתוך תוכן שנשלף מעמוד אינטרנט בודד (לפי בקשה ידנית של המשתמש לעצמו, לא סריקה אוטומטית של אתר שלם).
המקור: {url}

תוכן גולמי שנשלף מהעמוד (עלול להיות JSON-LD מבני של schema.org/Recipe, ו/או טקסט גלוי מהעמוד):
{raw_content}

המשימה שלך:
1. חלץ את שם המתכון, תיאור קצר, זמן הכנה כולל בדקות (שדות prepTime/cookTime/totalTime אם קיימים מגיעים בפורמט ISO 8601 כמו "PT20M" שזה 20 דקות, או "PT1H30M" שזה 90 דקות — תמיר למספר דקות), מספר מנות, רשימת מצרכים מבנית (שם+כמות+יחידה — אם הכמות לא ברורה מהטקסט, תנחש כמות סבירה ביחידה "יחידות"), ותגיות רלוונטיות (למשל "צמחוני", "קל הכנה", "מתאים לילדים", "טבעוני" — רק אם זה ברור מהתוכן).
2. את אופן ההכנה כתוב **במילים שלך, בקצרה ובבירור, כרשימת שלבים** — אסור להעתיק את הטקסט המקורי מילה במילה (שיקולי זכויות יוצרים), רק לתאר את אותן פעולות בניסוח עצמאי.
3. אם שפת המקור אינה עברית, תרגם ונסח הכל בעברית.
4. אם מידע מסוים חסר/לא ברור (לדוגמה זמן הכנה), השאר null במקום להמציא מספר שרירותי.

החזר JSON בלבד (בלי טקסט נוסף, בלי markdown) במבנה הזה:
{{
  "title": "<שם המתכון או null אם לא נמצא מתכון בתוכן>",
  "description": "<תיאור קצר או null>",
  "prep_time_minutes": <מספר או null>,
  "servings": <מספר או null>,
  "ingredients": [{{"name": "<שם מצרך בעברית>", "quantity": <מספר>, "unit": "<אחת מ: יחידות, קג, גרם, ליטר, מל, אריזות>"}}],
  "instructions": ["<שלב 1, מנוסח עצמאית>", "..."],
  "tags": ["<תגית>", "..."]
}}
אם לא הצלחת לזהות מתכון כלשהו בתוכן, החזר {{"title": null}}."""


def import_recipe_from_content(raw_content: str, url: str) -> dict:
    """raw_content: JSON-LD מחולץ או טקסט גלוי מהעמוד (כבר חתוך לאורך סביר ע"י הקורא).
    מחזיר תצוגה מקדימה בלבד — לא שומר. ההוראות מנוסחות מחדש ע"י קלוד, לא מועתקות."""
    prompt = RECIPE_IMPORT_PROMPT_TEMPLATE.format(url=url, raw_content=raw_content)
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json_response(response.content[0].text, default={"title": None})


# ---------- פינת AI לילדים: סיפור, סקרנות, חידה/בדיחה, רעיון יצירה ----------

def _age_note(age: int) -> str:
    if age <= 6:
        return "מאוד פשוט: משפטים קצרים, מילים יומיומיות, בלי עלילה מסובכת או הפשטות."
    if age <= 9:
        return "פשוט וברור, אפשר עלילה קצרה עם שלב-שלב, משפטים לא ארוכים."
    return "אפשר עלילה מורכבת יותר, משפטים ארוכים יותר ואוצר מילים עשיר יותר."


AI_CORNER_STORY_PROMPT = """אתה מספר סיפורי לילה טוב לילדים, כותב בעברית פשוטה ומתאימה לגיל.
כתוב סיפור לילה טוב קצר (כ-150-300 מילים) לילד/ה בשם {name}, בגיל {age}{interests_note}{topic_note}.

## כללים מחייבים:
1. סיפור חמים, מרגיע ומתאים לקראת שינה — בלי מתח, פחד או אלימות; סוף טוב וחיובי
2. רמת שפה: {age_note}
3. עברית פשוטה וברורה, בלי תוכן בוגר בכל אופן

החזר JSON בלבד (בלי טקסט נוסף, בלי markdown):
{{"title": "<שם קצר לסיפור>", "content": "<גוף הסיפור, פסקאות מופרדות ב-\\n\\n>"}}"""

AI_CORNER_CURIOSITY_PROMPT = """אתה עוזר סקרן וחם שעונה לילדים על שאלות "למה?" ושאלות סקרנות על העולם, בעברית פשוטה.
הילד/ה {name}, בגיל {age}, שאל/ה: "{topic}"

## כללים מחייבים:
1. תשובה קצרה ומעניינת (2-4 משפטים), רמת שפה: {age_note}
2. תעורר סקרנות נוספת — אפשר לסיים בשאלה קטנה שמזמינה חשיבה
3. תשובה מדויקת ככל האפשר, בלי להמציא עובדות — אם לא בטוח, אפשר לומר את זה בפשטות
4. אם השאלה נושקת לנושא רגיש (מוות, מחלה, פחד וכו'), ענה בעדינות ובקצרה והפנה לשיחה עם הורה
5. עברית פשוטה, חמה ותומכת, בלי תוכן בוגר בכל אופן

החזר JSON בלבד (בלי טקסט נוסף, בלי markdown):
{{"title": "<השאלה בקצרה>", "content": "<התשובה>"}}"""

AI_CORNER_RIDDLE_JOKE_PROMPT = """אתה ממציא חידה אחת או בדיחה אחת מצחיקה ומתאימה לילדים, בעברית.
לילד/ה בשם {name}, בגיל {age}{topic_note}.

## כללים מחייבים:
1. תוכן קליל ומשעשע, רמת שפה: {age_note}, בלי תוכן פוגעני/מפחיד/בוגר
2. אם זו חידה — כתוב את החידה, שורה ריקה, "---", שורה ריקה, ואז את הפתרון
3. אם זו בדיחה — קצרה וברורה, עם פאנץ' פשוט לגיל הזה
4. עברית פשוטה

החזר JSON בלבד (בלי טקסט נוסף, בלי markdown):
{{"title": "<'חידה' או 'בדיחה'>", "content": "<הטקסט המלא, כולל פתרון לחידה אם רלוונטי>"}}"""

AI_CORNER_CREATIVE_PROMPT = """אתה נותן רעיון יצירתי אחד לציור או יצירה לילד/ה, בעברית — לא תמונה, רק תיאור מילולי שמעורר דמיון (לא הוראות טכניות "איך לצייר").
לילד/ה בשם {name}, בגיל {age}{interests_note}{topic_note}.

## כללים מחייבים:
1. תאר בקצרה (2-4 משפטים) רעיון מקורי וכיפי לציור/יצירה — דמות, עולם, או סיטואציה מדומיינת
2. עורר דמיון: מה-לצייר, לא איך-לצייר
3. רמת שפה: {age_note}, חיובי ומשעשע, בלי תוכן בוגר/מפחיד
4. עברית פשוטה

החזר JSON בלבד (בלי טקסט נוסף, בלי markdown):
{{"title": "<שם קצר לרעיון>", "content": "<התיאור>"}}"""

_AI_CORNER_TEMPLATES = {
    "story": AI_CORNER_STORY_PROMPT,
    "curiosity": AI_CORNER_CURIOSITY_PROMPT,
    "riddle_joke": AI_CORNER_RIDDLE_JOKE_PROMPT,
    "creative": AI_CORNER_CREATIVE_PROMPT,
}

_AI_CORNER_DEFAULT = {"title": None, "content": "לא הצלחנו ליצור תוכן כרגע. נסו שוב בעוד כמה דקות."}


def get_ai_corner_content(
    content_type: str,
    child_name: str,
    child_age: int,
    interests: list = None,
    topic: str = None,
) -> dict:
    """content_type: story / curiosity / riddle_joke / creative.
    topic: לסקרנות זו השאלה עצמה (חובה); לאחרים נושא/בקשה חופשית-אופציונלית."""
    template = _AI_CORNER_TEMPLATES[content_type]
    prompt = template.format(
        name=child_name,
        age=child_age,
        age_note=_age_note(child_age),
        interests_note=(
            f", שאוהב/ת {', '.join(interests)}" if interests else ""
        ),
        topic_note=(f", בנושא/בקשה: {topic}" if topic and content_type != "curiosity" else ""),
        topic=topic or "",
    )
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json_response(response.content[0].text, default=_AI_CORNER_DEFAULT)


# ---------- טלגרם → רשומה: זיהוי וחילוץ מהודעת טקסט חופשית ----------
# מסווג כל הודעה לאחת מחמש קטגוריות (event/payment/maintenance/task/none) ומחלץ
# את השדות הרלוונטיים לאותה קטגוריה. routers/telegram.py מחליט לפי category לאיזו
# טבלה/שירות ליצור את הרשומה (Task / RecurringPayment / MaintenanceItem / יומן iCloud).

_TELEGRAM_WEEKDAY_HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]

TELEGRAM_MESSAGE_PROMPT_TEMPLATE = """אתה מסנן הודעות טלגרם מתוך קבוצת משפחה, ומחליט אם הן מכילות מידע שצריך לשמור באפליקציית ניהול הבית של המשפחה — ואם כן, לאיזה חלק באפליקציה הן שייכות.

התאריך והשעה כרגע: {now_str}, יום {weekday_he}
בני המשפחה הרשומים במערכת: {family_names}
ההודעה נשלחה ע"י: {sender_name}
תוכן ההודעה: "{text}"

## חמש קטגוריות אפשריות (category):
- "event" — אירוע/פגישה/מסיבה/חוג/תור עם תאריך — מקומו הנכון הוא ביומן, לא ברשימת משימות (למשל: מסיבת יום הולדת/בר-מצווה, תור לרופא, פגישה, אירוע משפחתי).
- "payment" — תשלום שצריך לשלם כדי שלא ייווצר חוב/אי-נעימות (ארנונה, ביטוח, מנוי, קנס, חוב), עם מועד תשלום.
- "maintenance" — טיפול תקופתי במכשיר/רכב, או תוקף מסמך/ביטוח/אחריות שצריך לחדש/לטפל בו, עם תאריך יעד.
- "task" — כל דבר אחר שהוא משימה/תזכורת ברורה לביצוע. גם event/payment/maintenance הופכים ל-"task" אם לא הצלחת לחלץ מהם תאריך קונקרטי (בלי תאריך, event/payment/maintenance לא תקפים).
- "none" — שיחת חולין, שאלה כללית, תגובה להודעת בוט קודמת, או כל דבר אחר שלא אמור להישמר בכלל.

## המשימה שלך:
1. קבע category לפי ההגדרות מעלה.
2. אם category הוא event/payment/maintenance — חובה תאריך קונקרטי (date), אחרת הורד category ל-"task" (או "none" אם גם זה לא מתאים).
3. חלץ כותרת קצרה וברורה (title) — אפשר לנסח טוב יותר מהמקור, אבל לשמור על המשמעות המדויקת.
4. אם יש בהודעה תאריך/שעה (גם יחסיים, כמו "מחר", "ביום שלישי", "בעוד שבועיים") — חשב תאריך מוחלט לפי התאריך הנוכחי, בפורמט "YYYY-MM-DDTHH:MM:SS", ושים בשדה date.
   - אם מוזכרת שעה ספציפית — קבע אותה, ול-event: all_day=false.
   - אם מוזכר רק יום בלי שעה: ל-task/payment/maintenance קבע שעה 09:00. ל-event קבע all_day=true (אירוע יום שלם, כמו מסיבה או חג) ושעה 00:00 ב-date.
   - אם אין שום אזכור זמן בהודעה — date=null (וה-category לא יכול להיות event/payment/maintenance, ראו כלל 2). אל תמציא תאריך.
5. event בלבד: אם יש שעת/תאריך סיום משוערים — end_date באותו פורמט, אחרת null. אם מוזכר מיקום — location, אחרת null.
6. task בלבד: אם מוזכר שם של אחד מבני המשפחה הרשומים (או כינוי קרוב וברור) — assigned_name (השם המדויק מהרשימה), אחרת null. אל תנחש.
7. payment בלבד: amount — סכום מספרי אם מוזכר (ש"ח), אחרת null. recurrence — "weekly"/"monthly"/"yearly" רק אם מוזכרת חזרתיות מפורשת (כל שבוע/חודש/שנה, חודשי, שנתי), אחרת "once".
8. maintenance בלבד: maintenance_category — אחד מ: "מכשיר", "רכב", "ביטוח", "מסמך", "אחר" (ברירת מחדל "אחר" אם לא ברור מההקשר).
9. דרג רמת ביטחון (confidence): "high" רק אם חד-משמעי וברור שזה דבר ששייך לאחת הקטגוריות ושצריך לשמור; "medium" אם כנראה כן אבל הניסוח מעורפל/חלקי; "low" אם מאוד לא בטוח.

החזר JSON בלבד (בלי טקסט נוסף, בלי markdown), עם כל השדות הבאים תמיד (null במה שלא רלוונטי לקטגוריה):
{{"category": "<event/payment/maintenance/task/none>", "confidence": "<high/medium/low>", "title": "<כותרת או null>", "date": "<YYYY-MM-DDTHH:MM:SS או null>", "end_date": "<YYYY-MM-DDTHH:MM:SS או null>", "all_day": <true/false>, "location": "<מיקום או null>", "assigned_name": "<שם מדויק מהרשימה או null>", "amount": <מספר או null>, "recurrence": "<once/weekly/monthly/yearly או null>", "maintenance_category": "<מכשיר/רכב/ביטוח/מסמך/אחר או null>"}}"""

_TELEGRAM_MESSAGE_DEFAULT = {
    "category": "none", "confidence": "low", "title": None, "date": None, "end_date": None,
    "all_day": False, "location": None, "assigned_name": None, "amount": None,
    "recurrence": None, "maintenance_category": None,
}


def parse_telegram_message(text: str, family_member_names: list, sender_name: str, now) -> dict:
    """text: תוכן הודעת הטלגרם. family_member_names: שמות המשתמשים הפעילים במערכת,
    לצורך שיוך אופציונלי במשימות. now: datetime נוכחי (aware, Asia/Jerusalem) לחישוב
    תאריכים יחסיים. מחזיר category אחד מ-event/payment/maintenance/task/none —
    ראו routers/telegram.py לאיך כל category הופך לרשומה בפועל."""
    prompt = TELEGRAM_MESSAGE_PROMPT_TEMPLATE.format(
        now_str=now.strftime("%Y-%m-%d %H:%M"),
        weekday_he=_TELEGRAM_WEEKDAY_HE[now.weekday()],
        family_names=", ".join(family_member_names) if family_member_names else "לא ידוע",
        sender_name=sender_name,
        text=text,
    )
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json_response(response.content[0].text, default=_TELEGRAM_MESSAGE_DEFAULT)


def _parse_json_response(text: str, default):
    text = text.strip()
    # Claude עלול לעטוף ב-```json ... ``` למרות ההנחיה שלא לעשות זאת — מסירים אם קיים
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return default
