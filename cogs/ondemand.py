"""On-demand: auto-download any TikTok link pasted in a channel the bot can see."""
import os

from discord.ext import commands

from src import tiktok
from src.discord_post import handle_url
from src.log import get_logger

log = get_logger(__name__)


class OnDemand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _workdir(self):
        return os.path.join(os.getenv("DATA_PATH", "./data"), "downloads")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        if not self.bot.cfg.get("auto_detect_links", True):
            return
        links = tiktok.find_links(message.content)
        if not links:
            return
        for url in links[:3]:  # cap per message
            try:
                async with message.channel.typing():
                    await handle_url(message.channel, url, self.bot.cfg, self.bot.cookies,
                                     self._workdir(), self.bot.proxy)
            except Exception:
                log.exception("auto-download failed for %s", url)


async def setup(bot):
    await bot.add_cog(OnDemand(bot))
