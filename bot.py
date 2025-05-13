from pyrogram import Client, filters
from pyrogram.types import Message
import os
from pymongo import MongoClient

# Load environment variables safely
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME").replace("@", "")  # Remove @ if given

# MongoDB connection
if not MONGO_URI:
    raise Exception("MONGO_URI is not set. Please set it in your environment.")

mongo_client = MongoClient(MONGO_URI)
db = mongo_client["movie_bot"]
collection = db["movies"]

# Initialize bot client
app = Client(
    "MongoMovieSearchBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# /start command handler
@app.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply_text(
        "হ্যালো! আমি লিংক সার্চ বট!\n\nচ্যানেলে মুভির নাম সহ লিংক পোস্ট করো, আর সার্চ করলেই আমি সেটা খুঁজে এনে দিব!"
    )

# Channel message indexer
@app.on_message(filters.channel)
async def index_channel_message(client, message: Message):
    try:
        if message.chat.username and message.chat.username.lower() == CHANNEL_USERNAME.lower():
            text = message.text or message.caption
            if text:
                data = {
                    "text": text,
                    "message_id": message.id
                }
                collection.update_one({"message_id": message.id}, {"$set": data}, upsert=True)
                print(f"Saved: {text[:30]}...")
    except Exception as e:
        print(f"Indexing error: {e}")

# Text message search
@app.on_message(filters.text & ~filters.command("start"))
async def search_movie(client, message: Message):
    query = message.text.strip()
    results = collection.find({"text": {"$regex": query, "$options": "i"}}).limit(5)

    found = False
    for result in results:
        found = True
        try:
            await app.forward_messages(
                chat_id=message.chat.id,
                from_chat_id=f"@{CHANNEL_USERNAME}",
                message_ids=result["message_id"]
            )
        except Exception as e:
            await message.reply_text(f"ফরওয়ার্ড করতে সমস্যা: {e}")

    if not found:
        await message.reply_text("দুঃখিত, কিছুই খুঁজে পাইনি!")

# Start the bot
app.run()
