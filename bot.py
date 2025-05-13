from pyrogram import Client, filters
from pyrogram.types import Message
import os

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME")  # without @

app = Client(
    "MovieSearchBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@app.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply_text(
        "হ্যালো! আমি অটো মুভি সার্চ বট।\n\nযেকোনো মুভির নাম লিখো, আমি তোমার জন্য খুঁজে আনবো!"
    )

@app.on_message(filters.text & ~filters.command("start"))
async def search_movie(client, message: Message):
    query = message.text.strip()
    results = []

    async for msg in app.search_messages(CHANNEL_USERNAME, query=query, limit=5):
        results.append(msg)

    if not results:
        await message.reply_text("দুঃখিত! কিছুই খুঁজে পাইনি।")
    else:
        for msg in results:
            await msg.copy(chat_id=message.chat.id)

app.run()
