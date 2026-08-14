import re
import asyncio
import logging
import time
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ChatMemberHandler, filters, ContextTypes
)

from config import BOT_TOKEN, OWNER_IDS, DEVELOPER_USERNAME, CHANNEL_INVITE, MAX_WARNINGS
from database import (
    init_db, add_warning, reset_warnings,
    is_whitelisted, whitelist_user, unwhitelist_user, get_whitelist,
    register_chat, get_all_chats, register_private_user,
    remember_user, find_user_by_username
)
from status import cmd_status

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

START_IMAGE = "https://files.catbox.moe/7w33t6.jpg"
AUTO_DELETE_SECONDS = 15

# ── Small caps texts ───────────────────────────────────────────────────────────

WELCOME_TEXT = "👋 ᴡᴇʟᴄᴏᴍᴇ, {full_name}!\n\n🛡️ ʙɪᴏ ʟɪɴᴋ ᴘʀᴏᴛᴇᴄᴛᴏʀ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴅᴇᴛᴇᴄᴛꜱ ᴀɴᴅ ʙʟᴏᴄᴋꜱ ᴜɴᴡᴀɴᴛᴇᴅ ʙɪᴏ ʟɪɴᴋꜱ.\n\n🔒 ɪɴꜱᴛᴀɴᴛ ᴅᴇᴛᴇᴄᴛɪᴏɴ\n⚡ ʀᴇᴀʟ-ᴛɪᴍᴇ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ\n🚫 ᴀᴜᴛᴏᴍᴀᴛɪᴄ ʟɪɴᴋ ʙʟᴏᴄᴋɪɴɢ\n\nᴛᴀᴘ ʜᴇʟᴘ ᴛᴏ ᴠɪᴇᴡ ᴛʜᴇ ꜱᴇᴛᴜᴘ ɢᴜɪᴅᴇ, ꜰᴇᴀᴛᴜʀᴇꜱ, ᴀɴᴅ ᴄᴏᴍᴍᴀɴᴅꜱ."

HELP_TEXT = """📖 ʜᴇʟᴘ & ᴄᴏᴍᴍᴀɴᴅꜱ

👮 ᴀᴅᴍɪɴ ᴄᴏᴍᴍᴀɴᴅꜱ:
/approve @user — ᴀᴘᴘʀᴏᴠᴇ ᴜꜱᴇʀ ᴛᴏ ᴘᴏꜱᴛ ʟɪɴᴋꜱ
/unapprove @user — ʀᴇᴍᴏᴠᴇ ᴀᴘᴘʀᴏᴠᴀʟ ꜰʀᴏᴍ ᴜꜱᴇʀ
/approveinfo — ꜱʜᴏᴡ ᴀʟʟ ᴀᴘᴘʀᴏᴠᴇᴅ ᴜꜱᴇʀꜱ
/ping — ᴄʜᴇᴄᴋ ʙᴏᴛ ꜱᴘᴇᴇᴅ

👑 ᴏᴡɴᴇʀ ᴄᴏᴍᴍᴀɴᴅꜱ:
/broadcast <message> — ꜱᴇɴᴅ ᴛᴏ ᴀʟʟ ɢʀᴏᴜᴘꜱ

⚙️ ʜᴏᴡ ɪᴛ ᴡᴏʀᴋꜱ:
ʙᴏᴛ ᴅᴇᴛᴇᴄᴛꜱ ᴀʟʟ ʟɪɴᴋ ᴛʏᴘᴇꜱ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ
ᴜꜱᴇʀ ɢᴇᴛꜱ 3 ᴡᴀʀɴɪɴɢꜱ — 4ᴛʜ = 🔇 ᴍᴜᴛᴇ
ᴀᴅᴍɪɴꜱ ᴀɴᴅ ᴀᴘᴘʀᴏᴠᴇᴅ ᴜꜱᴇʀꜱ ᴀʀᴇ ᴇxᴇᴍᴘᴛ"""

# ── Link Detection ─────────────────────────────────────────────────────────────

