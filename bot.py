import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
CHANNEL_ID = os.environ.get("CHANNEL_ID")  # "-100xxxxxxxxxx"

mongo_client = MongoClient(MONGO_URI)
db = mongo_client["movie_bot"]
collection = db["movies"]

app = Client(
    "MovieBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@app.on_message(filters.private & filters.command("start"))
async def start_handler(client, message: Message):
    await message.reply_text("হ্যালো! মুভির নাম লিখে আমাকে পাঠাও, আমি খুঁজে এনে দিব!")

@app.on_message(filters.text & filters.private & ~filters.command("start"))
async def search_movie(client, message: Message):
    query = message.text.strip()
    result = collection.find_one({"text": {"$eq": query}})
    if result:
        try:
            sent = await app.forward_messages(
                chat_id=message.chat.id,
                from_chat_id=int(CHANNEL_ID),
                message_ids=result["message_id"]
            )
            await asyncio.sleep(300)
            await sent.delete()
        except Exception as e:
            await message.reply_text(f"ফরওয়ার্ড করতে সমস্যা: {e}")
    else:
        # আংশিক মিল আছে এমন মুভির নাম সাজেস্ট করি
        suggestions = collection.find({"text": {"$regex": query, "$options": "i"}}).limit(5)
        buttons = []
        for movie in suggestions:
            buttons.append([InlineKeyboardButton(movie["text"], callback_data=f"suggest_{movie['text']}")])
        if buttons:
            await message.reply("আপনি কি এইগুলোর কোনটা খুঁজছেন?", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await message.reply("দুঃখিত, কিছুই খুঁজে পাইনি!")

@app.on_callback_query(filters.regex("^suggest_"))
async def suggestion_click(client, callback_query: CallbackQuery):
    movie_name = callback_query.data.replace("suggest_", "")
    result = collection.find_one({"text": {"$eq": movie_name}})
    if result:
        try:
            sent = await app.forward_messages(
                chat_id=callback_query.message.chat.id,
                from_chat_id=int(CHANNEL_ID),
                message_ids=result["message_id"]
            )
            await callback_query.answer()
            await asyncio.sleep(300)
            await sent.delete()
        except Exception as e:
            await callback_query.message.reply_text(f"ফরওয়ার্ড করতে সমস্যা: {e}")
    else:
        await callback_query.message.reply_text("মুভিটি খুঁজে পাওয়া যায়নি!")

app.run()
