import asyncio
import logging
import os

from deep_translator import GoogleTranslator
from telethon import TelegramClient, events

api_id = int(os.environ["api_id"])
api_hash = os.environ["api_hash"]
bot_token = os.environ["bot_token"]
source_channel = os.environ["source_channel"]
discussion_group_id = int(os.environ["discussion_group_id"])

target_language = "en"
translation_header = "English translation:"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

client = TelegramClient("translation_bot_session", api_id, api_hash)
translator = GoogleTranslator(source="auto", target=target_language)

# حفظ رسائل الترجمة حتى نعدلها عند تعديل المنشور
translation_map = {}


def split_text(text: str, max_length: int = 4000) -> list[str]:
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


def clean_text(text: str | None) -> str:
    return text.strip() if text else ""


def translate_text(text: str) -> str:
    return translator.translate(text)


async def send_translation(post_id: int, final_text: str) -> None:
    sent_ids = []

    for part in split_text(final_text):
        sent = await client.send_message(
            entity=discussion_group_id,
            message=part,
        )
        sent_ids.append(sent.id)

    translation_map[post_id] = sent_ids


async def update_translation(post_id: int, final_text: str) -> None:
    new_parts = split_text(final_text)

    if post_id not in translation_map:
        await send_translation(post_id, final_text)
        return

    old_ids = translation_map[post_id]
    new_ids = []

    common_count = min(len(old_ids), len(new_parts))

    for i in range(common_count):
        await client.edit_message(
            entity=discussion_group_id,
            message=old_ids[i],
            text=new_parts[i],
        )
        new_ids.append(old_ids[i])

    for i in range(common_count, len(new_parts)):
        sent = await client.send_message(
            entity=discussion_group_id,
            message=new_parts[i],
        )
        new_ids.append(sent.id)

    if len(old_ids) > len(new_parts):
        extra_ids = old_ids[len(new_parts):]
        await client.delete_messages(discussion_group_id, extra_ids)

    translation_map[post_id] = new_ids


@client.on(events.NewMessage(chats=source_channel))
async def handle_new_post(event) -> None:
    try:
        message = event.message
        original_text = clean_text(message.message)

        if not original_text:
            logging.info("Post has no text or caption. Skipping.")
            return

        logging.info("New post detected. Translating...")
        translated_text = translate_text(original_text)
        final_text = f"{translation_header}\n\n{translated_text}"

        await send_translation(message.id, final_text)
        logging.info("Translation sent successfully.")

    except Exception as e:
        logging.error(f"Error while handling new post: {e}")


@client.on(events.MessageEdited(chats=source_channel))
async def handle_edited_post(event) -> None:
    try:
        message = event.message
        original_text = clean_text(message.message)

        if not original_text:
            logging.info("Edited post has no text or caption. Skipping.")
            return

        logging.info("Edited post detected. Updating translation...")
        translated_text = translate_text(original_text)
        final_text = f"{translation_header}\n\n{translated_text}"

        await update_translation(message.id, final_text)
        logging.info("Translation updated successfully.")

    except Exception as e:
        logging.error(f"Error while handling edited post: {e}")


async def main() -> None:
    await client.start(bot_token=bot_token)
    logging.info("Bot is running...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