LINK_PATTERN = re.compile(
    r'(https?://\S+'
    r'|t\.me/\S+'
    r'|telegram\.me/\S+'
    r'|me\.t/\S+'
    r'|@[A-Za-z0-9_]{3,}'
    r'|[A-Za-z0-9_.+-]+@[A-Za-z0-9_]{3,}'
    r'|\S+\.(com|in|shop|org|net|io|co|xyz|me|info|online|site|web|app|store|link|click|ly|gg|tv|live|pro|club|tech|dev|ai|bot)(\S*)?)',
    re.IGNORECASE
)


def has_link_in_text(text: str) -> bool:
    return bool(LINK_PATTERN.search(text)) if text else False


def has_link_in_entities(message) -> bool:
    """Check Telegram entities for links - works with new Telegram format."""
    # Entity types that indicate a link
    link_entity_types = {
        "url",
        "text_link",
        "mention",
        "email",
    }

    entities = message.entities or message.caption_entities or []
    for entity in entities:
        if entity.type in link_entity_types:
            return True
    return False


def has_link(message) -> bool:
    """Combined check: entities + raw text regex."""
    text = message.text or message.caption or ""
    return has_link_in_entities(message) or has_link_in_text(text)


# ── Auto-delete ────────────────────────────────────────────────────────────────

async def auto_delete(message, delay: int = AUTO_DELETE_SECONDS):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass


def schedule_delete(message):
    asyncio.ensure_future(auto_delete(message))


# ── Helpers ────────────────────────────────────────────────────────────────────

async def is_admin(context, chat_id: int, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


def get_text_mention_user(message):
    """
    Extract a User object directly from a text_mention entity.
    This handles the case where an admin taps a user's name from the
    group member list to mention someone without a @username -
    Telegram embeds the full User object in the entity itself.
    """
    entities = message.entities or []
    for entity in entities:
        if entity.type == "text_mention" and entity.user:
            return entity.user
    return None


async def resolve_user(context, chat_id: int, arg: str):
    """
    Resolve a user from a command argument.
    Supports: numeric user_id, @username, or plain username.
    Returns the User object or None if not found.
    """
    arg = arg.strip()

    # Case 1: Numeric user ID
    if arg.lstrip("-").isdigit():
        try:
            member = await context.bot.get_chat_member(chat_id, int(arg))
            return member.user
        except Exception as e:
            logger.warning(f"resolve_user numeric failed for {arg}: {e}")
            return None

    # Case 2: @username or username
    username = arg.lstrip("@").lower()

    # Try 1: Search group admins (always available, no extra permission needed)
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        for admin in admins:
            if admin.user.username and admin.user.username.lower() == username:
                return admin.user
    except Exception as e:
        logger.warning(f"resolve_user admin search failed: {e}")

    # Try 2: Local database - users the bot has seen chatting in this group before
    try:
        result = await find_user_by_username(username)
        if result:
            found_id, _ = result
            member = await context.bot.get_chat_member(chat_id, found_id)
            return member.user
    except Exception as e:
        logger.warning(f"resolve_user local db lookup failed: {e}")

    # Try 3: Direct global chat lookup (works only for public usernames Telegram can resolve)
    try:
        chat_info = await context.bot.get_chat(f"@{username}")
        return chat_info
    except Exception as e:
        logger.warning(f"resolve_user @lookup failed for @{username}: {e}")

    return None


async def send_and_autodelete(context, chat_id: int, text: str):
    """Send plain text message and schedule auto-delete."""
    try:
        msg = await context.bot.send_message(chat_id=chat_id, text=text)
        schedule_delete(msg)
        return msg
    except Exception as e:
        logger.error(f"send_and_autodelete error: {e}")


# ── /start ─────────────────────────────────────────────────────────────────────

def main_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ ᴀᴅᴅ ᴍᴇ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ ➕",
                              url=f"https://t.me/{bot_username}?startgroup=true")],
        [InlineKeyboardButton("📋 ʜᴇʟᴘ ᴀɴᴅ ᴄᴏᴍᴍᴀɴᴅꜱ", callback_data="help")],
        [
            InlineKeyboardButton("👨‍💻 ᴅᴇᴠᴇʟᴏᴘᴇʀ ↗️", url=f"https://t.me/{DEVELOPER_USERNAME}"),
            InlineKeyboardButton("📢 ᴄʜᴀɴɴᴇʟ ↗️", url=CHANNEL_INVITE)
        ]
    ])


