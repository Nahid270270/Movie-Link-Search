import os import time import asyncio import threading from http.server import SimpleHTTPRequestHandler, HTTPServer from pyrogram import Client, filters from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery from pymongo import MongoClient

Start a simple web server for Koyeb health check

def start_web(): server = HTTPServer(("0.0.0.0", 8000), SimpleHTTPRequestHandler) print("Web server running on port 8000") server.serve_forever()

threading.Thread(target=start_web).start()

Pyrogram Bot Setup

API_ID = int(os.environ.get("API_ID")) API_HASH = os.environ.get("API_HASH") BOT_TOKEN = os.environ.get("BOT_TOKEN")) MONGO_URI = os.environ.get("MONGO_URI")) CHANNEL_ID = int(os.environ.get("CHANNEL_ID")) ADMINS = [int(x) for x in os.environ.get("ADMINS", "8172129114").split()]

mongo_client = MongoClient(MONGO_URI) db = mongo_client["movie_bot"] collection = db["movies"] user_collection = db["users"]

pyrogram_app = Client("MovieBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@pyrogram_app.on_message(filters.private & filters.command("start")) async def start_handler(client, message: Message): user_collection.update_one({"_id": message.from_user.id}, {"$set": {"name": message.from_user.first_name}}, upsert=True) await message.reply_text("হ্যালো! আমি মুভি লিংক সার্চ বট!\n\nমুভির নাম লিখো, আমি খুঁজে এনে দিব!")

@pyrogram_app.on_message(filters.command("help") & filters.private) async def help_command(client, message: Message): await message.reply_text( "সাহায্য মেনু:\n\n" "/start - বট চালু করুন\n" "/help - সাহায্য মেনু দেখুন\n" "/about - বট ও ডেভেলপার তথ্য\n" "/cancel - চলমান অপারেশন বন্ধ করুন\n" "/broadcast - সকল ইউজারে মেসেজ পাঠান (এডমিন)\n" "/users - মোট ইউজার সংখ্যা দেখুন (এডমিন)\n" )

@pyrogram_app.on_message(filters.command("about") & filters.private) async def about_command(client, message: Message): await message.reply_text( "বট পরিচিতি:\n\n" "➤ নাম: Movie Link Search Bot\n" "➤ ভার্সন: 1.1\n" "➤ ডেভেলপার: [আপনার ইউজারনেম]\n" "➤ সাপোর্ট: @YourSupportGroup" )

@pyrogram_app.on_message(filters.command("users") & filters.user(ADMINS)) async def user_stats(client, message: Message): count = user_collection.count_documents({}) await message.reply_text(f"মোট রেজিস্টার্ড ইউজার: {count}")

@pyrogram_app.on_message(filters.command("broadcast") & filters.user(ADMINS)) async def broadcast_message(client, message: Message): if len(message.command) < 2: return await message.reply("দয়া করে একটি মেসেজ প্রদান করুন। উদাহরণ: /broadcast Hello") msg = message.text.split(None, 1)[1] users = user_collection.find({}) sent, failed = 0, 0 for user in users: try: await client.send_message(user["_id"], msg) sent += 1 await asyncio.sleep(0.1) except: failed += 1 await message.reply_text(f"ব্রডকাস্ট সম্পন্ন!\nসফল: {sent}\nব্যর্থ: {failed}")

@pyrogram_app.on_message(filters.command("cancel") & filters.private) async def cancel_command(client, message: Message): await message.reply_text("আপনার অনুরোধ বাতিল করা হয়েছে।")

@pyrogram_app.on_message(filters.text & filters.private & ~filters.command("start")) async def search_movie(client, message: Message): query = message.text.strip() result = collection.find_one({"text": {"$regex": f"^{query}$", "$options": "i"}})

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

@pyrogram_app.on_callback_query(filters.regex("^id_")) async def suggestion_click(client, callback_query: CallbackQuery): message_id = int(callback_query.data.replace("id_", "")) result = collection.find_one({"message_id": message_id})

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

@pyrogram_app.on_message(filters.channel) async def save_channel_messages(client, message: Message): if message.chat.id == CHANNEL_ID: text = message.text or message.caption if text: collection.update_one( {"message_id": message.id}, {"$set": {"text": text, "message_id": message.id}}, upsert=True ) print(f"Saved: {text[:40]}...")

if name == "main": pyrogram_app.run()
