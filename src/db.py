"""SQLite state (via aiosqlite) for tracked accounts across platforms.

One row per (platform, account, channel, content_type) subscription. `last_seen_id`
is the newest item id already handled for that subscription; seeded on add so we never
dump the back-catalogue. Optional per-subscription mention (role / user / everyone) is
pinged when a new item is forwarded.

`content_type` is 'post' today; 'story' is reserved for Phase 2. The old TikTok-only
`accounts` table (if present from an earlier version) is migrated in on first run.
"""
import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    platform     TEXT NOT NULL DEFAULT 'tiktok',
    username     TEXT NOT NULL,
    channel_id   TEXT NOT NULL,
    guild_id     TEXT,
    content_type TEXT NOT NULL DEFAULT 'post',
    mention_type TEXT,           -- 'role' | 'user' | 'everyone' | NULL
    mention_id   TEXT,           -- role/user id ('everyone'/none -> NULL)
    last_seen_id TEXT,
    enabled      INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (platform, username, channel_id, content_type)
);
"""


async def init_db(path):
    async with aiosqlite.connect(path) as db:
        await db.execute(_SCHEMA)
        # Migrate the old TikTok-only `accounts` table (username, channel_id, guild_id,
        # last_seen_id, enabled) if it exists. INSERT OR IGNORE keeps this idempotent.
        cur = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'")
        if await cur.fetchone():
            await db.execute(
                "INSERT OR IGNORE INTO subscriptions "
                "(platform, username, channel_id, guild_id, content_type, last_seen_id, enabled) "
                "SELECT 'tiktok', username, channel_id, guild_id, 'post', last_seen_id, enabled "
                "FROM accounts")
        await db.commit()


async def add_subscription(path, platform, username, channel_id, guild_id,
                           content_type="post", mention_type=None, mention_id=None,
                           last_seen_id=None):
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO subscriptions "
            "(platform, username, channel_id, guild_id, content_type, "
            " mention_type, mention_id, last_seen_id, enabled) "
            "VALUES (?,?,?,?,?,?,?,?,1)",
            (platform, username, channel_id, guild_id, content_type,
             mention_type, mention_id, last_seen_id),
        )
        await db.commit()


async def remove_subscription(path, platform, username, channel_id=None, content_type="post"):
    """Remove a subscription. channel_id=None removes it from every channel.
    Returns number of rows deleted."""
    async with aiosqlite.connect(path) as db:
        if channel_id:
            cur = await db.execute(
                "DELETE FROM subscriptions WHERE platform=? AND username=? "
                "AND channel_id=? AND content_type=?",
                (platform, username, channel_id, content_type),
            )
        else:
            cur = await db.execute(
                "DELETE FROM subscriptions WHERE platform=? AND username=? AND content_type=?",
                (platform, username, content_type),
            )
        await db.commit()
        return cur.rowcount


async def list_subscriptions(path, platform, guild_id=None):
    q = ("SELECT username, channel_id, content_type, mention_type, mention_id, "
         "last_seen_id, enabled FROM subscriptions WHERE platform=?")
    args = [platform]
    if guild_id:
        q += " AND guild_id=?"
        args.append(guild_id)
    q += " ORDER BY username"
    async with aiosqlite.connect(path) as db:
        cur = await db.execute(q, args)
        return await cur.fetchall()


async def get_enabled(path, platform, content_type="post"):
    """Enabled subs as (username, channel_id, mention_type, mention_id, last_seen_id)."""
    async with aiosqlite.connect(path) as db:
        cur = await db.execute(
            "SELECT username, channel_id, mention_type, mention_id, last_seen_id "
            "FROM subscriptions WHERE platform=? AND content_type=? AND enabled=1",
            (platform, content_type),
        )
        return await cur.fetchall()


async def update_last_seen(path, platform, username, channel_id, last_seen_id,
                           content_type="post"):
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "UPDATE subscriptions SET last_seen_id=? "
            "WHERE platform=? AND username=? AND channel_id=? AND content_type=?",
            (last_seen_id, platform, username, channel_id, content_type),
        )
        await db.commit()