def help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data="back")]
    ])


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type != "private":
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    await register_private_user(user.id, user.full_name or "Unknown")

    await update.message.reply_photo(
        photo=START_IMAGE,
        caption=WELCOME_TEXT.format(full_name=user.full_name or "User"),
        reply_markup=main_keyboard(context.bot.username)
    )


# ── Help callback ──────────────────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.message.chat.type != "private":
        return

    if query.data == "help":
        await query.message.edit_caption(caption=HELP_TEXT, reply_markup=help_keyboard())
    elif query.data == "back":
        user = query.from_user
        await query.message.edit_caption(
            caption=WELCOME_TEXT.format(full_name=user.full_name or "User"),
            reply_markup=main_keyboard(context.bot.username)
        )


# ── /ping ──────────────────────────────────────────────────────────────────────

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    t = time.monotonic()
    msg = await update.message.reply_text("🏓 ᴘɪɴɢɪɴɢ...")
    ms = int((time.monotonic() - t) * 1000)
    await msg.edit_text(f"🏓 ᴘᴏɴɢ!\n⚡ ʀᴇꜱᴘᴏɴꜱᴇ: {ms}ms\n✅ ʙᴏᴛ ɪꜱ ᴀʟɪᴠᴇ ᴀɴᴅ ʀᴜɴɴɪɴɢ!")
    if chat.type != "private":
        schedule_delete(msg)
        try:
            await update.message.delete()
        except Exception:
            pass


# ── /approve ───────────────────────────────────────────────────────────────────

async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text("❌ ɢʀᴏᴜᴘꜱ ᴏɴʟʏ.")
        return

    if not await is_admin(context, chat.id, user.id):
        msg = await update.message.reply_text("❌ ᴏɴʟʏ ᴀᴅᴍɪɴꜱ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ.")
        schedule_delete(msg)
        try: await update.message.delete()
        except Exception: pass
        return

    target = None
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    else:
        target = get_text_mention_user(update.message)
        if not target and context.args:
            target = await resolve_user(context, chat.id, context.args[0])

    if not target:
        msg = await update.message.reply_text(
            "❌ ᴜꜱᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ.\n"
            "ᴛɪᴘ: ʀᴇᴘʟʏ ᴛᴏ ᴛʜᴇɪʀ ᴍᴇꜱꜱᴀɢᴇ, ᴏʀ ᴜꜱᴇ ᴛʜᴇɪʀ ɴᴜᴍᴇʀɪᴄ ᴜꜱᴇʀ ɪᴅ.\n"
            "@ᴜꜱᴇʀɴᴀᴍᴇ ᴏɴʟʏ ᴡᴏʀᴋꜱ ɪꜰ ᴛᴇʟᴇɢʀᴀᴍ ᴄᴀɴ ʀᴇꜱᴏʟᴠᴇ ɪᴛ ᴘᴜʙʟɪᴄʟʏ."
        )
        schedule_delete(msg)
        try: await update.message.delete()
        except Exception: pass
        return
    await whitelist_user(target.id, chat.id, user.id)
    await reset_warnings(target.id, chat.id)
    msg = await update.message.reply_text(
        f"✅ {target.full_name} ʜᴀꜱ ʙᴇᴇɴ ᴀᴘᴘʀᴏᴠᴇᴅ. ᴛʜᴇʏ ᴄᴀɴ ɴᴏᴡ ᴘᴏꜱᴛ ʟɪɴᴋꜱ ꜰʀᴇᴇʟʏ."
    )
    schedule_delete(msg)
    try: await update.message.delete()
    except Exception: pass


# ── /unapprove ─────────────────────────────────────────────────────────────────

