"""SQLite state (via aiosqlite) for tracked TikTok accounts.

One row per (account, channel) subscription. last_seen_id is the newest video id
we've already handled for that subscription; it's seeded on /tt add so we never
dump the back-catalogue.
"""
import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    username     TEXT NOT NULL,
    channel_id   TEXT NOT NULL,
    guild_id     TEXT,
    last_seen_id TEXT,
    enabled      INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (username, channel_id)
);
"""


async def init_db(path):
    async with aiosqlite.connect(path) as db:
        await db.execute(_SCHEMA)
        await db.commit()


async def add_account(path, username, channel_id, guild_id, last_seen_id):
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO accounts "
            "(username, channel_id, guild_id, last_seen_id, enabled) VALUES (?,?,?,?,1)",
            (username, channel_id, guild_id, last_seen_id),
        )
        await db.commit()


async def remove_account(path, username, channel_id=None):
    """Remove a subscription. If channel_id is None, removes the account everywhere.
    Returns number of rows deleted."""
    async with aiosqlite.connect(path) as db:
        if channel_id:
            cur = await db.execute(
                "DELETE FROM accounts WHERE username=? AND channel_id=?",
                (username, channel_id),
            )
        else:
            cur = await db.execute("DELETE FROM accounts WHERE username=?", (username,))
        await db.commit()
        return cur.rowcount


async def list_accounts(path, guild_id=None):
    async with aiosqlite.connect(path) as db:
        if guild_id:
            cur = await db.execute(
                "SELECT username, channel_id, last_seen_id, enabled "
                "FROM accounts WHERE guild_id=? ORDER BY username",
                (guild_id,),
            )
        else:
            cur = await db.execute(
                "SELECT username, channel_id, last_seen_id, enabled FROM accounts ORDER BY username"
            )
        return await cur.fetchall()


async def get_enabled(path):
    """All enabled subscriptions as (username, channel_id, last_seen_id) tuples."""
    async with aiosqlite.connect(path) as db:
        cur = await db.execute(
            "SELECT username, channel_id, last_seen_id FROM accounts WHERE enabled=1"
        )
        return await cur.fetchall()


async def update_last_seen(path, username, channel_id, last_seen_id):
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "UPDATE accounts SET last_seen_id=? WHERE username=? AND channel_id=?",
            (last_seen_id, username, channel_id),
        )
        await db.commit()
