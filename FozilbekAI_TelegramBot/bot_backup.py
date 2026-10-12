import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from google import genai
from google.genai import types

from config import TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, GEMINI_MODEL

# ==============================
# FOZILBEK AI SYSTEM INSTRUCTION
# ==============================
SYSTEM_INSTRUCTION = """
Sen Fozilbek AI nomli shaxsiy AI assistantsan.

Foydalanuvchi bilan o'zbek tilida, samimiy va do'stona gaplash.
Foydalanuvchiga "sen" deb murojaat qil.
Agar foydalanuvchi kod so'rasa, ishlaydigan va tushunarli kod ber.
Kimyo, biologiya va matematika masalalarida hisob-kitoblarni diqqat bilan tekshir.
Bilmagan narsangni o'ylab topma.
Foydalanuvchining shaxsiy ma'lumotlarini o'zingcha taxmin qilma.
Javoblarni foydali, tushunarli va imkon qadar qisqa qil.
"""

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("FozilbekAI")

# Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# Har bir Telegram chat uchun suhbat tarixi.
# Bot qayta ishga tushsa, tarix tozalanadi.
histories = {}

MAX_HISTORY = 20
TELEGRAM_LIMIT = 4000


def split_text(text, limit=TELEGRAM_LIMIT):
    """Telegram uzun xabarlarni qabul qilishi uchun bo'lib yuboradi."""
    if len(text) <= limit:
        return [text]

    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break

        cut = text.rfind("\n", 0, limit)
        if cut < 500:
            cut = text.rfind(" ", 0, limit)
        if cut < 500:
            cut = limit

        chunks.append(text[:cut])
        text = text[cut:].lstrip()

    return chunks


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🌌 Fozilbek AI'ga xush kelibsiz!\n\n"
        "Men sening shaxsiy AI assistantingman.\n"
        "Savolingni yozaver — kod, kimyo, biologiya, matematika yoki oddiy suhbat.\n\n"
        "Buyruqlar:\n"
        "/start — botni boshlash\n"
        "/help — yordam\n"
        "/clear — suhbat xotirasini tozalash\n"
        "/model — ishlayotgan Gemini modelini ko'rsatish"
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Fozilbek AI\n\n"
        "Oddiy xabar yuborsang, Gemini javob beradi.\n\n"
        "/clear — shu chatdagi suhbat tarixini o'chiradi\n"
        "/model — Gemini modelini ko'rsatadi\n"
        "/help — yordam"
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    histories.pop(chat_id, None)
    await update.message.reply_text("🧹 Suhbat xotirasi tozalandi.")


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🧠 Hozirgi model:\n`{GEMINI_MODEL}`",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_text = update.message.text.strip()
    if not user_text:
        return

    chat_id = update.effective_chat.id
    history = histories.setdefault(chat_id, [])

    await context.bot.send_chat_action(
        chat_id=chat_id,
        action="typing",
    )

    # Tarixga foydalanuvchi xabarini qo'shamiz.
    history.append(
        types.Content(
            role="user",
            parts=[types.Part(text=user_text)],
        )
    )

    # Juda katta tarixni cheklaymiz.
    if len(history) > MAX_HISTORY:
        del history[:-MAX_HISTORY]

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=history,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
            ),
        )

        answer = response.text

        if not answer:
            answer = "⚠️ Gemini javob qaytarmadi."

        # Model javobini ham tarixga qo'shamiz.
        history.append(
            types.Content(
                role="model",
                parts=[types.Part(text=answer)],
            )
        )

        if len(history) > MAX_HISTORY:
            del history[:-MAX_HISTORY]

        for chunk in split_text(answer):
            await update.message.reply_text(chunk)

    except Exception as e:
        logger.exception("Gemini xatosi")
        # Foydalanuvchiga texnik xatoni tushunarli ko'rinishda beramiz.
        await update.message.reply_text(
            "❌ Gemini bilan bog'lanishda xatolik yuz berdi.\n\n"
            f"Xato: {str(e)[:1500]}"
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Telegram xatosi", exc_info=context.error)


def main():
    if "BU_YERGA" in TELEGRAM_BOT_TOKEN:
        print("❌ config.py ichiga TELEGRAM_BOT_TOKEN yozilmagan!")
        return

    if "BU_YERGA" in GEMINI_API_KEY:
        print("❌ config.py ichiga GEMINI_API_KEY yozilmagan!")
        return

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("model", model_command))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    app.add_error_handler(error_handler)

    print("======================================")
    print("🌌 FOZILBEK AI TELEGRAM BOT")
    print("✅ Bot ishga tushdi.")
    print("📱 Telegramdan /start yubor.")
    print("🛑 To'xtatish: Ctrl+C")
    print("======================================")

    app.run_polling()


if __name__ == "__main__":
    main()
