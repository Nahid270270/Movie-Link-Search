import os
import asyncio
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pymongo import MongoClient
from rapidfuzz import fuzz

# ওয়েব সার্ভার (health check) চালানো, Koyeb এর জন্য প্রয়োজন
def start_web():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    print(f"Web server running on port {port}")
    server.serve_forever()

threading.Thread(target=start_web, daemon=True).start()

# Environment variables
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")  # UserSession string
MONGO_URI = os.environ.get("MONGO_URI")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID"))
ADMINS = [int(x) for x in os.environ.get("ADMINS", "").split() if x.strip().isdigit()]

# MongoDB setup
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["movie_bot"]
collection = db["movies"]
user_collection = db["users"]
not_found_collection = db["not_found"]

# Pyrogram client using UserSession
app = Client("movie_bot_session", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

# START command - সকল ইউজারের জন্য
@app.on_message(filters.private & filters.command("start"))
async def start_handler(client, message):
    user_collection.update_one({"user_id": message.from_user.id}, {"$set": {"user_id": message.from_user.id}}, upsert=True)
    await message.reply_text(
        "হ্যালো! আমি মুভি লিংক সার্চ বট!\n\nমুভির নাম লিখো, আমি খুঁজে এনে দিব!",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{(await client.get_me()).username}?startgroup=true"),
                    InlineKeyboardButton("📢 Update Channel", url="https://t.me/CTGMovieOfficial")
                ]
            ]
        )
    )

# HELP command - সকল ইউজারের জন্য
@app.on_message(filters.private & filters.command("help"))
async def help_handler(client, message):
    await message.reply_text(
        "**ব্যবহার নির্দেশনা:**\n\nশুধু মুভির নাম লিখে পাঠান, আমি খুঁজে দেবো!\n\nআপনি যদি কিছু না পান, তাহলে অনুরূপ কিছু সাজেস্ট করা হবে।"
    )

# STATS command - শুধুমাত্র এডমিনদের জন্য
@app.on_message(filters.private & filters.command("stats") & filters.user(ADMINS))
async def stats_handler(client, message):
    total_movies = collection.count_documents({})
    total_users = user_collection.count_documents({})
    await message.reply_text(f"মোট মুভি: {total_movies}\nমোট ইউজার: {total_users}")

# DELETE ALL command - শুধুমাত্র এডমিনদের জন্য
@app.on_message(filters.private & filters.command("delete_all") & filters.user(ADMINS))
async def delete_all_handler(client, message):
    collection.delete_many({})
    await message.reply_text("সব মুভি ডাটাবেজ থেকে মুছে ফেলা হয়েছে।")

# BROADCAST command - শুধুমাত্র এডমিনদের জন্য
@app.on_message(filters.private & filters.command("broadcast") & filters.user(ADMINS))
async def broadcast_handler(client, message):
    if not message.reply_to_message:
        return await message.reply_text("ব্রডকাস্ট করার জন্য কোনো মেসেজে রিপ্লাই দিন।")

    users = user_collection.find()
    success = 0
    failed = 0

    for user in users:
        try:
            await message.reply_to_message.copy(chat_id=user["user_id"])
            success += 1
        except Exception:
            failed += 1

    await message.reply_text(f"✅ সফল: {success}\n❌ ব্যর্থ: {failed}")

