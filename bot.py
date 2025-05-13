import os
import time
import asyncio
import threading
from fastapi import FastAPI
import uvicorn
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient

# টাইম ঠিক করার জন্য
time.sleep(5)
os.environ['TZ'] = 'UTC'
time.tzset()

# ENV variables
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))

# MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["movie_bot"]
collection = db["movies"]

# Pyrogram client
app = Client("MovieBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# FastAPI
api = FastAPI()

@app.on_message(filters.private & filters.command("start"))
async def start_handler(client, message: Message):
    await message.reply_text("হ্যালো! আমি মুভি লিংক সার্চ বট!\n\nমুভির নাম লিখো, আমি খুঁজে এনে দিব!")

@app.on_message(filters.text & filters.private & ~filters.command("start"))
async def search_movie(client, message: Message):
    query = message.text.strip()
    result = collection.find_one({"text": {"$regex": f"^{query}$", "$options": "i"}})
    
    if result:
        try:
            sent = await app.forward_messages(
                chat_id=message.chat.id,
                from_chat_id=CHANNEL_ID,
                message_ids=result["message_id"]
            )
            await asyncio.sleep(300)
            await sent.delete()
        except Exception as e:
            await message.reply_text(f"ফরওয়ার্ড করতে সমস্যা: {e}")
    else:
        suggestions = collection.find({"text": {"$regex": query, "$options": "i"}}).limit(5)
        buttons = [
            [InlineKeyboardButton(movie["text"][:30], callback_data=f"id_{movie['message_id']}")]
            for movie in suggestions
        ]
        if buttons:
            await message.reply("আপনি কি নিচের কোনটি খুঁজছেন?", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await message.reply("দুঃখিত, কিছুই খুঁজে পাইনি!")

@app.on_callback_query(filters.regex("^id_"))
async def suggestion_click(client, callback_query: CallbackQuery):
    message_id = int(callback_query.data.replace("id_", ""))
    result = collection.find_one({"message_id": message_id})
    
    if result:
        try:
            sent = await app.forward_messages(
                chat_id=callback_query.message.chat.id,
                from_chat_id=CHANNEL_ID,
                message_ids=message_id
            )
            await callback_query.answer()
            await asyncio.sleep(300)
            await sent.delete()
        except Exception as e:
            await callback_query.message.reply_text(f"ফরওয়ার্ড করতে সমস্যা: {e}")
    else:
        await callback_query.message.reply_text("মুভিটি খুঁজে পাওয়া যায়নি!")

@app.on_message(filters.channel)
async def save_channel_messages(client, message: Message):
    if message.chat.id == CHANNEL_ID:
        text = message.text or message.caption
        if text:
            collection.update_one(
                {"message_id": message.id},
                {"$set": {"text": text, "message_id": message.id}},
                upsert=True
            )
            print(f"Saved: {text[:40]}...")

# Pyrogram বট চালু করার জন্য আলাদা থ্রেড
def start_bot():
    app.run()

# FastAPI root path
@api.get("/")
def home():
    return {"message": "Bot is running!"}

# Main
if __name__ == "__main__":
    bot_thread = threading.Thread(target=start_bot)
    bot_thread.start()
    uvicorn.run(api, host="0.0.0.0", port=8000)
