import os
import asyncio
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from rapidfuzz import process

# Health check server for Koyeb
def start_web():
    server = HTTPServer(("0.0.0.0", 8000), SimpleHTTPRequestHandler)
    print("Web server running on port 8000")
    server.serve_forever()

threading.Thread(target=start_web).start()

# Env variables
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))
ADMINS = [int(x) for x in os.environ.get("ADMINS", "").split()]

# Mongo
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["movie_bot"]
collection = db["movies"]
user_collection = db["users"]

# Pyrogram bot
pyrogram_app = Client("MovieBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# /start
@pyrogram_app.on_message(filters.private & filters.command("start"))
async def start_handler(client, message: Message):
    user_collection.update_one({"user_id": message.from_user.id}, {"$set": {"user_id": message.from_user.id}}, upsert=True)
    await message.reply_photo(
        photo="https://envs.sh/ot1.jpg",
        caption="হ্যালো! আমি মুভি লিংক সার্চ বট!\n\nমুভির নাম লিখো, আমি খুঁজে এনে দিব!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("গ্রুপ", url="https://t.me/Terabox_search_group"),
             InlineKeyboardButton("চ্যানেল", url="https://t.me/HDCineBox")],
            [InlineKeyboardButton("ক্রিয়েটর", url="https://t.me/ctgmovies23"),
             InlineKeyboardButton("এড গ্রুপে", url="https://t.me/yourbot?startgroup=true")]
        ])
    )

# /help
@pyrogram_app.on_message(filters.private & filters.command("help"))
async def help_handler(client, message: Message):
    await message.reply_text("**ব্যবহার নির্দেশনা:**\n\nশুধু মুভির নাম লিখে পাঠান, আমি খুঁজে দেবো!")

# /stats
@pyrogram_app.on_message(filters.private & filters.command("stats") & filters.user(ADMINS))
async def stats_handler(client, message: Message):
    total_movies = collection.count_documents({})
    total_users = user_collection.count_documents({})
    await message.reply_text(f"মোট মুভি: {total_movies}\nমোট ইউজার: {total_users}")

# /delete_all
@pyrogram_app.on_message(filters.private & filters.command("delete_all") & filters.user(ADMINS))
async def delete_all_handler(client, message: Message):
    collection.delete_many({})
    await message.reply_text("সব মুভি ডাটাবেজ থেকে মুছে ফেলা হয়েছে।")

# /broadcast
@pyrogram_app.on_message(filters.private & filters.command("broadcast") & filters.user(ADMINS))
async def broadcast_handler(client, message: Message):
    if not message.reply_to_message:
        return await message.reply_text("ব্রডকাস্ট করতে রিপ্লাই দিন।")

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

# Movie search
@pyrogram_app.on_message(filters.text & (filters.private | filters.group) & ~filters.command(["start", "help", "stats", "delete_all", "broadcast"]))
async def search_movie(client, message: Message):
    query = message.text.strip().lower()
    all_data = list(collection.find({}, {"text": 1, "message_id": 1}))
    all_titles = [movie["text"].lower() for movie in all_data if "text" in movie]

    matches = process.extract(query, all_titles, limit=2, score_cutoff=70)

    if len(matches) == 1:
        matched_title = matches[0][0]
        result = next((movie for movie in all_data if movie["text"].lower() == matched_title), None)
        if result:
            try:
                sent = await pyrogram_app.forward_messages(
                    chat_id=message.chat.id,
                    from_chat_id=CHANNEL_ID,
                    message_ids=result["message_id"]
                )
                await message.reply_text(
                    f"📂 ফাইল: {result['text']}\n📅 তারিখ: {message.date.strftime('%d %b, %Y')}\n⏰ সময়: {message.date.strftime('%I:%M %p')}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔎 গুগলে সার্চ করুন", url=f"https://www.google.com/search?q={result['text']}")],
                        [InlineKeyboardButton("✴️ CLOSE ✴️", callback_data="close_msg")]
                    ])
                )
                await asyncio.sleep(300)
                await sent.delete()
                return
            except Exception as e:
                await message.reply_text(f"ফরওয়ার্ড করতে সমস্যা: {e}")
                return

    elif len(matches) > 1:
        buttons = []
        for matched_title, _, _ in matches:
            movie = next((m for m in all_data if m["text"].lower() == matched_title), None)
            if movie:
                buttons.append([InlineKeyboardButton(movie["text"][:30], callback_data=f"id_{movie['message_id']}")])
        buttons.append([InlineKeyboardButton("✴️ CLOSE ✴️", callback_data="close_msg")])
        await message.reply("আপনি কি নিচের কোনটি খুঁজছেন?", reply_markup=InlineKeyboardMarkup(buttons))
        return

    await message.reply("দুঃখিত, কিছুই খুঁজে পাইনি!")

# Suggestion callback
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

# Close button
@pyrogram_app.on_callback_query(filters.regex("close_msg"))
async def close_msg(client, callback_query: CallbackQuery):
    await callback_query.message.delete()
    await callback_query.answer()

# Save channel messages
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
            print(f"Saved: {text[:50]}...")

# Run
if __name__ == "__main__":
    pyrogram_app.run()
