import asyncio
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from src import db
from src.config import load_config
from src.log import get_logger, setup_logging

load_dotenv()
log = get_logger(__name__)


def _resolve_cookies():
    path = os.getenv("TIKTOK_COOKIES") or ""
    path = path.strip()
    if not path:
        return None
    if not os.path.exists(path):
        log.warning("TIKTOK_COOKIES set to %s but file not found — continuing without cookies", path)
        return None
    log.info("using TikTok cookies from %s", path)
    return path


def _resolve_ig_cookies():
    path = (os.getenv("IG_COOKIES") or "").strip()
    if not path:
        log.info("IG_COOKIES not set — running anonymously. On-demand downloads of public "
                 "posts/reels usually work; set IG_COOKIES if you hit 'no media' or rate-limits.")
        return None
    if not os.path.exists(path):
        log.warning("IG_COOKIES set to %s but file not found — continuing without cookies", path)
        return None
    log.info("using Instagram cookies from %s", path)
    return path


async def _run():
    setup_logging()
    cfg = load_config()

    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN is missing — set it in .env")

    data_path = os.getenv("DATA_PATH", "./data")
    os.makedirs(os.path.join(data_path, "downloads"), exist_ok=True)
    db_path = os.path.join(data_path, "tiktok.db")
    await db.init_db(db_path)

    intents = discord.Intents.default()
    intents.message_content = True  # needed to read pasted TikTok links

    bot = commands.Bot(command_prefix=cfg.get("prefix", "!"), intents=intents)
    bot.cfg = cfg
    bot.db_path = db_path
    bot.cookies = _resolve_cookies()
    bot.proxy = (os.getenv("TIKTOK_PROXY") or "").strip() or None
    if bot.proxy:
        log.info("routing TikTok requests through a proxy")  # don't log the URL (may hold creds)
    bot.ig_cookies = _resolve_ig_cookies()
    bot.ig_proxy = (os.getenv("IG_PROXY") or "").strip() or None
    if bot.ig_proxy:
        log.info("routing Instagram requests through a proxy")

    @bot.event
    async def on_ready():
        log.info("%s is online", bot.user)
        try:
            synced = await bot.tree.sync()
            log.info("synced %d slash command(s)", len(synced))
        except Exception:
            log.exception("slash command sync failed")

    async with bot:
        for fn in sorted(os.listdir("./cogs")):
            if fn.endswith(".py") and fn != "__init__.py":
                await bot.load_extension(f"cogs.{fn[:-3]}")
                log.info("loaded cog %s", fn)
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(_run())
