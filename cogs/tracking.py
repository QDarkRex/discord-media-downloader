"""/tt slash command group + TikTok video/story monitoring.

Normal TikTok videos still use the proven yt-dlp profile listing path. TikTok
Stories are experimental: yt-dlp cannot list them, so story discovery uses
Playwright in src/tiktok_story.py and runs in a separate, slower poller.
"""
import asyncio
import os
import random
from collections import defaultdict
from typing import Optional, Union

import discord
from discord import app_commands
from discord.ext import commands

from src import db, mentions, monitor, tiktok, tiktok_story
from src.discord_post import handle_url
from src.log import get_logger

log = get_logger(__name__)

Target = Union[discord.TextChannel, discord.Thread]
Tag = Union[discord.Role, discord.Member]


def _short(e):
    msg = str(e).strip()
    return msg.splitlines()[-1] if msg else e.__class__.__name__


class Tracking(commands.Cog):
    tt = app_commands.Group(
        name="tt",
        description="Forward TikTok videos and experimental stories to Discord",
    )

    def __init__(self, bot):
        self.bot = bot
        self._poller_task = None
        self._story_poller_task = None
        self._backoff = 1.0
        self._story_backoff = 1.0

    async def cog_load(self):
        self._poller_task = asyncio.create_task(self._run_poller())
        if self.bot.cfg.get("tiktok_story_enabled", False):
            self._story_poller_task = asyncio.create_task(self._run_story_poller())

    def cog_unload(self):
        if self._poller_task:
            self._poller_task.cancel()
        if self._story_poller_task:
            self._story_poller_task.cancel()

    def _workdir(self):
        return os.path.join(os.getenv("DATA_PATH", "./data"), "downloads")

    # ---- commands ---------------------------------------------------------

    @tt.command(name="add", description="Track a TikTok account and post new videos/stories")
    @app_commands.describe(username="TikTok @username",
                           channel="Where to post (default: this channel/thread)",
                           tag="Optional role or person to ping on each new item",
                           type="What to forward (default: videos)")
    @app_commands.choices(type=[
        app_commands.Choice(name="videos", value="post"),
        app_commands.Choice(name="stories (experimental)", value="story"),
        app_commands.Choice(name="both", value="both"),
    ])
    async def add(self, interaction: discord.Interaction, username: str,
                  channel: Optional[Target] = None, tag: Optional[Tag] = None,
                  type: Optional[app_commands.Choice[str]] = None):
        await interaction.response.defer(ephemeral=True)
        username = tiktok.normalize_username(username)
        target = channel or interaction.channel
        mtype, mid = mentions.parse_target(tag)
        kind = type.value if type else "post"
        wants_videos = kind in ("post", "both")
        wants_stories = kind in ("story", "both")
        added = []

        if wants_videos:
            try:
                recent = await asyncio.to_thread(tiktok.list_recent, username, 1,
                                                 self.bot.cookies, self.bot.proxy)
            except Exception as e:
                log.warning("add: couldn't read @%s (%s)", username, _short(e))
                await interaction.followup.send(
                    f"Couldn't read **@{username}**. Check the spelling and that the account is public.",
                    ephemeral=True)
                return
            baseline = recent[0]["id"] if recent else None
            await db.add_subscription(self.bot.db_path, "tiktok", username, str(target.id),
                                      str(interaction.guild_id), "post", mtype, mid, baseline)
            added.append("videos")

        if wants_stories:
            if not self.bot.cfg.get("tiktok_story_enabled", False):
                await interaction.followup.send(
                    "TikTok story monitoring is disabled. Set `tiktok_story_enabled: true` "
                    "in `configs.yml` after adding burner cookies.", ephemeral=True)
                return
            if not self.bot.tiktok_story_cookies:
                await interaction.followup.send(
                    "TikTok story monitoring needs `TIKTOK_STORY_COOKIES` "
                    "(or `TIKTOK_COOKIES`).", ephemeral=True)
                return
            try:
                stories = await tiktok_story.list_stories(
                    username, self.bot.tiktok_story_cookies, self.bot.tiktok_story_proxy,
                    float(self.bot.cfg.get("tiktok_story_timeout", 45)))
            except Exception as e:
                log.warning("add: couldn't check TikTok stories @%s (%s)", username, _short(e))
                stories = []
            await db.add_subscription(self.bot.db_path, "tiktok", username, str(target.id),
                                      str(interaction.guild_id), "story", mtype, mid,
                                      stories[0]["id"] if stories else None)
            added.append("stories")

        ping = f" and ping {mentions.mention_string(mtype, mid)}" if mtype else ""
        await interaction.followup.send(
            f"Tracking **@{username}** ({' + '.join(added)}) -> {target.mention}{ping}. "
            f"New items will post there.",
            ephemeral=True)

    @tt.command(name="remove", description="Stop tracking a TikTok account")
    @app_commands.describe(username="TikTok @username", channel="Only this channel (default: everywhere)")
    async def remove(self, interaction: discord.Interaction, username: str,
                     channel: Optional[Target] = None):
        await interaction.response.defer(ephemeral=True)
        username = tiktok.normalize_username(username)
        chan = str(channel.id) if channel else None
        n = 0
        for ctype in ("post", "story"):
            n += await db.remove_subscription(self.bot.db_path, "tiktok", username, chan, ctype)
        if n:
            await interaction.followup.send(f"Removed **@{username}** ({n} subscription(s)).", ephemeral=True)
        else:
            await interaction.followup.send(f"**@{username}** wasn't being tracked.", ephemeral=True)

    @tt.command(name="list", description="Show tracked TikTok accounts")
    async def list_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rows = await db.list_subscriptions(self.bot.db_path, "tiktok", str(interaction.guild_id))
        if not rows:
            await interaction.followup.send("No accounts tracked yet. Use `/tt add`.", ephemeral=True)
            return
        lines = []
        for username, channel_id, ctype, mtype, mid, _last, enabled in rows:
            mark = "" if enabled else " *(paused)*"
            kind = "stories" if ctype == "story" else "videos"
            lines.append(f"- **@{username}** ({kind}) -> <#{channel_id}>{mentions.label(mtype, mid)}{mark}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @tt.command(name="get", description="Download and post one TikTok video now")
    @app_commands.describe(url="A TikTok video link")
    async def get(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer()
        try:
            await handle_url(interaction.channel, url, self.bot.cfg, self.bot.cookies,
                             self._workdir(), self.bot.proxy)
            await interaction.followup.send("Done.", ephemeral=True)
        except Exception:
            log.exception("/tt get failed for %s", url)
            await interaction.followup.send("Couldn't download that link.", ephemeral=True)

    # ---- normal video scheduler ------------------------------------------

    def _spacing(self, account_count):
        target = float(self.bot.cfg.get("sweep_target_seconds", 150))
        floor = float(self.bot.cfg.get("min_request_spacing", 1.5))
        return max(floor, target / max(account_count, 1))

    def _jittered(self, spacing):
        j = float(self.bot.cfg.get("request_jitter", 0.5))
        return max(0.1, spacing + random.uniform(-j, j))

    async def _run_poller(self):
        await self.bot.wait_until_ready()
        log.info("tiktok poller alive (paced scheduler)")
        while not self.bot.is_closed():
            try:
                await self._one_sweep()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("poller sweep crashed; backing off 10s")
                await asyncio.sleep(10)

    async def _one_sweep(self):
        rows = await db.get_enabled(self.bot.db_path, "tiktok", "post")
        by_user = defaultdict(list)
        for username, channel_id, mtype, mid, last_seen in rows:
            by_user[username].append((channel_id, mtype, mid, last_seen))
        if not by_user:
            await asyncio.sleep(10)
            return

        spacing = self._spacing(len(by_user)) * self._backoff
        failures = 0
        for username, subs in by_user.items():
            if not await self._check_account(username, subs):
                failures += 1
            await asyncio.sleep(self._jittered(spacing))

        if failures / len(by_user) >= 0.3:
            self._backoff = min(self._backoff * 2, 8.0)
            log.warning("poll: %d/%d accounts failed this sweep; slowing down (spacing x%.0f)",
                        failures, len(by_user), self._backoff)
        elif failures == 0 and self._backoff > 1.0:
            self._backoff = max(self._backoff / 2, 1.0)
            log.info("poll: recovered; easing back (spacing x%.1f)", self._backoff)

    async def _check_account(self, username, subs):
        scan = int(self.bot.cfg.get("playlist_scan_count", 5))
        try:
            recent = await asyncio.to_thread(tiktok.list_recent, username, scan,
                                             self.bot.cookies, self.bot.proxy)
        except Exception as e:
            log.warning("poll: couldn't list @%s (%s)", username, _short(e))
            return False
        await monitor.forward_new(self.bot, "tiktok", username, subs, recent, handle_url,
                                  self._workdir(), self.bot.cookies, self.bot.proxy, "TikTok")
        return True

    # ---- experimental story scheduler ------------------------------------

    def _story_spacing(self, account_count):
        target = float(self.bot.cfg.get("tiktok_story_sweep_target_seconds", 1800))
        floor = float(self.bot.cfg.get("tiktok_story_min_request_spacing", 45))
        return max(floor, target / max(account_count, 1))

    def _story_jittered(self, spacing):
        j = float(self.bot.cfg.get("tiktok_story_request_jitter", 10))
        return max(5.0, spacing + random.uniform(-j, j))

    async def _run_story_poller(self):
        await self.bot.wait_until_ready()
        if not self.bot.tiktok_story_cookies:
            log.warning("tiktok story poller disabled: no burner cookies configured")
            return
        log.info("tiktok story poller alive (experimental Playwright watcher)")
        while not self.bot.is_closed():
            try:
                await self._one_story_sweep()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("story poller sweep crashed; backing off 60s")
                await asyncio.sleep(60)

    async def _one_story_sweep(self):
        rows = await db.get_enabled(self.bot.db_path, "tiktok", "story")
        by_user = defaultdict(list)
        for username, channel_id, mtype, mid, last_seen in rows:
            by_user[username].append((channel_id, mtype, mid, last_seen))
        if not by_user:
            await asyncio.sleep(30)
            return

        spacing = self._story_spacing(len(by_user)) * self._story_backoff
        failures = 0
        for username, subs in by_user.items():
            if not await self._check_story_account(username, subs):
                failures += 1
            await asyncio.sleep(self._story_jittered(spacing))

        if failures / len(by_user) >= 0.3:
            self._story_backoff = min(self._story_backoff * 2, 8.0)
            log.warning("story poll: %d/%d accounts failed; slowing down (spacing x%.0f)",
                        failures, len(by_user), self._story_backoff)
        elif failures == 0 and self._story_backoff > 1.0:
            self._story_backoff = max(self._story_backoff / 2, 1.0)
            log.info("story poll: recovered; easing back (spacing x%.1f)", self._story_backoff)

    async def _check_story_account(self, username, subs):
        try:
            recent = await tiktok_story.list_stories(
                username, self.bot.tiktok_story_cookies, self.bot.tiktok_story_proxy,
                float(self.bot.cfg.get("tiktok_story_timeout", 45)))
        except Exception as e:
            log.warning("story poll: couldn't discover @%s stories (%s)", username, _short(e))
            return False
        await monitor.forward_new(self.bot, "tiktok", username, subs, recent, handle_url,
                                  self._workdir(), self.bot.tiktok_story_cookies,
                                  self.bot.tiktok_story_proxy, "TikTok story")
        return True


async def setup(bot):
    await bot.add_cog(Tracking(bot))
