import os
import time
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient

# Pyrogram Bot Setup
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))
ADMINS = [int(admin) for admin in os.environ.get("ADMINS", "").split()]  # Add admin user IDs

mongo_client = MongoClient(MONGO_URI)
db = mongo_client["movie_bot"]
collection = db["movies"]
user_collection = db["users"]

pyrogram_app = Client("MovieBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@pyrogram_app.on_message(filters.private & filters.command("start"))
async def start_handler(client, message: Message):
    user_collection.update_one({"_id": message.from_user.id}, {"$set": {"name": message.from_user.first_name}}, upsert=True)
    await message.reply_text("হ্যালো! আমি মুভি লিংক সার্চ বট!\n\nমুভির নাম লিখো, আমি খুঁজে এনে দিব!")

@pyrogram_app.on_message(filters.command("help") & filters.private)
async def help_command(client, message: Message):
    await message.reply_text(
        "**সাহায্য মেনু:**\n\n"
        "/start - বট চালু করুন\n"
        "/help - সাহায্য মেনু দেখুন\n"
        "/about - বট ও ডেভেলপার তথ্য\n"
        "/cancel - চলমান অপারেশন বন্ধ করুন\n\n"
        "**আপনি শুধু মুভির নাম লিখুন, আমি খুঁজে এনে দেবো!**\n"
        "উদাহরণ: Jawan, Pathaan"
    )

@pyrogram_app.on_message(filters.command("about") & filters.private)
async def about_command(client, message: Message):
    await message.reply_text(
        "**বট পরিচিতি:**\n\n"
        "➤ নাম: Movie Link Search Bot\n"
        "➤ ভার্সন: 1.0.0\n"
        "➤ ডেভেলপার: [আপনার নাম বা ইউজারনেম]\n"
        "➤ সাপোর্ট: @YourSupportGroup"
    )

@pyrogram_app.on_message(filters.command("cancel") & filters.private)
async def cancel_command(client, message: Message):
    await message.reply_text("আপনার অনুরোধ বাতিল করা হয়েছে। নতুন করে কিছু সার্চ করতে পারেন।")

@pyrogram_app.on_message(filters.command("ping") & filters.user(ADMINS))
async def ping_handler(client, message: Message):
    start = time.time()
    m = await message.reply("Pinging...")
    end = time.time()
    await m.edit(f"Pong! `{round((end - start) * 1000)} ms`")

@pyrogram_app.on_message(filters.command("status") & filters.user(ADMINS))
async def status_handler(client, message: Message):
    movie_count = collection.count_documents({})
    user_count = user_collection.count_documents({})
    await message.reply_text(
        f"**বট স্ট্যাটাস:**\n\n"
        f"• মোট মুভি সেভড: `{movie_count}`\n"
        f"• মোট ইউজার: `{user_count}`"
    )

@pyrogram_app.on_message(filters.text & filters.private & ~filters.command("start"))
async def search_movie(client, message: Message):
    query = message.text.strip()
    result = collection.find_one({"text": {"$regex": f"^{query}$", "$options": "i"}})
    
    if result:
        try:
            sent = await pyrogram_app.forward_messages(
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

@pyrogram_app.on_callback_query(filters.regex("^id_"))
async def suggestion_click(client, callback_query: CallbackQuery):
    message_id = int(callback_query.data.replace("id_", ""))
    result = collection.find_one({"message_id": message_id})
    
    if result:
        try:
            sent = await pyrogram_app.forward_messages(
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

@pyrogram_app.on_message(filters.channel)
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

if __name__ == "__main__":
    pyrogram_app.run()
