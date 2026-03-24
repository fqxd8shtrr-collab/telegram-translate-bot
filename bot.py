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
update_header = "Updated translation:"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

client = TelegramClient("translation_bot_session", api_id, api_hash)
translator = GoogleTranslator(source="auto", target=target_language)

translation_map = {}


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


async def send_translation(group_message_id, post_key, final_text):
    sent_ids = []

    for part in split_text(final_text):
        sent = await client.send_message(
            entity=discussion_group_id,
            message=part,
            reply_to=group_message_id,
        )
        sent_ids.append(sent.id)

    translation_map[post_key] = {
        "reply_to": group_message_id,
        "message_ids": sent_ids,
    }


async def update_translation(post_key, final_text):
    if post_key not in translation_map:
        return

    saved = translation_map[post_key]
    old_ids = saved["message_ids"]
    reply_to_id = saved["reply_to"]

    new_parts = split_text(final_text)
    new_ids = []

    common = min(len(old_ids), len(new_parts))

    for i in range(common):
        await client.edit_message(
            entity=discussion_group_id,
            message=old_ids[i],
            text=new_parts[i],
        )
        new_ids.append(old_ids[i])

    for i in range(common, len(new_parts)):
        sent = await client.send_message(
            entity=discussion_group_id,
            message=new_parts[i],
            reply_to=reply_to_id,
        )
        new_ids.append(sent.id)

    if len(old_ids) > len(new_parts):
        await client.delete_messages(
            discussion_group_id,
            old_ids[len(new_parts):]
        )

    translation_map[post_key]["message_ids"] = new_ids


def make_post_key(message):
    return f"{message.chat_id}:{message.id}"


def is_channel_post_in_discussion(message):
    sender = getattr(message, "sender", None)
    sender_id = getattr(message, "sender_id", None)

    if sender_id is None:
        return False

    source_clean = source_channel.lstrip("@").lower()

    if sender and getattr(sender, "username", None):
        if sender.username.lower() == source_clean:
            return True

    if sender and getattr(sender, "title", None):
        if sender.title.lower() == source_clean:
            return True

    return False


@client.on(events.NewMessage(chats=discussion_group_id))
async def handle_new_discussion_message(event):
    try:
        msg = event.message

        if not is_channel_post_in_discussion(msg):
            return

        text = clean_text(msg.message)
        if not text:
            logging.info("No text/caption in linked post. Skipping.")
            return

        logging.info("Discussion copy of channel post detected. Translating...")
        translated = translate_text(text)
        final_text = f"{translation_header}\n\n{translated}"

        post_key = make_post_key(msg)
        await send_translation(msg.id, post_key, final_text)

        logging.info("Translation sent successfully as reply.")

    except Exception as e:
        logging.error(f"Error while handling new discussion message: {e}")


@client.on(events.MessageEdited(chats=discussion_group_id))
async def handle_edited_discussion_message(event):
    try:
        msg = event.message

        if not is_channel_post_in_discussion(msg):
            return

        text = clean_text(msg.message)
        if not text:
            return

        logging.info("Edited linked post detected. Updating translation...")
        translated = translate_text(text)
        final_text = f"{update_header}\n\n{translated}"

        post_key = make_post_key(msg)
        await update_translation(post_key, final_text)

        logging.info("Translation updated successfully.")

    except Exception as e:
        logging.error(f"Error while handling edited discussion message: {e}")


async def main():
    await client.start(bot_token=bot_token)
    logging.info("Bot running...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
