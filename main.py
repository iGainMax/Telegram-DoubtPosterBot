import telebot
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import random
import re
import os, json   # ✅ needed for environment variable

# --- CONFIGURABLE SETTINGS ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Setup Telegram bot
bot = telebot.TeleBot(BOT_TOKEN)

# Google Sheets setup
scope = [
    "https://spreadsheets.google.com/feeds",
    'https://www.googleapis.com/auth/spreadsheets',
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

# creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)

creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
client = gspread.authorize(creds)
sheet = client.open("DoubtBotSheet").sheet1

# Anonymous ID Generator
user_anon_map = {}

def get_anon_id(user_id):
    if user_id not in user_anon_map:
        user_anon_map[user_id] = f"Anon#{random.randint(100,999)}"
    return user_anon_map[user_id]

SUBJECT_ALIASES = {
    "p": "physics", "phy": "physics", "physics": "physics",
    "m": "maths", "math": "maths", "maths": "maths",
    "c": "chemistry", "chem": "chemistry", "chemistry": "chemistry",
    "b": "biology", "bio": "biology", "biology": "biology"
}

GROUP_IDS = {
    "class12": -1002140385835,
    "class11": -1002557367347
}

TOPIC_IDS = {
    "class12": {"maths": 8, "physics": 9, "chemistry": 10, "biology": 11},
    "class11": {"maths": 2, "physics": 3, "chemistry": 4, "biology": 5}
}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(message.chat.id, "👋 Send your doubt like this:\nSubject: Maths\nDoubt: What is sin 30?")

@bot.message_handler(func=lambda message: message.reply_to_message is not None)
def handle_answer(message):
    try:
        solver_id = message.from_user.id
        solver_username = message.from_user.username or message.from_user.first_name or "NoName"
        chat_id = message.chat.id

        if chat_id == GROUP_IDS["class12"]:
            group_name = "class12"
        elif chat_id == GROUP_IDS["class11"]:
            group_name = "class11"
        else:
            group_name = "unknown"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        original_msg = message.reply_to_message
        if original_msg.from_user.id != bot.get_me().id:
            print("⚠️ Skipped logging: Not a reply to bot's message.")
            return

        doubt_text = original_msg.text or "(No text)"
        answer_photo_url = ""

        if message.content_type == 'photo':
            file_id = message.photo[-1].file_id
            file_info = bot.get_file(file_id)
            answer_photo_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
            answer_text = message.caption or "(No caption)"
        else:
            answer_text = message.text or ""
            if not answer_text.strip() and not answer_photo_url:
                print("⚠️ Skipped logging: Empty answer and no image.")
                return

        if "Subject:" in doubt_text:
            subject_line = doubt_text.split("\n")[0]
            subject = subject_line.replace("Subject:", "").strip()
        else:
            subject = "Unknown"

        answer_sheet = client.open("DoubtBotSheet").worksheet("Answers")
        answer_sheet.append_row([
            timestamp, group_name, str(solver_id), solver_username, subject,
            doubt_text, answer_text, 2, answer_photo_url
        ])

        bot.send_message(message.chat.id, f"📝 Answer logged for {solver_username} (+2 points).",
                         message_thread_id=message.message_thread_id)
        print(f"Logged answer by {solver_username} to sheet.")

    except Exception as e:
        print("❌ Error logging answer:", e)

@bot.message_handler(content_types=["text", "photo"])

def handle_message(message):
    print("Message received from user.")
    print("Raw message repr:", repr(message.text))
    if message.chat.type != "private":
        print("⚠️ Ignored: Message is not from private chat.")
        return

    
    try:
        text = message.caption if message.content_type == 'photo' else message.text
        lines = text.strip().split('\n') if text else []

        group_name = None
        subject = None

        first_line = lines[0].strip().lower().replace(" ", "") if lines else ""
        match = re.match(r"^([c]?\d{2})([a-zA-Z]+)[:\-]", first_line)
        if match:
            class_code = match.group(1).replace("c", "")
            subject_code = match.group(2).lower()

            group_name = {
                "12": "class12",
                "11": "class11"
            }.get(class_code)

            subject = SUBJECT_ALIASES.get(subject_code)

            if not group_name or not subject:
                bot.send_message(message.chat.id,
                    "❗ Please use a valid class (11 or 12) and subject code like `12M:` or `11C:`.",
                    parse_mode='Markdown')
                print("❌ Invalid format: unknown class or subject code.")
                return

            chat_id = GROUP_IDS.get(group_name)
            if not chat_id:
                bot.send_message(message.chat.id,
                    "❌ Could not identify the correct group. Please check your class format like '12M:' or '11C:'.",
                    parse_mode='Markdown')
                print("❌ Failed: Unknown group_name or chat_id.")
                return

            prefix = match.group(0)
            remaining = text[len(prefix):].strip()
            doubt = remaining if remaining else '\n'.join(lines[1:]).strip()
        else:
            bot.send_message(message.chat.id,
                "❗ *Invalid format!*\n\nPlease start your message like this:\n\n12M: What is your doubt?\n11C: Please explain acid-base concept\n\nJust type your class (11 or 12) and subject code (M/P/C/B) followed by : and then your doubt.\n\nExample\n11P: What is Newton's 2nd Law?",
                parse_mode='Markdown')
            print("❌ Invalid format. Missing class+subject code.")
            return

        if not doubt:
            bot.send_message(message.chat.id,
                "❗ *Incomplete message!*\nYour doubt seems empty.",
                parse_mode='Markdown')
            print("❌ Empty doubt content.")
            return

        subject = subject or "Unknown"

        file_id = ""
        photo_url = ""
        if message.content_type == 'photo':
            file_id = message.photo[-1].file_id
            file_info = bot.get_file(file_id)
            photo_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"

        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.first_name or "NoName"
        anon_id = get_anon_id(user_id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        sheet.append_row([timestamp, group_name, str(user_id), username, subject, doubt, anon_id, photo_url])

        post_text = f"📘 *Subject:* {subject}\n❓ *Doubt from {anon_id}:*\n{doubt}"
        thread_id = TOPIC_IDS.get(group_name, {}).get(subject)

        if thread_id:
            if photo_url:
                bot.send_photo(chat_id, file_id, caption=post_text, parse_mode="Markdown", message_thread_id=thread_id)
            else:
                bot.send_message(chat_id, post_text, parse_mode='Markdown', message_thread_id=thread_id)
            print(f"✅ Posted in topic: {subject} (thread_id: {thread_id})")
        else:
            if photo_url:
                bot.send_photo(chat_id, file_id, caption=post_text, parse_mode="Markdown")
            else:
                bot.send_message(chat_id, post_text, parse_mode='Markdown')
            print("⚠️ Posted in General (topic not found)")

    except Exception as e:
        print("❌ Error occurred:", e)

# Start the bot as a worker (infinite loop, restart if it crashes)
bot.infinity_polling(timeout=60, long_polling_timeout=60)

