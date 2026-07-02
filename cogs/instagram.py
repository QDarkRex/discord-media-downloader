"""On-demand Instagram downloader, living alongside the TikTok /tt commands.

Primary interface: the `/ig` slash command — paste a post/reel/carousel link and
the bot uploads every photo/video at native resolution. As a convenience it also
auto-downloads Instagram links pasted into chat (shares the `auto_detect_links`
toggle with the TikTok paste-detect).
"""
import os

import discord
from discord import app_commands
from discord.ext import commands

from src import instagram
from src.discord_utils import suppress_link_embeds
from src.instagram_post import handle_url
from src.log import get_logger

log = get_logger(__name__)


class Instagram(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _workdir(self):
        return os.path.join(os.getenv("DATA_PATH", "./data"), "downloads")

    @app_commands.command(
        name="ig",
        description="Download an Instagram post/reel/carousel (photo or video) at native resolution",
    )
    @app_commands.describe(url="An instagram.com post, reel, or tv link")
    async def ig(self, interaction: discord.Interaction, url: str):
        if not instagram.find_links(url):
            await interaction.response.send_message(
                "That doesn't look like an Instagram link.", ephemeral=True)
            return
        # Posting media can take a while (download + maybe compress) — defer first.
        await interaction.response.defer(thinking=True)
        try:
            await handle_url(interaction.channel, url, self.bot.cfg, self.bot.ig_cookies,
                             self._workdir(), self.bot.ig_proxy)
            # Drop the "thinking…" placeholder; the media is now in the channel.
            try:
                await interaction.delete_original_response()
            except discord.HTTPException:
                pass
        except Exception:
            log.exception("/ig failed for %s", url)
            try:
                await interaction.followup.send(
                    "Sorry — I couldn't download that one. Check the link, or the "
                    "bot may need valid Instagram cookies.", ephemeral=True)
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        if not self.bot.cfg.get("auto_detect_links", True):
            return
        links = instagram.find_links(message.content)
        if not links:
            return
        for url in links[:3]:  # cap per message
            try:
                async with message.channel.typing():
                    await handle_url(message.channel, url, self.bot.cfg, self.bot.ig_cookies,
                                     self._workdir(), self.bot.ig_proxy)
            except Exception:
                log.exception("auto-download failed for %s", url)
        # Strip Discord's redundant link-preview embed now that we've reposted it.
        await suppress_link_embeds(message, self.bot.cfg)


async def setup(bot):
    await bot.add_cog(Instagram(bot))
