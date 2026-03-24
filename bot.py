import asyncio
import logging
import os
import re
from typing import Dict, List

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

# نخزن رسائل الترجمة الخاصة بكل منشور داخل مجموعة النقاش
translation_map: Dict[str, Dict[str, List[int] | int]] = {}


def clean_text(text: str | None) -> str:
    return text.strip() if text else ""


def split_text(text: str, max_length: int = 4000) -> List[str]:
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


def detect_language(text: str) -> str:
    # حروف فارسية خاصة
    if re.search(r"[گچپژکەیێۆڕڵڤ]", text):
        return "fa"

    # عربي/فارسي عام
    if re.search(r"[\u0600-\u06FF]", text):
        # مؤشرات أقرب للفارسية
        fa_markers = [
            " از ", " در ", " با ", " برای ", " که ", " این ", " آن ",
            "می", "ها", "شود", "کرد", "آتش", "خودرو"
        ]
        score = sum(marker in text for marker in fa_markers)
        return "fa" if score >= 2 else "ar"

    return "en"


def get_target_languages(source_lang: str) -> List[str]:
    if source_lang == "ar":
        return ["en", "fa"]
    if source_lang == "en":
        return ["ar", "fa"]
    if source_lang == "fa":
        return ["ar", "en"]
    return ["en", "fa"]


def translate_text(text: str, target_lang: str) -> str:
    return GoogleTranslator(source="auto", target=target_lang).translate(text)


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

    # بعض النسخ المرتبطة قد لا تُظهر الاسم بشكل ثابت
    # وجود forward/replies من قناة داخل مجموعة النقاش غالبًا يعني أنها نسخة المنشور
    if getattr(message, "post", False):
        return True

    return False


def make_post_key(message) -> str:
    return f"{message.chat_id}:{message.id}"


async def send_parts(reply_to_id: int, text: str) -> List[int]:
    sent_ids: List[int] = []

    for part in split_text(text):
        sent = await client.send_message(
            entity=discussion_group_id,
            message=part,
            reply_to=reply_to_id,
        )
        sent_ids.append(sent.id)

    return sent_ids


async def update_parts(reply_to_id: int, old_ids: List[int], new_text: str) -> List[int]:
    new_parts = split_text(new_text)
    new_ids: List[int] = []

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
        extra_ids = old_ids[len(new_parts):]
        await client.delete_messages(discussion_group_id, extra_ids)

    return new_ids


async def send_translation_pair(post_key: str, group_message_id: int, source_text: str) -> None:
    source_lang = detect_language(source_text)
    targets = get_target_languages(source_lang)

    first_text = translate_text(source_text, targets[0])
    second_text = translate_text(source_text, targets[1])

    first_ids = await send_parts(group_message_id, first_text)
    second_ids = await send_parts(group_message_id, second_text)

    translation_map[post_key] = {
        "reply_to": group_message_id,
        "first_ids": first_ids,
        "second_ids": second_ids,
        "targets": targets,
    }


async def update_translation_pair(post_key: str, source_text: str) -> None:
    if post_key not in translation_map:
        return

    saved = translation_map[post_key]
    reply_to_id = int(saved["reply_to"])
    old_first_ids = list(saved["first_ids"])
    old_second_ids = list(saved["second_ids"])

    source_lang = detect_language(source_text)
    targets = get_target_languages(source_lang)

    first_text = translate_text(source_text, targets[0])
    second_text = translate_text(source_text, targets[1])

    new_first_ids = await update_parts(reply_to_id, old_first_ids, first_text)
    new_second_ids = await update_parts(reply_to_id, old_second_ids, second_text)

    translation_map[post_key] = {
        "reply_to": reply_to_id,
        "first_ids": new_first_ids,
        "second_ids": new_second_ids,
        "targets": targets,
    }


@client.on(events.NewMessage(chats=discussion_group_id))
async def handle_new_discussion_message(event) -> None:
    try:
        msg = event.message

        if not is_channel_post_in_discussion(msg):
            return

        text = clean_text(msg.message)
        if not text:
            logging.info("No text/caption in linked post. Skipping.")
            return

        post_key = make_post_key(msg)

        # منع التكرار إذا وصل نفس الحدث أكثر من مرة
        if post_key in translation_map:
            return

        logging.info("New linked post detected. Sending translations...")
        await send_translation_pair(post_key, msg.id, text)
        logging.info("Translations sent successfully.")

    except Exception as e:
        logging.error(f"Error while handling new discussion message: {e}")


@client.on(events.MessageEdited(chats=discussion_group_id))
async def handle_edited_discussion_message(event) -> None:
    try:
        msg = event.message

        if not is_channel_post_in_discussion(msg):
            return

        text = clean_text(msg.message)
        if not text:
            return

        post_key = make_post_key(msg)

        # إذا لم يكن عندنا سجل سابق، نتجاهله أو نرسله كجديد
        if post_key not in translation_map:
            logging.info("Edited post not found in memory. Sending fresh translations...")
            await send_translation_pair(post_key, msg.id, text)
            return

        logging.info("Edited linked post detected. Updating translations...")
        await update_translation_pair(post_key, text)
        logging.info("Translations updated successfully.")

    except Exception as e:
        logging.error(f"Error while handling edited discussion message: {e}")


async def main() -> None:
    await client.start(bot_token=bot_token)
    logging.info("Bot running...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