async def cmd_unapprove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text("❌ ɢʀᴏᴜᴘꜱ ᴏɴʟʏ.")
        return

    if not await is_admin(context, chat.id, user.id):
        msg = await update.message.reply_text("❌ ᴏɴʟʏ ᴀᴅᴍɪɴꜱ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ.")
        schedule_delete(msg)
        try: await update.message.delete()
        except Exception: pass
        return

    target = None
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    else:
        target = get_text_mention_user(update.message)
        if not target and context.args:
            target = await resolve_user(context, chat.id, context.args[0])

    if not target:
        msg = await update.message.reply_text("❌ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜꜱᴇʀ ᴏʀ ᴘʀᴏᴠɪᴅᴇ @ᴜꜱᴇʀɴᴀᴍᴇ.")
        schedule_delete(msg)
        try: await update.message.delete()
        except Exception: pass
        return

    await unwhitelist_user(target.id, chat.id)
    msg = await update.message.reply_text(
        f"⚠️ {target.full_name} ᴀᴘᴘʀᴏᴠᴀʟ ʜᴀꜱ ʙᴇᴇɴ ʀᴇᴍᴏᴠᴇᴅ."
    )
    schedule_delete(msg)
    try: await update.message.delete()
    except Exception: pass


# ── /approveinfo ───────────────────────────────────────────────────────────────

async def cmd_approveinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text("❌ ɢʀᴏᴜᴘꜱ ᴏɴʟʏ.")
        return

    if not await is_admin(context, chat.id, user.id):
        msg = await update.message.reply_text("❌ ᴏɴʟʏ ᴀᴅᴍɪɴꜱ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ.")
        schedule_delete(msg)
        try: await update.message.delete()
        except Exception: pass
        return

    wl_ids = await get_whitelist(chat.id)
    if not wl_ids:
        msg = await update.message.reply_text("📋 ɴᴏ ᴀᴘᴘʀᴏᴠᴇᴅ ᴜꜱᴇʀꜱ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ.")
        schedule_delete(msg)
        try: await update.message.delete()
        except Exception: pass
        return

    lines = ["📋 ᴀᴘᴘʀᴏᴠᴇᴅ ᴜꜱᴇʀꜱ:\n"]
    for uid in wl_ids:
        try:
            m = await context.bot.get_chat_member(chat.id, uid)
            lines.append(f"• {m.user.full_name}")
        except Exception:
            lines.append(f"• ID: {uid}")

    msg = await update.message.reply_text("\n".join(lines))
    schedule_delete(msg)
    try: await update.message.delete()
    except Exception: pass


# ── /broadcast ─────────────────────────────────────────────────────────────────

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id not in OWNER_IDS:
        await update.message.reply_text("❌ ᴏᴡɴᴇʀꜱ ᴏɴʟʏ.")
        return

    # Get raw text after the command, preserving exact formatting
    full_text = update.message.text or ""
    parts = full_text.split(None, 1)  # split only on first whitespace

    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text("📢 ᴜꜱᴀɢᴇ: /broadcast Your message")
        return

    broadcast_text = parts[1]

    chat_ids = await get_all_chats()

    if not chat_ids:
        await update.message.reply_text("❌ ɴᴏ ɢʀᴏᴜᴘꜱ ʀᴇɢɪꜱᴛᴇʀᴇᴅ ʏᴇᴛ.")
        return

    status = await update.message.reply_text(f"📡 ʙʀᴏᴀᴅᴄᴀꜱᴛɪɴɢ ᴛᴏ {len(chat_ids)} ɢʀᴏᴜᴘꜱ...")
    success = 0
    failed = 0

    for cid in chat_ids:
        try:
            await context.bot.send_message(chat_id=cid, text=broadcast_text)
            success += 1
        except Exception as e:
            logger.warning(f"Broadcast failed {cid}: {e}")
            failed += 1

    await status.edit_text(
        f"✅ ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴄᴏᴍᴘʟᴇᴛᴇ\n📨 ꜱᴇɴᴛ: {success}\n❌ ꜰᴀɪʟᴇᴅ: {failed}"
    )


# ── New Member Tracker ─────────────────────────────────────────────────────────