# ইউজারের মুভি সার্চ - সকল প্রাইভেট ইউজারের জন্য
@app.on_message(filters.private & filters.text & ~filters.command(["start", "help", "stats", "delete_all", "broadcast"]))
async def search_movie(client, message):
    query = message.text.strip().lower()
    movies = list(collection.find())
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
            sent = await client.forward_messages(
                chat_id=message.chat.id,
                from_chat_id=CHANNEL_ID,
                message_ids=best_match["message_id"]
            )
            await asyncio.sleep(300)  # ৫ মিনিট পর মেসেজ ডিলিট
            await sent.delete()
        except Exception as e:
            await message.reply_text(f"ফরওয়ার্ড করতে সমস্যা: {e}")
    else:
        suggestions = sorted(movies, key=lambda m: fuzz.partial_ratio(query, m.get("text", "").lower()), reverse=True)[:5]
        buttons = [
            [InlineKeyboardButton(movie["text"][:30], callback_data=f"id_{movie['message_id']}")]
            for movie in suggestions if fuzz.partial_ratio(query, movie.get("text", "").lower()) > 50
        ]

        if buttons:
            await message.reply("আপনি কি নিচের কোনটি খুঁজছেন?", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            not_found_collection.update_one(
                {"query": query},
                {"$addToSet": {"users": message.from_user.id}, "$set": {"query": query}},
                upsert=True
            )
            for admin_id in ADMINS:
                try:
                    await client.send_message(
                        chat_id=admin_id,
                        text=f"⚠️ ইউজার @{message.from_user.username or message.from_user.id} '{query}' মুভি খুঁজে পায়নি।"
                    )
                except Exception as e:
                    print(f"Failed to notify admin {admin_id}: {e}")

            await message.reply(f"দুঃখিত, '{query}' নামে কিছু খুঁজে পাইনি!")

# Callback query for suggestions
@app.on_callback_query(filters.regex("^id_"))
async def suggestion_click(client, callback_query: CallbackQuery):
    message_id = int(callback_query.data.replace("id_", ""))
    result = collection.find_one({"message_id": message_id})

    if result:
        try:
            sent = await client.forward_messages(
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

# Channel থেকে মুভি মেসেজ সংরক্ষণ
@app.on_message(filters.channel)
async def save_channel_messages(client, message):
    if message.chat.id == CHANNEL_ID:
        text = message.text or message.caption
        if text:
            collection.update_one(
                {"message_id": message.id},
                {"$set": {"text": text, "message_id": message.id}},
                upsert=True
            )
            print(f"Saved: {text[:40]}...")

            # নতুন মুভির নোটিফিকেশন ইউজারদের কাছে পাঠানো (এডমিন ছাড়া সব ইউজার)
            users = user_collection.find()
            for user in users:
                try:
                    await client.send_message(
                        chat_id=user["user_id"],
                        text=(
                            "হ্যালো গাইস!\n\n"
                            f"নতুন মুভি **'{text[:35]}'** এখন মাত্র আপলোড করা হয়েছে!\n"
                            "আপনি চাইলে এখনই নামটি লিখে সার্চ করে দেখে নিতে পারেন।"
                        )
                    )
                except Exception as e:
                    print(f"Couldn't notify user {user['user_id']}: {e}")

# এডমিনদের কাছে ইউজারদের নট ফাউন্ড রিকোয়েস্ট দেখানোর কমান্ড
@app.on_message(filters.private & filters.command("check_requests") & filters.user(ADMINS))
async def check_requests(client, message):
    requests = not_found_collection.find()
    response = "এই মুভিগুলো খোঁজার জন্য রিকোয়েস্ট করা হয়েছে:\n\n"
    for request in requests:
        users = ", ".join([str(user) for user in request["users"]])
        response += f"মুভি: {request['query']}, ইউজাররা: {users}\n"
    await message.reply_text(response)

# গ্রুপে সার্চ সাপোর্ট (গ্রুপে যেকোন ইউজারের জন্য)
@app.on_message(filters.group & filters.text & ~filters.command(["start", "help", "stats", "delete_all", "broadcast"]))
async def group_search_movie(client, message):
    query = message.text.strip().lower()
    movies = list(collection.find())
    best_match = None
    best_score = 0

    for movie in movies:
        title = movie.get("text", "").lower()
        score = fuzz.partial_ratio(query, title)
        if score > best_score:
            best_score = score
            best_match = movie

    if best_score >= 70 and best_match:
        try:
            sent = await client.forward_messages(
                chat_id=message.chat.id,
                from_chat_id=CHANNEL_ID,
                message_ids=best_match["message_id"]
            )
            await asyncio.sleep(300)
            await sent.delete()
        except Exception as e:
            await message.reply_text(f"ফরওয়ার্ড করতে সমস্যা: {e}")
    else:
        suggestions = sorted(movies, key=lambda m: fuzz.partial_ratio(query, m.get("text", "").lower()), reverse=True)[:5]
        buttons = [
            [InlineKeyboardButton(movie["text"][:30], callback_data=f"id_{movie['message_id']}")]
            for movie in suggestions if fuzz.partial_ratio(query, movie.get("text", "").lower()) > 50
        ]

        if buttons:
            await message.reply("আপনি কি নিচের কোনটি খুঁজছেন?", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            not_found_collection.update_one(
                {"query": query},
                {"$addToSet": {"users": message.from_user.id}, "$set": {"query": query}},
                upsert=True
            )
            for admin_id in ADMINS:
                try:
                    await client.send_message(
                        chat_id=admin_id,
                        text=f"⚠️ ইউজার @{message.from_user.username or message.from_user.id} '{query}' মুভি খুঁজে পায়নি।"
                    )
                except Exception as e:
                    print(f"Failed to notify admin {admin_id}: {e}")

            await message.reply(f"দুঃখিত, '{query}' নামে কিছু খুঁজে পাইনি!")

if __name__ == "__main__":
    print("Starting Bot...")
    app.run()
