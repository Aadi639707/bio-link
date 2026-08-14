import aiosqlite

DB_PATH = "biolink.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Warnings table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                user_id INTEGER,
                chat_id INTEGER,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        # Whitelist table - users allowed to post links freely
        await db.execute("""
            CREATE TABLE IF NOT EXISTS whitelist (
                user_id INTEGER,
                chat_id INTEGER,
                added_by INTEGER,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        # Broadcast tracking table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                chat_title TEXT
            )
        """)
        # Private users who started the bot
        await db.execute("""
            CREATE TABLE IF NOT EXISTS private_users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT
            )
        """)
        # Known users - tracks username to user_id mapping from group activity
        await db.execute("""
            CREATE TABLE IF NOT EXISTS known_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT
            )
        """)
        await db.commit()


# ── Warning functions ──────────────────────────────────────────────────────────

async def get_warnings(user_id: int, chat_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT count FROM warnings WHERE user_id=? AND chat_id=?",
            (user_id, chat_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def add_warning(user_id: int, chat_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        current = await get_warnings(user_id, chat_id)
        new_count = current + 1
        await db.execute(
            "INSERT OR REPLACE INTO warnings (user_id, chat_id, count) VALUES (?, ?, ?)",
            (user_id, chat_id, new_count)
        )
        await db.commit()
        return new_count


async def reset_warnings(user_id: int, chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM warnings WHERE user_id=? AND chat_id=?",
            (user_id, chat_id)
        )
        await db.commit()


# ── Whitelist functions ────────────────────────────────────────────────────────

async def is_whitelisted(user_id: int, chat_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM whitelist WHERE user_id=? AND chat_id=?",
            (user_id, chat_id)
        ) as cursor:
            return await cursor.fetchone() is not None


async def whitelist_user(user_id: int, chat_id: int, added_by: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO whitelist (user_id, chat_id, added_by) VALUES (?, ?, ?)",
            (user_id, chat_id, added_by)
        )
        await db.commit()


async def unwhitelist_user(user_id: int, chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM whitelist WHERE user_id=? AND chat_id=?",
            (user_id, chat_id)
        )
        await db.commit()


async def get_whitelist(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM whitelist WHERE chat_id=?",
            (chat_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


# ── Chat tracking for broadcast ────────────────────────────────────────────────

async def register_chat(chat_id: int, chat_title: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO chats (chat_id, chat_title) VALUES (?, ?)",
            (chat_id, chat_title)
        )
        await db.commit()


async def get_all_chats():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT chat_id FROM chats") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


# ── Private user tracking ──────────────────────────────────────────────────────

async def register_private_user(user_id: int, full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO private_users (user_id, full_name) VALUES (?, ?)",
            (user_id, full_name)
        )
        await db.commit()


# ── Known users tracking (for @username resolution) ────────────────────────────

async def remember_user(user_id: int, username: str, full_name: str):
    """Save/update a user's username so /approve @username can find them later."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO known_users (user_id, username, full_name) VALUES (?, ?, ?)",
            (user_id, username, full_name)
        )
        await db.commit()


async def find_user_by_username(username: str):
    """Look up a user_id by their username (case-insensitive)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, full_name FROM known_users WHERE LOWER(username) = LOWER(?)",
            (username,)
        ) as cursor:
            row = await cursor.fetchone()
            return row  # (user_id, full_name) or None
