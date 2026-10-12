import json
import logging
import time
from datetime import datetime

import requests

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import (
    TELEGRAM_BOT_TOKEN,
    GEMINI_API_KEYS,
    GEMINI_MODEL,
)


# ============================================================
# ADMIN
# ============================================================

ADMIN_USER_ID = 7647736924


# ============================================================
# FOZILBEK AI — SYSTEM INSTRUCTION
# ============================================================

SYSTEM_INSTRUCTION = """
Sen Fozilbek AI nomli shaxsiy AI assistantsan.

Foydalanuvchi bilan o'zbek tilida, samimiy va do'stona gaplash.
Foydalanuvchiga "sen" deb murojaat qil.

Foydalanuvchining Telegram First Name'i berilsa,
zarur joylarda ismi bilan murojaat qilishing mumkin.
Ismni haddan tashqari ko'p takrorlama.

Foydalanuvchini "yaratuvchim", "xo'jayinim",
"ustozim" yoki shunga o'xshash haddan tashqari
rasmiy yoki bo'ysunuvchi so'zlar bilan atama.

Murojaat tabiiy, samimiy va do'stona bo'lsin.

Agar foydalanuvchi kod so'rasa:
- ishlaydigan;
- tushunarli;
- to'liq kod ber.

Kimyo, biologiya va matematika masalalarida
hisob-kitoblarni diqqat bilan tekshir.

Bilmagan narsangni o'ylab topma.
Ishonching komil bo'lmasa, buni ochiq ayt.

Foydalanuvchining shaxsiy ma'lumotlarini
o'zingcha taxmin qilma.

Javoblarni foydali, tushunarli va imkon qadar qisqa qil.
"""


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("FozilbekAI")


# ============================================================
# SETTINGS
# ============================================================

MAX_HISTORY = 20
TELEGRAM_LIMIT = 4000

USERS_FILE = "users.json"


# ============================================================
# GEMINI MODELS
# ============================================================

FALLBACK_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
]

MODELS = []

if GEMINI_MODEL:
    MODELS.append(GEMINI_MODEL)

for model in FALLBACK_MODELS:
    if model not in MODELS:
        MODELS.append(model)


# ============================================================
# API KEYS
# ============================================================

API_KEYS = [
    key.strip()
    for key in GEMINI_API_KEYS
    if isinstance(key, str)
    and key.strip()
    and "BU_YERGA" not in key
]


# ============================================================
# GLOBAL DATA
# ============================================================

processed_updates = set()

histories = {}

users = {}

current_key_index = 0


# ============================================================
# USERS DATABASE
# ============================================================

def load_users():
    global users

    try:
        with open(USERS_FILE, "r", encoding="utf-8") as file:
            users = json.load(file)

        logger.info(f"Users yuklandi: {len(users)}")

    except FileNotFoundError:
        users = {}
        save_users()

    except json.JSONDecodeError:
        logger.warning("users.json buzilgan. Yangi baza yaratildi.")
        users = {}
        save_users()


def save_users():
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as file:
            json.dump(
                users,
                file,
                ensure_ascii=False,
                indent=4,
            )

    except Exception as error:
        logger.error(f"Users saqlashda xato: {error}")


def register_user(update):
    if not update.effective_user:
        return

    user = update.effective_user

    user_id = str(user.id)

    first_name = user.first_name or ""

    username = user.username or ""

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    if user_id not in users:

        users[user_id] = {
            "id": user.id,
            "first_name": first_name,
            "username": username,
            "first_seen": now,
            "last_seen": now,
            "messages": 0,
        }

        logger.info(
            f"Yangi foydalanuvchi: "
            f"{first_name} | ID={user.id}"
        )

    else:

        users[user_id]["first_name"] = first_name

        users[user_id]["username"] = username

        users[user_id]["last_seen"] = now

    users[user_id]["messages"] += 1

    save_users()


# ============================================================
# ADMIN CHECK
# ============================================================

