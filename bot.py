import asyncio
import logging
import os
import re

from deep_translator import GoogleTranslator
from telethon import TelegramClient, events

api_id = int(os.environ["api_id"])
api_hash = os.environ["api_hash"]
bot_token = os.environ["bot_token"]
source_channel = os.environ["source_channel"].lstrip("@").lower()
discussion_group_id = int(os.environ["discussion_group_id"])

client = TelegramClient("translation_bot_session", api_id, api_hash)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# =========================
# تحديد اللغة
# =========================
def detect_language(text):
    if re.search(r'[\u0600-\u06FF]', text):  # عربي/فارسي
        # نميز الفارسي عن العربي
        if re.search(r'[گچپژ]', text):
            return "fa"
        return "ar"
    return "en"


def clean_text(text):
    return text.strip() if text else ""


def split_text(text, max_length=4000):
    parts = []
    while len(text) > max_length:
        split_at = text.rfind("\n", 0, max_length)
        if split_at == -1:
            split_at = max_length
        parts.append(text[:split_at])
        text = text[split_at:].lstrip()
    if text:
        parts.append(text)
    return parts


def translate(text, target):
    return GoogleTranslator(source="auto", target=target).translate(text)


def is_channel_post(message):
    sender = getattr(message, "sender", None)

    if sender and getattr(sender, "username", None):
        return sender.username.lower() == source_channel

    if sender and getattr(sender, "title", None):
        return sender.title.lower() == source_channel

    return False


# =========================
# إرسال الترجمة
# =========================
async def send_translation(msg_id, text):
    lang = detect_language(text)

    results = []

    if lang == "ar":
        results.append(translate(text, "en"))
        results.append(translate(text, "fa"))

    elif lang == "en":
        results.append(translate(text, "ar"))
        results.append(translate(text, "fa"))

    elif lang == "fa":
        results.append(translate(text, "ar"))
        results.append(translate(text, "en"))

    for t in results:
        for part in split_text(t):
            await client.send_message(
                discussion_group_id,
                part,
                reply_to=msg_id
            )


# =========================
# التقاط المنشورات
# =========================
@client.on(events.NewMessage(chats=discussion_group_id))
async def handler(event):
    try:
        msg = event.message

        if not is_channel_post(msg):
            return

        text = clean_text(msg.message)
        if not text:
            return

        # 🔥 تأخير بسيط حتى يظهر المنشور أولاً
        await asyncio.sleep(0)

        await send_translation(msg.id, text)

        logging.info("Translation sent")

    except Exception as e:
        logging.error(e)


# =========================
# التشغيل
# =========================
async def main():
    await client.start(bot_token=bot_token)
    print("Bot running...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
