import asyncio
import logging
import os

from deep_translator import GoogleTranslator
from telethon import TelegramClient, events

# =========================
# ENV
# =========================
api_id = int(os.environ["api_id"])
api_hash = os.environ["api_hash"]
bot_token = os.environ["bot_token"]
source_channel = os.environ["source_channel"]
discussion_group_id = int(os.environ["discussion_group_id"])

# =========================
# SETTINGS
# =========================
target_language = "en"
translation_header = "English translation:"
update_header = "Updated translation:"
send_delay_seconds = 8  # مهم جدًا لتأخير الإرسال

# =========================
# LOGGING
# =========================
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

client = TelegramClient("translation_bot_session", api_id, api_hash)
translator = GoogleTranslator(source="auto", target=target_language)

# حفظ الرسائل حتى نعدلها لاحقًا
translation_map = {}


# =========================
# HELPERS
# =========================
def split_text(text: str, max_length: int = 4000):
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


def clean_text(text):
    return text.strip() if text else ""


def translate_text(text):
    return translator.translate(text)


# =========================
# SEND TRANSLATION
# =========================
async def send_translation(post_id, final_text):
    # ننتظر حتى يظهر المنشور في الكروب
    await asyncio.sleep(send_delay_seconds)

    sent_ids = []

    for part in split_text(final_text):
        sent = await client.send_message(
            entity=discussion_group_id,
            message=part,
        )
        sent_ids.append(sent.id)

    translation_map[post_id] = sent_ids


# =========================
# UPDATE TRANSLATION
# =========================
async def update_translation(post_id, final_text):
    new_parts = split_text(final_text)

    if post_id not in translation_map:
        await send_translation(post_id, final_text)
        return

    old_ids = translation_map[post_id]
    new_ids = []

    common = min(len(old_ids), len(new_parts))

    # تعديل الموجود
    for i in range(common):
        await client.edit_message(
            entity=discussion_group_id,
            message=old_ids[i],
            text=new_parts[i],
        )
        new_ids.append(old_ids[i])

    # إضافة أجزاء جديدة
    for i in range(common, len(new_parts)):
        sent = await client.send_message(
            entity=discussion_group_id,
            message=new_parts[i],
        )
        new_ids.append(sent.id)

    # حذف الزائد
    if len(old_ids) > len(new_parts):
        await client.delete_messages(
            discussion_group_id,
            old_ids[len(new_parts):]
        )

    translation_map[post_id] = new_ids


# =========================
# NEW POST
# =========================
@client.on(events.NewMessage(chats=source_channel))
async def handle_new_post(event):
    try:
        msg = event.message
        text = clean_text(msg.message)

        if not text:
            logging.info("No text, skipping...")
            return

        logging.info("Translating new post...")
        translated = translate_text(text)

        final_text = f"{translation_header}\n\n{translated}"

        await send_translation(msg.id, final_text)

        logging.info("Done.")

    except Exception as e:
        logging.error(f"Error: {e}")


# =========================
# EDITED POST
# =========================
@client.on(events.MessageEdited(chats=source_channel))
async def handle_edit(event):
    try:
        msg = event.message
        text = clean_text(msg.message)

        if not text:
            return

        logging.info("Updating translation...")
        translated = translate_text(text)

        final_text = f"{update_header}\n\n{translated}"

        await update_translation(msg.id, final_text)

        logging.info("Updated.")

    except Exception as e:
        logging.error(f"Edit error: {e}")


# =========================
# RUN
# =========================
async def main():
    await client.start(bot_token=bot_token)
    logging.info("Bot running...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
