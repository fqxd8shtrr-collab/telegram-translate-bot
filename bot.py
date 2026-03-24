import asyncio
import logging
import os

from deep_translator import GoogleTranslator
from openai import OpenAI
from telethon import TelegramClient, events

api_id = int(os.environ["api_id"])
api_hash = os.environ["api_hash"]
bot_token = os.environ["bot_token"]
source_channel = os.environ["source_channel"].lstrip("@").lower()
discussion_group_id = int(os.environ["discussion_group_id"])

openai_api_key = os.environ["OPENAI_API_KEY"]
openai_model = os.environ.get("OPENAI_MODEL", "gpt-5")

client = TelegramClient("translation_bot_session", api_id, api_hash)
translator_en = GoogleTranslator(source="auto", target="en")
translator_fa = GoogleTranslator(source="auto", target="fa")
ai_client = OpenAI(api_key=openai_api_key)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# نخزن رسائل الترجمة حتى نعدلها إذا تم تعديل المنشور
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


def is_channel_post_in_discussion(message) -> bool:
    sender = getattr(message, "sender", None)
    sender_id = getattr(message, "sender_id", None)

    if sender_id is None:
        return False

    if sender and getattr(sender, "username", None):
        if sender.username.lstrip("@").lower() == source_channel:
            return True

    if sender and getattr(sender, "title", None):
        if sender.title.strip().lower() == source_channel:
            return True

    return False


def ai_rewrite_text(text: str) -> str:
    response = ai_client.responses.create(
        model=openai_model,
        input=[
            {
                "role": "system",
                "content": (
                    "أعد صياغة النص العربي بأسلوب إخباري قوي ومرتب ومختصر. "
                    "حافظ على المعنى الكامل، بدون مبالغة زائدة، وبدون عناوين، وبدون شرح إضافي. "
                    "أعد النص النهائي فقط."
                ),
            },
            {
                "role": "user",
                "content": text,
            },
        ],
    )
    return response.output_text.strip()


def translate_en(text: str) -> str:
    return translator_en.translate(text)


def translate_fa(text: str) -> str:
    return translator_fa.translate(text)


async def send_translation_pair(group_message_id: int, post_key: str, base_text: str):
    en_text = translate_en(base_text)
    fa_text = translate_fa(base_text)

    sent_en_ids = []
    sent_fa_ids = []

    for part in split_text(en_text):
        sent = await client.send_message(
            entity=discussion_group_id,
            message=part,
            reply_to=group_message_id,
        )
        sent_en_ids.append(sent.id)

    for part in split_text(fa_text):
        sent = await client.send_message(
            entity=discussion_group_id,
            message=part,
            reply_to=group_message_id,
        )
        sent_fa_ids.append(sent.id)

    translation_map[post_key] = {
        "reply_to": group_message_id,
        "en_ids": sent_en_ids,
        "fa_ids": sent_fa_ids,
    }


async def update_message_parts(entity, old_ids, reply_to_id, new_text):
    new_parts = split_text(new_text)
    new_ids = []

    common = min(len(old_ids), len(new_parts))

    for i in range(common):
        await client.edit_message(
            entity=entity,
            message=old_ids[i],
            text=new_parts[i],
        )
        new_ids.append(old_ids[i])

    for i in range(common, len(new_parts)):
        sent = await client.send_message(
            entity=entity,
            message=new_parts[i],
            reply_to=reply_to_id,
        )
        new_ids.append(sent.id)

    if len(old_ids) > len(new_parts):
        await client.delete_messages(entity, old_ids[len(new_parts):])

    return new_ids


async def update_translation_pair(post_key: str, base_text: str):
    if post_key not in translation_map:
        return

    saved = translation_map[post_key]
    reply_to_id = saved["reply_to"]

    en_text = translate_en(base_text)
    fa_text = translate_fa(base_text)

    new_en_ids = await update_message_parts(
        discussion_group_id,
        saved["en_ids"],
        reply_to_id,
        en_text,
    )

    new_fa_ids = await update_message_parts(
        discussion_group_id,
        saved["fa_ids"],
        reply_to_id,
        fa_text,
    )

    translation_map[post_key]["en_ids"] = new_en_ids
    translation_map[post_key]["fa_ids"] = new_fa_ids


def make_post_key(message):
    return f"{message.chat_id}:{message.id}"


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

        logging.info("Linked channel post detected. Rewriting...")
        rewritten_text = ai_rewrite_text(text)

        post_key = make_post_key(msg)
        await send_translation_pair(msg.id, post_key, rewritten_text)

        logging.info("English and Persian translations sent successfully.")

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

        post_key = make_post_key(msg)

        if post_key not in translation_map:
            return

        logging.info("Edited linked post detected. Rewriting...")
        rewritten_text = ai_rewrite_text(text)

        await update_translation_pair(post_key, rewritten_text)

        logging.info("English and Persian translations updated successfully.")

    except Exception as e:
        logging.error(f"Error while handling edited discussion message: {e}")


async def main():
    await client.start(bot_token=bot_token)
    logging.info("Bot running...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
