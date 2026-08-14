import aiosqlite
from telegram import Update
from telegram.ext import ContextTypes

from config import OWNER_IDS

DB_PATH = "biolink.db"


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id not in OWNER_IDS:
        return

    async with aiosqlite.connect(DB_PATH) as db:

        # Total active groups
        async with db.execute("SELECT COUNT(*) FROM chats") as cursor:
            row = await cursor.fetchone()
            total_groups = row[0] if row else 0

        # Total unique users who have warnings (interacted in groups)
        async with db.execute("SELECT COUNT(DISTINCT user_id) FROM warnings") as cursor:
            row = await cursor.fetchone()
            total_warned_users = row[0] if row else 0

        # Total approved users across all groups
        async with db.execute("SELECT COUNT(*) FROM whitelist") as cursor:
            row = await cursor.fetchone()
            total_approved = row[0] if row else 0

        # Total warnings issued
        async with db.execute("SELECT SUM(count) FROM warnings") as cursor:
            row = await cursor.fetchone()
            total_warnings = row[0] if row else 0

        # Total users who started bot in private
        async with db.execute("SELECT COUNT(*) FROM private_users") as cursor:
            row = await cursor.fetchone()
            total_private_users = row[0] if row else 0

    text = (
        "📊 ʙᴏᴛ ꜱᴛᴀᴛᴜꜱ\n\n"
        f"👤 ᴜꜱᴇʀꜱ ꜱᴛᴀʀᴛᴇᴅ ʙᴏᴛ: {total_private_users}\n"
        f"👥 ɢʀᴏᴜᴘꜱ ᴀᴄᴛɪᴠᴇ: {total_groups}\n"
        f"✅ ᴀᴘᴘʀᴏᴠᴇᴅ ᴜꜱᴇʀꜱ: {total_approved}\n"
        f"⚠️ ᴜꜱᴇʀꜱ ᴡᴀʀɴᴇᴅ: {total_warned_users}\n"
        f"🔗 ᴛᴏᴛᴀʟ ʟɪɴᴋꜱ ʀᴇᴍᴏᴠᴇᴅ: {total_warnings}"
    )

    await update.message.reply_text(text)
