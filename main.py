"""
Telegram Guruh Spam Filter Bot
================================
O'rnatish:
    pip install python-telegram-bot==20.7

Ishlatish:
    1. @BotFather dan bot yarating, TOKEN oling
    2. BOT_TOKEN ga yozing
    3. Botni guruhga ADMIN qiling (xabar o'chirish huquqi bilan)
    4. python spam_filter_bot.py
"""

import re
import logging
from telegram import Update, ChatPermissions
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from datetime import datetime, timedelta

# ============================================================
# SOZLAMALAR
# ============================================================
BOT_TOKEN = "SIZNING_BOT_TOKEN_INGIZ"   # @BotFather dan oling

BAN_AFTER_WARNINGS    = 3     # Necha marta ogohlantirish keyin ban
MUTE_DURATION_MINUTES = 60   # Mute qilish vaqti (daqiqa), 0 = to'g'ridan ban
IGNORE_ADMINS         = True  # Adminlarni tekshirmasin

ALLOWED_DOMAINS = [
    # "yoursite.com",  # Ruxsat etilgan domenlar (izohni olib tashlang)
]

BLOCKED_DOMAINS = [
    "alijahon.uz", "bit.ly", "tinyurl.com",
    "cutt.ly", "is.gd", "shorturl.at",
]

SPAM_KEYWORDS = [
    # Profil/kanal reklamasi
    "profilimda", "profilida", "mening kanalim", "mening profilim",
    "profilga kiring", "profilimga kiring", "profile da",
    "na moyom kanale", "moyom profile", "perejdi v profil",
    # Buyurtma / narx reklamasi
    "buyurtma bering", "buyurtma berish", "narxi:", "narx :",
    "chegirma", "skidka", "discount", "aksiya", "promo kodi",
    "sotib oling", "xarid qiling", "zakazyvajte",
    # Pul / investitsiya spam
    "zarabot", "earn money", "passivnyj doxod",
    "passive income", "kriptovalyut", "crypto signal",
    "forex signal", "investits", "invest now",
    # Subscribe / follow spam
    "podpisyvajtes", "subscribe", "follow me",
    "click here", "bosing", "click link",
    "besplatno", "tekin", "free gift",
    # Bot/referral spam
    "bot orqali", "botga yozing", "pishite botu",
    "referral", "referal", "@oqim",
    # Kafolat spam
    "100% kafolat", "garantiya", "guarantee",
]

CAPS_LOCK_THRESHOLD = 0.70   # 70% katta harf bo'lsa spam
MIN_CAPS_LENGTH     = 20     # Bu uzunlikdan qisqa bo'lsa tekshirilmaydi
MAX_LINKS_ALLOWED   = 2      # Xabarda nechta linkdan ko'p bo'lsa spam
MAX_MENTIONS        = 3      # Xabarda nechta @mention dan ko'p bo'lsa spam

# ============================================================
# ICHKI MANTIQ
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

user_warnings: dict[int, int] = {}


def is_spam(text: str) -> tuple[bool, str]:
    if not text:
        return False, ""

    lower = text.lower()

    # 1. Kalit so'zlar
    for kw in SPAM_KEYWORDS:
        if kw in lower:
            return True, f"spam kalit so'z: '{kw}'"

    # 2. Domenlar
    urls = re.findall(r'https?://([^\s/]+)', lower)
    plain = re.findall(r'(?<!\w)([\w-]+\.(?:uz|ru|com|net|org|io|me))', lower)
    for domain in urls + plain:
        domain = domain.lstrip("www.")
        if any(a in domain for a in ALLOWED_DOMAINS):
            continue
        if any(b in domain for b in BLOCKED_DOMAINS):
            return True, f"bloklangan domen: '{domain}'"

    # 3. Ko'p link
    link_count = len(re.findall(r'https?://', text))
    if link_count > MAX_LINKS_ALLOWED:
        return True, f"{link_count} ta link topildi"

    # 4. Ko'p @ mention
    mentions = re.findall(r'@\w+', text)
    if len(mentions) >= MAX_MENTIONS:
        return True, f"{len(mentions)} ta @mention topildi"

    # 5. CAPS LOCK
    if len(text) >= MIN_CAPS_LENGTH:
        letters = [c for c in text if c.isalpha()]
        if letters:
            ratio = sum(1 for c in letters if c.isupper()) / len(letters)
            if ratio >= CAPS_LOCK_THRESHOLD:
                return True, f"CAPS LOCK spam ({int(ratio*100)}%)"

    return False, ""


async def is_admin(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user    = update.effective_user
    chat    = update.effective_chat

    if not message or not user or not chat:
        return
    if chat.type == "private":
        return
    if IGNORE_ADMINS and await is_admin(chat.id, user.id, context):
        return

    text = message.text or message.caption or ""
    spam, reason = is_spam(text)

    if not spam:
        return

    # ---- SPAM TOPILDI ----
    username = f"@{user.username}" if user.username else user.full_name
    user_warnings[user.id] = user_warnings.get(user.id, 0) + 1
    warnings = user_warnings[user.id]

    logger.info(f"SPAM | {username} | {reason} | ogohlantirish: {warnings}")

    # Xabarni o'chir
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Xabarni o'chirib bo'lmadi: {e}")

    # Ban yoki Mute
    if warnings >= BAN_AFTER_WARNINGS:
        try:
            if MUTE_DURATION_MINUTES > 0:
                until = datetime.now() + timedelta(minutes=MUTE_DURATION_MINUTES)
                await context.bot.restrict_chat_member(
                    chat.id, user.id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until
                )
                action_text = (
                    f"⛔ {username} {MUTE_DURATION_MINUTES} daqiqa "
                    f"MUTE qilindi (spam uchun)."
                )
            else:
                await context.bot.ban_chat_member(chat.id, user.id)
                action_text = f"🚫 {username} BAN qilindi (spam uchun)."

            user_warnings[user.id] = 0
            await context.bot.send_message(chat.id, action_text)
            logger.info(action_text)
        except Exception as e:
            logger.error(f"Ban/mute qilishda xato: {e}")
    else:
        remaining = BAN_AFTER_WARNINGS - warnings
        try:
            warn_msg = await context.bot.send_message(
                chat.id,
                f"⚠️ {username}, spam xabar o'chirildi!\n"
                f"Sabab: {reason}\n"
                f"Ogohlantirish: {warnings}/{BAN_AFTER_WARNINGS} "
                f"(yana {remaining} ta qoldi)"
            )
            # Ogohlantirish xabarini 10 soniyadan keyin o'chir
            context.job_queue.run_once(
                lambda ctx: ctx.bot.delete_message(chat.id, warn_msg.message_id),
                when=10
            )
        except Exception as e:
            logger.warning(f"Ogohlantirish xabarini yuborib bo'lmadi: {e}")


def main():
    if BOT_TOKEN == "SIZNING_BOT_TOKEN_INGIZ":
        print("Xato: BOT_TOKEN ni o'zgartiring!")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # Barcha matnli xabarlar va rasm captionlarini ushlaydi
    app.add_handler(MessageHandler(
        filters.TEXT | filters.CAPTION,
        handle_message
    ))

    print("Spam filter bot ishga tushdi...")
    print(f"   Ban chegarasi : {BAN_AFTER_WARNINGS} ogohlantirish")
    print(f"   Mute vaqti    : {MUTE_DURATION_MINUTES} daqiqa")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
