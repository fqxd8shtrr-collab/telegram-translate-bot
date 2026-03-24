import asyncio
import logging
import os

from deep_translator import GoogleTranslator
from telethon import TelegramClient, events

api_id = int(os.environ["api_id"])
api_hash = os.environ["api_hash"]
bot_token = os.environ["bot_token"]
source_channel = os.environ["source_channel"]

target_language = "en"
translation_header = "English translation:"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

client = TelegramClient("translation_bot_session", api_id, api_hash)
translator = GoogleTranslator(source="auto", target=target_language)


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

        for part in split_text(final_text):
            await client.send_message(
                entity=source_channel,
                message=part,
                comment_to=message.id,
            )

        logging.info("Translation sent successfully in post discussion.")

    except Exception as e:
        logging.error(f"Error while handling post: {e}")


async def main() -> None:
    await client.start(bot_token=bot_token)
    logging.info("Bot is running...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