def is_admin(update):
    if not update.effective_user:
        return False

    return update.effective_user.id == ADMIN_USER_ID


# ============================================================
# GEMINI KEY
# ============================================================

def get_current_key():

    global current_key_index

    if not API_KEYS:
        raise RuntimeError(
            "config.py ichida Gemini API key topilmadi."
        )

    return API_KEYS[current_key_index]


def switch_key():

    global current_key_index

    if len(API_KEYS) <= 1:
        return False

    old_index = current_key_index

    current_key_index = (
        current_key_index + 1
    ) % len(API_KEYS)

    print(
        f"[Gemini] API key almashtirildi: "
        f"{old_index + 1} -> "
        f"{current_key_index + 1}"
    )

    return True


# ============================================================
# TEXT SPLITTER
# ============================================================

def split_text(
    text,
    limit=TELEGRAM_LIMIT
):

    if len(text) <= limit:
        return [text]

    chunks = []

    while text:

        if len(text) <= limit:
            chunks.append(text)
            break

        cut = text.rfind(
            "\n",
            0,
            limit
        )

        if cut < 500:
            cut = text.rfind(
                " ",
                0,
                limit
            )

        if cut < 500:
            cut = limit

        chunks.append(
            text[:cut]
        )

        text = text[cut:].lstrip()

    return chunks


# ============================================================
# GEMINI REQUEST
# ============================================================

def request_model(
    model,
    history
):

    key = get_current_key()

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{model}:generateContent"
        f"?key={key}"
    )

    contents = []

    for message in history:

        contents.append(
            {
                "role": message["role"],
                "parts": [
                    {
                        "text": message["text"]
                    }
                ],
            }
        )

    payload = {

        "systemInstruction": {
            "parts": [
                {
                    "text": SYSTEM_INSTRUCTION
                }
            ]
        },

        "contents": contents,
    }

    retry_delays = [2, 4, 8]

    for attempt, delay in enumerate(
        retry_delays
    ):

        try:

            print(
                f"[Gemini] "
                f"Model={model} | "
                f"Key={current_key_index + 1}/"
                f"{len(API_KEYS)} | "
                f"Urinish={attempt + 1}/"
                f"{len(retry_delays)}"
            )

            response = requests.post(
                url,
                json=payload,
                timeout=90,
            )

            status = response.status_code


            # ==================================================
            # SUCCESS
            # ==================================================

            if status == 200:

                data = response.json()

                candidates = data.get(
                    "candidates",
                    []
                )

                if not candidates:
                    raise Exception(
                        "Gemini javob yaratmadi."
                    )

                parts = (
                    candidates[0]
                    .get("content", {})
                    .get("parts", [])
                )

                answer_parts = []

                for part in parts:

                    if "text" in part:
                        answer_parts.append(
                            part["text"]
                        )

                answer = "".join(
                    answer_parts
                ).strip()

                if not answer:
                    raise Exception(
                        "Gemini bo'sh javob qaytardi."
                    )

                print(
                    f"[Gemini] "
                    f"{model} -> OK"
                )

                return answer


            # ==================================================
            # RATE LIMIT
            # ==================================================

            if status == 429:

                print(
                    f"[Gemini] "
                    f"{model} -> 429 "
                    f"(limit/quota)"
                )

                switched = switch_key()

                if switched:
                    return None

                if attempt < len(
                    retry_delays
                ) - 1:

                    print(
                        f"[Gemini] "
                        f"Key yagona. "
                        f"{delay} soniya kutmoqda..."
                    )

                    time.sleep(delay)

                    continue

                return None


            # ==================================================
            # SERVER BUSY
            # ==================================================

            if status == 503:

                print(
                    f"[Gemini] "
                    f"{model} -> 503 "
                    f"(server band)"
                )

                if attempt < len(
                    retry_delays
                ) - 1:

                    print(
                        f"[Gemini] "
                        f"{delay} soniya kutmoqda..."
                    )

                    time.sleep(delay)

                    continue

                return None


            # ==================================================
            # OTHER API ERROR
            # ==================================================

            try:

                error_data = response.json()

                error_message = (
                    error_data
                    .get("error", {})
                    .get(
                        "message",
                        "Noma'lum xato"
                    )
                )

            except Exception:

                error_message = (
                    "Noma'lum API xatosi"
                )

            logger.error(
                f"Gemini {model}: "
                f"HTTP {status} - "
                f"{error_message}"
            )

            raise Exception(
                f"Gemini API xatosi ({status})"
            )


        except requests.exceptions.Timeout:

            print(
                f"[Gemini] "
                f"{model} -> TIMEOUT"
            )

            if attempt < len(
                retry_delays
            ) - 1:

                time.sleep(delay)

                continue

            return None


        except requests.exceptions.RequestException as error:

            print(
                f"[Gemini] "
                f"Internet xatosi: {error}"
            )

            if attempt < len(
                retry_delays
            ) - 1:

                time.sleep(delay)

                continue

            return None


