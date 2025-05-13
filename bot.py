from pyrogram import Client, filters
from pyrogram.types import Message
import os
from pymongo import MongoClient
import asyncio  # সময় বিলম্বের জন্য

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))  # Example: -1001234567890
DEFAULT_DELETE_TIME = int(os.environ.get("DEFAULT_DELETE_TIME", 300))  # Default 5 mins (300 seconds)

# MongoDB ইনিশিয়ালাইজ
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["movie_bot"]
collection = db["movies"]

app = Client(
    "MongoMovieSearchBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@app.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply_text(
        "স্বাগতম!\n\nএই বট দ্বারা আপনি আমাদের চ্যানেলে পোস্ট করা মুভিগুলোর নাম সার্চ করে সরাসরি লিংক পেতে পারেন।\n\nযেকোনো মুভির নাম লিখুন আর দেখুন ম্যাজিক!"
    )

@app.on_message(filters.channel)
async def index_channel_message(client, message: Message):
    if message.chat.id == CHANNEL_ID:
        text = message.text or message.caption
        if text:
            data = {
                "text": text,
                "message_id": message.id
            }
            collection.insert_one(data)
            print(f"Saved: {text[:30]}...")

@app.on_message(filters.text & ~filters.command("start"))
async def search_movie(client, message: Message):
    query = message.text.strip()
    results = collection.find({"text": {"$regex": query, "$options": "i"}}).limit(5)

    found = False
    for result in results:
        found = True
        try:
            sent = await app.forward_messages(
                chat_id=message.chat.id,
                from_chat_id=CHANNEL_ID,
                message_ids=result["message_id"]
            )
            # ৫ মিনিট (ডিফল্ট) পর অটো ডিলিট করবে
            delete_time = DEFAULT_DELETE_TIME  # Default time in seconds
            if len(message.text.split()) > 1:
                # যদি ইউজার কাস্টম টাইম দিতে চায়
                try:
                    custom_time = int(message.text.split()[1])
                    delete_time = custom_time if custom_time > 0 else DEFAULT_DELETE_TIME
                except ValueError:
                    pass

            await asyncio.sleep(delete_time)
            await sent.delete()
        except Exception as e:
            await message.reply_text(f"ফরওয়ার্ড করতে সমস্যা: {e}")

    if not found:
        await message.reply_text("দুঃখিত, কিছুই খুঁজে পাইনি!")

@app.on_message(filters.command("deleteall"))
async def delete_all_messages(client, message: Message):
    if message.chat.id == CHANNEL_ID:
        async for msg in app.get_chat_history(message.chat.id):
            try:
                await msg.delete()
            except Exception as e:
                print(f"Error deleting message: {e}")
        await message.reply_text("সব মেসেজ ডিলিট করা হয়েছে!")

app.run()
