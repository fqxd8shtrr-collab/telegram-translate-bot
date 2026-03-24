import asyncio
import logging
import os

from deep_translator import GoogleTranslator
from telethon import TelegramClient, events, functions

api_id = int(os.environ["api_id"])
api_hash = os.environ["api_hash"]
phone = os.environ["phone"]
source_channel = os.environ["source_channel"]

target_language = "en"
translation_header = "English translation:"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

client = TelegramClient("translation_user_session", api_id, api_hash)
translator = GoogleTranslator(source="auto", target=target_language)

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


async def get_discussion_thread(post_id: int):
    result = await client(
        functions.messages.GetDiscussionMessageRequest(
            peer=source_channel,
            msg_id=post_id,
        )
    )

    discussion_message = result.messages[0]
    discussion_entity = await client.get_input_entity(discussion_message.peer_id)
    return discussion_entity, discussion_message.id


async def send_new_translation(post_id: int, final_text: str):
    discussion_entity, thread_message_id = await get_discussion_thread(post_id)

    sent_ids = []
    for part in split_text(final_text):
        sent = await client.send_message(
            entity=discussion_entity,
            message=part,
            reply_to=thread_message_id,
        )
        sent_ids.append(sent.id)

    translation_map[post_id] = {
        "entity": discussion_entity,
        "thread_message_id": thread_message_id,
        "message_ids": sent_ids,
    }


async def update_existing_translation(post_id: int, final_text: str):
    if post_id not in translation_map:
        await send_new_translation(post_id, final_text)
        return

    saved = translation_map[post_id]
    discussion_entity = saved["entity"]
    thread_message_id = saved["thread_message_id"]
    old_ids = saved["message_ids"]

    new_parts = split_text(final_text)
    new_ids = []

    common_count = min(len(old_ids), len(new_parts))

    for i in range(common_count):
        await client.edit_message(
            entity=discussion_entity,
            message=old_ids[i],
            text=new_parts[i],
        )
        new_ids.append(old_ids[i])

    for i in range(common_count, len(new_parts)):
        sent = await client.send_message(
            entity=discussion_entity,
            message=new_parts[i],
            reply_to=thread_message_id,
        )
        new_ids.append(sent.id)

    if len(old_ids) > len(new_parts):
        extra_ids = old_ids[len(new_parts):]
        await client.delete_messages(discussion_entity, extra_ids)

    translation_map[post_id]["message_ids"] = new_ids


@client.on(events.NewMessage(chats=source_channel))
async def handle_new_post(event):
    try:
        message = event.message
        original_text = clean_text(message.message)

        if not original_text:
            logging.info("Post has no text or caption. Skipping.")
            return

        logging.info("New post detected. Translating...")
        translated_text = translate_text(original_text)
        final_text = f"{translation_header}\n\n{translated_text}"

        await send_new_translation(message.id, final_text)
        logging.info("Translation sent successfully.")

    except Exception as e:
        logging.error(f"Error while handling new post: {e}")


@client.on(events.MessageEdited(chats=source_channel))
async def handle_edited_post(event):
    try:
        message = event.message
        original_text = clean_text(message.message)

        if not original_text:
            logging.info("Edited post has no text or caption. Skipping.")
            return

        logging.info("Edited post detected. Updating translation...")
        translated_text = translate_text(original_text)
        final_text = f"{translation_header}\n\n{translated_text}"

        await update_existing_translation(message.id, final_text)
        logging.info("Translation updated successfully.")

    except Exception as e:
        logging.error(f"Error while handling edited post: {e}")


async def main():
    await client.start(phone=phone)
    logging.info("Userbot is running...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
