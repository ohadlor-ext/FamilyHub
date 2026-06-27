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