# ============================================================
# ASK GEMINI
# ============================================================

def ask_gemini(history):

    print(
        "--------------------------------------"
    )

    print(
        "[Gemini] Javob qidirilmoqda..."
    )

    for index, model in enumerate(
        MODELS
    ):

        print(
            f"[Gemini] Model "
            f"{index + 1}/"
            f"{len(MODELS)}: "
            f"{model}"
        )

        keys_to_try = len(API_KEYS)

        for key_attempt in range(
            keys_to_try
        ):

            answer = request_model(
                model,
                history
            )

            if answer:

                print(
                    f"[Gemini] "
                    f"Ishlagan model: "
                    f"{model}"
                )

                print(
                    "--------------------------------------"
                )

                return answer

            if key_attempt < (
                keys_to_try - 1
            ):

                print(
                    "[Gemini] Key bilan "
                    "javob kelmadi. "
                    "Keyingi key tekshiriladi."
                )

                continue

            break

        if index < len(MODELS) - 1:

            next_model = MODELS[
                index + 1
            ]

            print(
                f"[Gemini] "
                f"{model} ishlamadi."
            )

            print(
                f"[Gemini] "
                f"Fallback -> "
                f"{next_model}"
            )


    print(
        "[Gemini] Barcha "
        "modellar/keylar bilan "
        "javob olinmadi."
    )

    print(
        "--------------------------------------"
    )

    raise Exception(
        "Gemini modellarining "
        "barchasi vaqtincha ishlamadi."
    )


# ============================================================
# USER INFORMATION
# ============================================================

def get_first_name(update):

    if not update.effective_user:
        return None

    first_name = (
        update.effective_user.first_name
    )

    if not first_name:
        return None

    return first_name.strip()


def get_user_id(update):

    if not update.effective_user:
        return None

    return update.effective_user.id


# ============================================================
# /START
# ============================================================

async def start(
    update,
    context
):

    register_user(update)

    first_name = get_first_name(
        update
    )

    if first_name:

        greeting = (
            f"🌌 Salom, {first_name}!"
        )

    else:

        greeting = (
            "🌌 Fozilbek AI'ga "
            "xush kelibsiz!"
        )

    text = (

        f"{greeting}\n\n"

        "Men sening shaxsiy "
        "AI assistantingman.\n\n"

        "Savolingni yozaver — "
        "kod, kimyo, biologiya, "
        "matematika yoki oddiy suhbat.\n\n"

        "📋 Buyruqlar:\n"

        "/start — botni boshlash\n"

        "/help — yordam\n"

        "/clear — suhbat xotirasini tozalash\n"

        "/model — ishlayotgan modellarni ko'rsatish\n"

        "/users — foydalanuvchilar statistikasi "
        "(faqat admin)"
    )

    await update.message.reply_text(
        text
    )


# ============================================================
# /HELP
# ============================================================

