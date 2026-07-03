"""Shared monitoring logic for both platforms: given an account's recent items and
its subscriptions, forward anything newer than each subscription's last_seen marker,
pinging the configured role/user, and advance the marker only past items actually
delivered (so a transient failure retries next sweep instead of dropping an item).
"""
from src import db, mentions
from src.log import get_logger

log = get_logger(__name__)


def _short(e):
    msg = str(e).strip()
    return msg.splitlines()[-1] if msg else e.__class__.__name__


async def forward_new(bot, platform, username, subs, recent, handle_url,
                      workdir, cookies, proxy, label):
    """subs:   list of (channel_id, mention_type, mention_id, last_seen)
    recent:    [{"id", "url"}, ...] most-recent first
    handle_url: async (channel, url, cfg, cookies, workdir, proxy) -> ...
    label:     'TikTok' / 'Instagram' — used in the ping line + logs
    """
    if not recent:
        return
    newest_id = recent[0]["id"]

    for channel_id, mtype, mid, last_seen in subs:
        if last_seen is None:
            # No baseline (account was unreachable at add-time) — set it now, don't dump.
            await db.update_last_seen(bot.db_path, platform, username, channel_id, newest_id)
            continue

        new_items = []
        for item in recent:                 # most-recent first
            if item["id"] == last_seen:
                break
            new_items.append(item)
        if not new_items:
            continue

        channel = bot.get_channel(int(channel_id))
        if channel is None:
            log.warning("poll: channel %s for @%s not found (bot removed / no access?)",
                        channel_id, username)
            continue

        for item in reversed(new_items):    # oldest-first
            try:
                if mtype:
                    await mentions.announce(channel, mtype, mid,
                                            f"new {label} post from **@{username}**")
                await handle_url(channel, item["url"], bot.cfg, cookies, workdir, proxy)
            except Exception as e:
                log.warning("poll: forward failed for @%s %s (%s); will retry next sweep",
                            username, item["id"], _short(e))
                break
            await db.update_last_seen(bot.db_path, platform, username, channel_id, item["id"])
            log.info("forwarded %s @%s %s -> channel %s", label, username, item["id"], channel_id)
