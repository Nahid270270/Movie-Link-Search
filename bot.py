import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient

# API_KEY এবং MongoDB URI গুলি পরিবেশে সেট করা থাকতে হবে
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))  # যেমন -1001234567890

# MongoDB সেটআপ
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["movie_bot"]
collection = db["movies"]

# Pyrogram বট সেটআপ
app = Client(
    "MovieBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# স্টার্ট কমান্ডে বটের রেসপন্স
@app.on_message(filters.private & filters.command("start"))
async def start_handler(client, message: Message):
    await message.reply_text(
        "হ্যালো! আমি মুভি লিংক সার্চ বট!\n\nমুভির নাম লিখো, আমি খুঁজে এনে দিব!",
    )

# মুভি সার্চ করার কমান্ড
@app.on_message(filters.text & filters.private & ~filters.command("start"))
async def search_movie(client, message: Message):
    query = message.text.strip()
    # এক্স্যাক্ট মাচের জন্য
    result = collection.find_one({"text": {"$regex": f"^{query}$", "$options": "i"}})
    
    if result:
        try:
            # ফরওয়ার্ড মেসেজ
            sent = await app.forward_messages(
                chat_id=message.chat.id,
                from_chat_id=CHANNEL_ID,
                message_ids=result["message_id"]
            )
            # ৫ মিনিট পর মেসেজ ডিলিট
            await asyncio.sleep(300)
            await sent.delete()
        except Exception as e:
            await message.reply_text(f"ফরওয়ার্ড করতে সমস্যা: {e}")
    else:
        # যদি এক্স্যাক্ট ম্যাচ না পাওয়া যায় তবে রিলেটেড মুভির সার্চ
        suggestions = collection.find({"text": {"$regex": query, "$options": "i"}}).limit(5)
        buttons = []
        for movie in suggestions:
            buttons.append([
                InlineKeyboardButton(
                    movie["text"][:30],  # মুভির নাম
                    callback_data=f"id_{movie['message_id']}"  # বাটনের ডাটা হিসেবে মেসেজ আইডি
                )
            ])
        if buttons:
            # ইউজারকে সিলেক্ট করার জন্য বাটন দেখানো
            await message.reply(
                "আপনি কি নিচের কোনটি খুঁজছেন?",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        else:
            await message.reply("দুঃখিত, কিছুই খুঁজে পাইনি!")

# কাস্টম বাটন ক্লিক করার কমান্ড
@app.on_callback_query(filters.regex("^id_"))
async def suggestion_click(client, callback_query: CallbackQuery):
    message_id = int(callback_query.data.replace("id_", ""))
    result = collection.find_one({"message_id": message_id})
    
    if result:
        try:
            # ফরওয়ার্ড মেসেজ
            sent = await app.forward_messages(
                chat_id=callback_query.message.chat.id,
                from_chat_id=CHANNEL_ID,
                message_ids=message_id
            )
            await callback_query.answer()
            # ৫ মিনিট পর মেসেজ ডিলিট
            await asyncio.sleep(300)
            await sent.delete()
        except Exception as e:
            await callback_query.message.reply_text(f"ফরওয়ার্ড করতে সমস্যা: {e}")
    else:
        await callback_query.message.reply_text("মুভিটি খুঁজে পাওয়া যায়নি!")

# চ্যানেল থেকে মেসেজ সংগ্রহ করা এবং MongoDB তে সেভ করা
@app.on_message(filters.channel)
async def save_channel_messages(client, message: Message):
    if message.chat.id == CHANNEL_ID:
        text = message.text or message.caption
        if text:
            # মেসেজ আইডি সহ MongoDB তে সেভ করা
            collection.update_one(
                {"message_id": message.id},
                {"$set": {"text": text, "message_id": message.id}},
                upsert=True
            )
            print(f"Saved: {text[:40]}...")

# বট চালানো
app.run()