async def help_command(
    update,
    context
):

    register_user(update)

    first_name = get_first_name(
        update
    )

    if first_name:

        greeting = (
            f"🤖 {first_name}, "
            "Fozilbek AI yordam:"
        )

    else:

        greeting = (
            "🤖 Fozilbek AI yordam:"
        )

    await update.message.reply_text(

        f"{greeting}\n\n"

        "Oddiy xabar yuborsang, "
        "Gemini javob beradi.\n\n"

        "/clear — suhbat tarixini o'chiradi\n"

        "/model — Gemini modellarini ko'rsatadi\n"

        "/users — foydalanuvchilar statistikasi "
        "(faqat admin)\n"

        "/help — yordam"
    )


# ============================================================
# /CLEAR
# ============================================================

async def clear_command(
    update,
    context
):

    register_user(update)

    user_id = get_user_id(
        update
    )

    if user_id is not None:

        histories.pop(
            user_id,
            None
        )

    first_name = get_first_name(
        update
    )

    if first_name:

        text = (
            f"🧹 {first_name}, "
            "suhbat xotirang tozalandi."
        )

    else:

        text = (
            "🧹 Suhbat xotirasi "
            "tozalandi."
        )

    await update.message.reply_text(
        text
    )


# ============================================================
# /MODEL
# ============================================================

async def model_command(
    update,
    context
):

    register_user(update)

    models_text = "\n".join(
        f"• {model}"
        for model in MODELS
    )

    await update.message.reply_text(

        "🧠 Fozilbek AI "
        "Gemini modellari:\n\n"

        f"{models_text}\n\n"

        f"🔑 API keylar: "
        f"{len(API_KEYS)}\n\n"

        "🔄 Vaqtinchalik xatoda "
        "fallback ishlaydi."
    )


# ============================================================
# /USERS — ADMIN ONLY
# ============================================================

async def users_command(
    update,
    context
):

    register_user(update)

    if not is_admin(update):

        await update.message.reply_text(
            "❌ Bu buyruq faqat "
            "administrator uchun."
        )

        return


    total_users = len(users)


    total_messages = sum(
        user.get(
            "messages",
            0
        )
        for user in users.values()
    )


    if total_users == 0:

        await update.message.reply_text(
            "👥 Hozircha foydalanuvchilar yo'q."
        )

        return


    active_users = sum(
        1
        for user in users.values()
        if user.get("messages", 0) > 0
    )


    # Eng ko'p xabar yuborganlar

    top_users = sorted(
        users.values(),
        key=lambda user: user.get(
            "messages",
            0
        ),
        reverse=True
    )[:10]


    top_text = ""

    for index, user in enumerate(
        top_users,
        start=1
    ):

        name = (
            user.get(
                "first_name",
                ""
            )
            or "Noma'lum"
        )

        username = user.get(
            "username",
            ""
        )

        messages = user.get(
            "messages",
            0
        )

        if username:

            display_name = (
                f"{name} "
                f"(@{username})"
            )

        else:

            display_name = name

        top_text += (
            f"{index}. "
            f"{display_name} — "
            f"{messages} ta xabar\n"
        )


    text = (

        "👥 FOZILBEK AI STATISTIKASI\n\n"

        f"👤 Jami foydalanuvchilar: "
        f"{total_users}\n"

        f"🟢 Faol foydalanuvchilar: "
        f"{active_users}\n"

        f"💬 Jami xabarlar: "
        f"{total_messages}\n\n"

        "🏆 Eng faol foydalanuvchilar:\n"

        f"{top_text}\n"

        "💾 Baza: users.json"
    )


    await update.message.reply_text(
        text
    )


# ============================================================
# MESSAGE HANDLER
# ============================================================

