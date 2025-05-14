import os
import asyncio
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient

# Start a simple web server for Koyeb health check
def start_web():
    server = HTTPServer(("0.0.0.0", 8000), SimpleHTTPRequestHandler)
    print("Web server running on port 8000")
    server.serve_forever()

threading.Thread(target=start_web).start()

# Pyrogram Bot Setup
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))
ADMINS = [int(x) for x in os.environ.get("ADMINS", "").split()]

mongo_client = MongoClient(MONGO_URI)
db = mongo_client["movie_bot"]
collection = db["movies"]
user_collection = db["users"]

pyrogram_app = Client("MovieBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# /start command handler
@pyrogram_app.on_message(filters.command("start"))
async def start_handler(client, message: Message):
    user_collection.update_one(
        {"user_id": message.from_user.id},
        {"$set": {"user_id": message.from_user.id}},
        upsert=True
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{client.me.username}?startgroup=true")],
        [InlineKeyboardButton("🔄 Update Channel", url="https://t.me/HDCineBox")]  # <-- এখানে চ্যানেলের ইউজারনেম বসাও
    ])

    await message.reply_text(
        "হ্যালো! আমি মুভি লিংক সার্চ বট!\n\nমুভির নাম লিখো, আমি খুঁজে এনে দিব!",
        reply_markup=buttons
    )

# /help command handler
@pyrogram_app.on_message(filters.private & filters.command("help"))
async def help_handler(client, message: Message):
    await message.reply_text("**ব্যবহার নির্দেশনা:**\n\nশুধু মুভির নাম লিখে পাঠান, আমি খুঁজে দেবো!\n\nআপনি যদি কিছু না পান, তাহলে অনুরূপ কিছু সাজেস্ট করা হবে।")

# /stats command handler for admins
@pyrogram_app.on_message(filters.private & filters.command("stats") & filters.user(ADMINS))
async def stats_handler(client, message: Message):
    total_movies = collection.count_documents({})
    total_users = user_collection.count_documents({})
    await message.reply_text(f"মোট মুভি: {total_movies}\nমোট ইউজার: {total_users}")

# /delete_all command handler for admins
@pyrogram_app.on_message(filters.private & filters.command("delete_all") & filters.user(ADMINS))
async def delete_all_handler(client, message: Message):
    collection.delete_many({})
    await message.reply_text("সব মুভি ডাটাবেজ থেকে মুছে ফেলা হয়েছে।")

# /broadcast command handler for admins
@pyrogram_app.on_message(filters.private & filters.command("broadcast") & filters.user(ADMINS))
async def broadcast_handler(client, message: Message):
    if not message.reply_to_message:
        return await message.reply_text("ব্রডকাস্ট করার জন্য কোনো মেসেজে রিপ্লাই দিন।")

    users = user_collection.find()
    success = 0
    failed = 0

    for user in users:
        try:
            await message.reply_to_message.copy(chat_id=user["user_id"])
            success += 1
        except:
            failed += 1

    await message.reply_text(f"✅ সফল: {success}\n❌ ব্যর্থ: {failed}")

# Movie search handler
@pyrogram_app.on_message(filters.text & ~filters.command(["start", "help", "stats", "delete_all", "broadcast"]))
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

# Callback query handler for movie suggestions
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

# Save movie messages from channel to MongoDB
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

# Run the bot
if __name__ == "__main__":
    pyrogram_app.run()
