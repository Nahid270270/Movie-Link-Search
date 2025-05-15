import os
import asyncio
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from rapidfuzz import fuzz

# Web server for health check
def start_web():
    server = HTTPServer(("0.0.0.0", 8000), SimpleHTTPRequestHandler)
    print("Web server started on port 8000")
    server.serve_forever()

threading.Thread(target=start_web).start()

# Environment variables
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")  # Pyrogram UserSession string
MONGO_URI = os.getenv("MONGO_URI")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
ADMINS = list(map(int, os.getenv("ADMINS", "").split()))

# MongoDB setup
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["movie_bot"]
movies_col = db["movies"]
users_col = db["users"]
notfound_col = db["not_found"]

# Pyrogram Client with UserSession
app = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

# Start command
@app.on_message(filters.private & filters.command("start"))
async def start_cmd(client, message):
    users_col.update_one({"user_id": message.from_user.id}, {"$set": {"user_id": message.from_user.id}}, upsert=True)
    await message.reply_text(
        "হ্যালো! আমি মুভি সার্চ বট।\n\n"
        "কোনো মুভির নাম লিখে সার্চ করুন, অথবা চ্যানেল থেকে মুভি ফরওয়ার্ড করুন।",
        reply_markup=InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{client.me.username}?startgroup=true"),
                InlineKeyboardButton("📢 Channel", url="https://t.me/YourChannelHere")
            ]]
        )
    )

# Help command
@app.on_message(filters.private & filters.command("help"))
async def help_cmd(client, message):
    await message.reply_text(
        "**ব্যবহার নির্দেশনা:**\n"
        "- মুভির নাম লিখে সার্চ করুন।\n"
        "- অথবা চ্যানেল থেকে মুভি মেসেজ ফরওয়ার্ড করুন।\n"
        "- অ্যাডমিনদের জন্য /stats, /broadcast, /requests কমান্ড আছে।"
    )

# Save forwarded movie from channel
@app.on_message(filters.private & filters.forwarded)
async def save_forwarded(client, message):
    if message.forward_from_chat and message.forward_from_chat.id == CHANNEL_ID:
        text = message.text or message.caption or ""
        if not text:
            await message.reply_text("মুভির টেক্সট পাওয়া যায়নি।")
            return

        movies_col.update_one(
            {"message_id": message.forward_from_message_id},
            {"$set": {"text": text, "message_id": message.forward_from_message_id}},
            upsert=True
        )
        await message.reply_text("মুভি সংরক্ষণ করা হয়েছে! এখন নাম লিখে সার্চ করতে পারেন।")
    else:
        await message.reply_text("অনুগ্রহ করে কেবলমাত্র অনুমোদিত চ্যানেল থেকে ফরওয়ার্ড করুন।")

# Search movie by name
@app.on_message(filters.private & filters.text & ~filters.command(["start", "help", "stats", "broadcast", "requests"]))
async def search_movie(client, message):
    query = message.text.strip().lower()
    movies = list(movies_col.find())
    best_match = None
    best_score = 0

    for movie in movies:
        title = movie.get("text", "").lower()
        score = fuzz.partial_ratio(query, title)
        if score > best_score:
            best_score = score
            best_match = movie

    if best_score >= 90 and best_match:
        try:
            await client.forward_messages(
                chat_id=message.chat.id,
                from_chat_id=CHANNEL_ID,
                message_ids=best_match["message_id"]
            )
        except Exception as e:
            await message.reply_text(f"ফরওয়ার্ড করতে সমস্যা: {e}")
    else:
        # Suggestions
        suggestions = sorted(movies, key=lambda m: fuzz.partial_ratio(query, m.get("text", "").lower()), reverse=True)[:5]
        buttons = [
            [InlineKeyboardButton(m["text"][:30], callback_data=f"id_{m['message_id']}")]
            for m in suggestions if fuzz.partial_ratio(query, m.get("text", "").lower()) > 50
        ]
        if buttons:
            await message.reply("আপনি কি নিচের কোনটি খুঁজছেন?", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            notfound_col.update_one(
                {"query": query},
                {"$addToSet": {"users": message.from_user.id}, "$set": {"query": query}},
                upsert=True
            )
            for admin in ADMINS:
                try:
                    await client.send_message(admin, f"⚠️ ইউজার @{message.from_user.username or message.from_user.id} '{query}' খুঁজে পায়নি।")
                except: pass
            await message.reply(f"দুঃখিত, '{query}' নামে কিছু খুঁজে পাইনি!")

# Callback for suggestion buttons
@app.on_callback_query(filters.regex("^id_"))
async def suggestion_cb(client, callback_query):
    msg_id = int(callback_query.data.split("_")[1])
    movie = movies_col.find_one({"message_id": msg_id})
    if movie:
        try:
            await client.forward_messages(
                chat_id=callback_query.message.chat.id,
                from_chat_id=CHANNEL_ID,
                message_ids=msg_id
            )
            await callback_query.answer()
        except Exception as e:
            await callback_query.message.reply_text(f"ফরওয়ার্ড করতে সমস্যা: {e}")
    else:
        await callback_query.message.reply_text("মুভিটি খুঁজে পাওয়া যায়নি!")

# Admin commands: stats, broadcast, requests
@app.on_message(filters.private & filters.command("stats") & filters.user(ADMINS))
async def stats_cmd(client, message):
    total_movies = movies_col.count_documents({})
    total_users = users_col.count_documents({})
    await message.reply_text(f"মোট মুভি: {total_movies}\nমোট ইউজার: {total_users}")

@app.on_message(filters.private & filters.command("broadcast") & filters.user(ADMINS))
async def broadcast_cmd(client, message):
    if not message.reply_to_message:
        return await message.reply_text("ব্রডকাস্ট করার জন্য মেসেজে রিপ্লাই দিন।")
    users = users_col.find()
    success = 0
    failed = 0
    for user in users:
        try:
            await message.reply_to_message.copy(chat_id=user["user_id"])
            success += 1
        except:
            failed += 1
    await message.reply_text(f"✅ সফল: {success}\n❌ ব্যর্থ: {failed}")

@app.on_message(filters.private & filters.command("requests") & filters.user(ADMINS))
async def requests_cmd(client, message):
    requests = notfound_col.find()
    text = "অনুরোধকৃত মুভি গুলো:\n\n"
    for req in requests:
        users = ", ".join(str(u) for u in req.get("users", []))
        text += f"মুভি: {req['query']}\nব্যবহারকারী: {users}\n\n"
    await message.reply_text(text)

# Run app
if __name__ == "__main__":
    app.run()
