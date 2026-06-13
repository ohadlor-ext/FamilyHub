"""
Telegram Bot — תזכורות, פקודות מהירות, עדכוני משפחה
"""
import os
import logging
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
FAMILY_CHAT_ID = os.getenv("TELEGRAM_FAMILY_CHAT_ID")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 שלום! אני הבוט של המשפחה שלכם!\n\n"
        "הפקודות הזמינות:\n"
        "/events — אירועים של היום\n"
        "/tasks — משימות פתוחות\n"
        "/shopping — רשימת קניות\n"
        "/weather — מזג אוויר\n"
        "/help — עזרה"
    )


async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from services.openweather import get_current_weather
    weather = await get_current_weather()
    msg = (
        f"{weather['icon']} *מזג אוויר*\n"
        f"🌡️ {weather['temp']}°C (מורגש: {weather['feels_like']}°C)\n"
        f"💧 לחות: {weather['humidity']}%\n"
        f"💨 רוח: {weather['wind_speed']} קמ\"ש\n"
        f"📝 {weather['description']}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def send_reminder(chat_id: str, message: str):
    """שליחת תזכורת לצ'אט ספציפי"""
    bot = Bot(token=BOT_TOKEN)
    await bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")


async def send_family_notification(message: str):
    """הודעה לקבוצת המשפחה"""
    if FAMILY_CHAT_ID:
        await send_reminder(FAMILY_CHAT_ID, message)


def run_bot():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("weather", weather_command))
    logger.info("🤖 Telegram Bot מופעל!")
    app.run_polling()


if __name__ == "__main__":
    run_bot()