async def handle_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track users the moment they join the group - no need to wait for their first message."""
    result = update.chat_member
    if not result:
        return

    new_status = result.new_chat_member.status
    if new_status in ("member", "administrator", "restricted"):
        member_user = result.new_chat_member.user
        if member_user.username and not member_user.is_bot:
            await remember_user(
                member_user.id,
                member_user.username,
                member_user.full_name or "Unknown"
            )


# ── Message Handler ────────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return
    if chat.type == "private":
        return

    # Register group for broadcast
    await register_chat(chat.id, chat.title or "Unknown")

    # Remember this user's username for /approve @username lookups later
    if user.username:
        await remember_user(user.id, user.username, user.full_name or "Unknown")

    if user.is_bot:
        return
    if user.id in OWNER_IDS:
        return
    if await is_admin(context, chat.id, user.id):
        return
    if await is_whitelisted(user.id, chat.id):
        return

    # Fetch user's profile bio and check for links
    try:
        chat_info = await context.bot.get_chat(user.id)
        bio_text = chat_info.bio or ""
    except Exception as e:
        logger.warning(f"Could not fetch bio for {user.id}: {e}")
        return

    if not has_link_in_text(bio_text):
        return

    # Double-check after a short delay to avoid stale/cached bio false positives
    await asyncio.sleep(1.5)
    try:
        chat_info_recheck = await context.bot.get_chat(user.id)
        bio_text_recheck = chat_info_recheck.bio or ""
    except Exception as e:
        logger.warning(f"Could not re-fetch bio for {user.id}: {e}")
        return

    if not has_link_in_text(bio_text_recheck):
        # Bio was already cleaned, cache was just stale - skip warning
        return

    # Delete the user's message (their bio itself cannot be deleted, only their messages)
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Delete failed: {e}")

    warn_count = await add_warning(user.id, chat.id)

    if warn_count > MAX_WARNINGS:
        # Mute permanently
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat.id,
                user_id=user.id,
                permissions=ChatPermissions(can_send_messages=False)
            )
        except Exception as e:
            logger.error(f"Mute failed: {e}")

        await send_and_autodelete(
            context, chat.id,
            f"🔇 {user.full_name} ʜᴀꜱ ʙᴇᴇɴ ᴍᴜᴛᴇᴅ!\n\n"
            f"ʀᴇᴀꜱᴏɴ: ᴘᴏꜱᴛᴇᴅ ʙɪᴏ ʟɪɴᴋ {warn_count} ᴛɪᴍᴇꜱ.\n"
            "ᴄᴏɴᴛᴀᴄᴛ ᴀɴ ᴀᴅᴍɪɴ ᴛᴏ ɢᴇᴛ ᴜɴᴍᴜᴛᴇᴅ."
        )
    else:
        icons = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣"}
        icon = icons.get(warn_count, "⚠️")
        remaining = MAX_WARNINGS - warn_count
        next_action = (
            "⛔ ɴᴇxᴛ ᴏꜰꜰᴇɴꜱᴇ = 🔇 ᴘᴇʀᴍᴀɴᴇɴᴛ ᴍᴜᴛᴇ!"
            if remaining == 0
            else f"🔔 {remaining} ᴡᴀʀɴɪɴɢ(ꜱ) ʟᴇꜰᴛ ʙᴇꜰᴏʀᴇ ᴍᴜᴛᴇ"
        )

        await send_and_autodelete(
            context, chat.id,
            f"⚠️ ᴡᴀʀɴɪɴɢ {icon} — {user.full_name}\n\n"
            f"🔗 ʟɪɴᴋ ᴅᴇᴛᴇᴄᴛᴇᴅ ɪɴ ʏᴏᴜʀ ᴘʀᴏꜰɪʟᴇ ʙɪᴏ!\n\n"
            f"📊 ᴡᴀʀɴɪɴɢꜱ: {warn_count}/{MAX_WARNINGS}\n"
            f"{next_action}"
        )


# ── Main ───────────────────────────────────────────────────────────────────────

async def post_init(application: Application):
    await init_db()
    logger.info("Database initialized successfully.")


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("approve", cmd_approve))
    app.add_handler(CommandHandler("unapprove", cmd_unapprove))
    app.add_handler(CommandHandler("approveinfo", cmd_approveinfo))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, handle_message))
    app.add_handler(ChatMemberHandler(handle_chat_member_update, ChatMemberHandler.CHAT_MEMBER))

    logger.info("Bio Link Protector Bot is RUNNING...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
