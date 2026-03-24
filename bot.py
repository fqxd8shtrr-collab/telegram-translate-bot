import asyncio
import logging
from telethon import TelegramClient, events
from deep_translator import GoogleTranslator

# =========================
‎# بياناتك
# =========================
api_id = 221419
api_hash = "2817e3392d4265a68c095dda41cad0"
bot_token = "8682456304:AAErlWXnoqB2suIiSJebrI-58qu424ohF"

‎# يوزر القناة مثال: "A"
‎# أو يمكن استخدام chat id إذا تعرفه
source_channel = "Alfaq"

# ID مجموعة النقاش المرتبطة بالقناة
discussion_group_id = -1002645

‎# اللغة الهدف
target_language = "en"

‎# عنوان ثابت أعلى الترجمة
translation_header = "English translation:"

# =========================
‎# إعدادات السجل
# =========================
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

client = TelegramClient("translation_bot_session", api_id, api_hash)

translator = GoogleTranslator(source="auto", target=target_language)


def split_text(text: str, max_length: int = 4000):
    """
‎    تقسيم النص الطويل إلى أجزاء مناسبة لتيليغرام
    """
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


def clean_text(text: str) -> str:
    """
‎    تنظيف بسيط للنص
    """
    if not text:
        return ""
    return text.strip()


def translate_text(text: str) -> str:
    """
‎    ترجمة النص
    """
    return translator.translate(text)


@client.on(events.NewMessage(chats=source_channel))
async def handle_new_post(event):
    """
‎    التقاط أي منشور جديد من القناة
    """
    try:
        message = event.message

‎        # النص الموجود في المنشور أو الكابشن
        original_text = clean_text(message.message)

‎        # إذا لا يوجد نص، لا نفعل شيئًا
        if not original_text:
            logging.info("Post has no text/caption. Skipping.")
            return

        logging.info("New post detected. Translating...")

        translated_text = translate_text(original_text)

        final_text = f"{translation_header}\n\n{translated_text}"

‎        # إذا كانت الرسالة طويلة جدًا
        parts = split_text(final_text)

        for part in parts:
            await client.send_message(
                entity=discussion_group_id,
                message=part
            )

        logging.info("Translation sent successfully.")

    except Exception as e:
        logging.error(f"Error while handling post: {e}")


async def main():
    await client.start(bot_token=bot_token)
    logging.info("Bot is running...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
