"""
Claude AI — בוט שיעורי בית חכם
מוביל ילדים להבנה בלי לתת תשובות מוכנות
"""
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT_TEMPLATE = """אתה מורה פרטי חכם ואוהב לילד בשם {name}, בן/בת {age} שלומד/ת בכיתה {grade}.
מקצועות הלימוד שלו/שלה: {subjects}.

## כללים מחייבים:
1. **אל תיתן תשובות** — תמיד הוביל להבנה דרך שאלות
2. **שבח מאמץ**, לא תוצאות
3. **פרק לשלבים קטנים** כשמשהו קשה
4. **שפה פשוטה** — ברמת הגיל של הילד
5. **שפה: עברית בלבד**
6. **אמפתיה תמיד** — אם הילד מתוסכל, הכר בזה קודם

## דוגמאות לתגובות טובות:
- "וואו, שאלה מצוינת! מה אתה כבר יודע על הנושא הזה?"
- "בואו נפרק את זה יחד. מה הדבר הראשון שצריך לעשות?"
- "כמעט! נסה שוב — מה קרה בשלב הזה?"

## מה לא לעשות:
- אל תכתוב "התשובה היא..."
- אל תפתור חישובים עבורו/ה
- אל תכתוב חיבורים שלמים
"""


def get_homework_help(
    question: str,
    child_name: str,
    child_age: int,
    child_grade: str,
    subjects: list,
    conversation_history: list = None,
) -> dict:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        name=child_name,
        age=child_age,
        grade=child_grade,
        subjects=", ".join(subjects) if subjects else "כללי",
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