async def handle_message(
    update,
    context
):

    if (
        not update.message
        or not update.message.text
    ):
        return


    register_user(update)


    update_id = update.update_id


    if update_id in processed_updates:

        logger.warning(
            "Duplicate update o'tkazib yuborildi: "
            f"{update_id}"
        )

        return


    processed_updates.add(
        update_id
    )


    if len(
        processed_updates
    ) > 1000:

        processed_updates.clear()


    user_text = (
        update.message.text.strip()
    )


    if not user_text:
        return


    user_id = get_user_id(
        update
    )


    if user_id is None:

        await update.message.reply_text(
            "❌ Foydalanuvchini "
            "aniqlab bo'lmadi."
        )

        return


    history = histories.setdefault(
        user_id,
        []
    )


    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )


    history.append(
        {
            "role": "user",
            "text": user_text
        }
    )


    if len(history) > MAX_HISTORY:

        del history[
            :-MAX_HISTORY
        ]


    try:

        answer = ask_gemini(
            history
        )


        history.append(
            {
                "role": "model",
                "text": answer
            }
        )


        if len(history) > MAX_HISTORY:

            del history[
                :-MAX_HISTORY
            ]


        for chunk in split_text(
            answer
        ):

            await update.message.reply_text(
                chunk
            )


    except Exception as error:

        logger.exception(
            "Gemini xatosi"
        )

        logger.error(
            f"Xato: {error}"
        )

        await update.message.reply_text(

            "❌ Gemini hozircha "
            "javob bera olmadi.\n\n"

            "Birozdan keyin yana "
            "urinib ko'r."
        )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update,
    context
):

    logger.error(
        "Telegram xatosi",
        exc_info=context.error
    )


# ============================================================
# MAIN
# ============================================================

def main():

    # Users bazasini yuklash

    load_users()


    # Telegram token tekshirish

    if (
        not TELEGRAM_BOT_TOKEN
        or "BU_YERGA"
        in TELEGRAM_BOT_TOKEN
    ):

        print(
            "❌ TELEGRAM_BOT_TOKEN "
            "topilmadi."
        )

        return


    # Gemini key tekshirish

    if not API_KEYS:

        print(
            "❌ config.py ichida "
            "Gemini API key topilmadi."
        )

        return


    # ========================================================
    # CONSOLE
    # ========================================================

    print()

    print(
        "======================================"
    )

    print(
        "      🌌 FOZILBEK AI TELEGRAM BOT"
    )

    print(
        "======================================"
    )

    print(
        "🐍 Python: 3.11"
    )

    print(
        f"🔑 API keylar: "
        f"{len(API_KEYS)}"
    )

    print(
        f"🧠 Asosiy model: "
        f"{GEMINI_MODEL}"
    )

    print(
        "🔄 Fallback modellar:"
    )

    for model in MODELS:

        print(
            f"   • {model}"
        )

    print(
        f"👥 Users bazasi: "
        f"{len(users)}"
    )

    print(
        "💾 users.json: ON"
    )

    print(
        "🔐 Admin statistics: ON"
    )

    print(
        "👤 First Name: ON"
    )

    print(
        "📱 Telegramdan /start yubor."
    )

    print(
        "🛑 To'xtatish: Ctrl+C"
    )

    print(
        "======================================"
    )

    print()


    # ========================================================
    # TELEGRAM APP
    # ========================================================

    app = (
        ApplicationBuilder()
        .token(
            TELEGRAM_BOT_TOKEN
        )
        .build()
    )


    # ========================================================
    # COMMANDS
    # ========================================================

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    app.add_handler(
        CommandHandler(
            "clear",
            clear_command
        )
    )

    app.add_handler(
        CommandHandler(
            "model",
            model_command
        )
    )

    app.add_handler(
        CommandHandler(
            "users",
            users_command
        )
    )


    # ========================================================
    # TEXT
    # ========================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_message
        )
    )


    # ========================================================
    # ERROR
    # ========================================================

    app.add_error_handler(
        error_handler
    )


    # ========================================================
    # START POLLING
    # ========================================================

    app.run_polling(
        drop_pending_updates=True
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
