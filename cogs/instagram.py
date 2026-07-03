"""The whole `/ig` command group + Instagram post monitoring.

Commands (mirroring `/tt`):
  /ig get <url>                 on-demand download of a post/reel/carousel
  /ig add <user> [chan] [tag]   forward an account's NEW posts (optionally ping a role/person)
  /ig remove <user> [chan]
  /ig list

Plus a passive listener that auto-downloads Instagram links pasted in chat.

Monitoring is sharded across one or more "burners" (each a cookie+proxy pair). Each
burner runs its OWN poller in parallel and only handles the accounts assigned to it
(by a stable hash of the username), so load — and ban risk — is split across separate
logins/IPs. Polling is deliberately much slower than TikTok's: Instagram flags
aggressive automated access.
"""
import asyncio
import hashlib
import os
import random
from collections import defaultdict
from typing import Optional, Union

import discord
from discord import app_commands
from discord.ext import commands

from src import db, instagram, mentions, monitor
from src.discord_utils import suppress_link_embeds
from src.instagram_post import handle_url
from src.log import get_logger

log = get_logger(__name__)

Target = Union[discord.TextChannel, discord.Thread]
Tag = Union[discord.Role, discord.Member]


def _short(e):
    msg = str(e).strip()
    return msg.splitlines()[-1] if msg else e.__class__.__name__


class Instagram(commands.Cog):
    ig = app_commands.Group(name="ig", description="Download Instagram media & forward new posts")

    def __init__(self, bot):
        self.bot = bot
        self._poller_tasks = []
        # one adaptive-backoff factor per burner
        self._backoff = [1.0] * max(len(getattr(bot, "ig_burners", [])), 1)

    async def cog_load(self):
        # One poller per burner — they run in parallel, each on its own cookie/proxy.
        for bi in range(len(self.bot.ig_burners)):
            self._poller_tasks.append(asyncio.create_task(self._run_poller(bi)))

    def cog_unload(self):
        for t in self._poller_tasks:
            t.cancel()

    def _workdir(self):
        return os.path.join(os.getenv("DATA_PATH", "./data"), "downloads")

    def _burner_for(self, username):
        """Stable account -> burner assignment (survives restarts, so an account never
        hops burners). Returns (index, cookies, proxy) or None if no burners."""
        burners = self.bot.ig_burners
        if not burners:
            return None
        idx = int(hashlib.md5(username.encode()).hexdigest(), 16) % len(burners)
        b = burners[idx]
        return (idx, b["cookies"], b["proxy"])

    # ---- commands ---------------------------------------------------------

    @ig.command(name="get",
                description="Download an Instagram post/reel/carousel at native resolution")
    @app_commands.describe(url="An instagram.com post, reel, or tv link")
    async def get(self, interaction: discord.Interaction, url: str):
        if not instagram.find_links(url):
            await interaction.response.send_message(
                "That doesn't look like an Instagram link.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        try:
            await handle_url(interaction.channel, url, self.bot.cfg, self.bot.ig_cookies,
                             self._workdir(), self.bot.ig_proxy)
            try:
                await interaction.delete_original_response()
            except discord.HTTPException:
                pass
        except Exception:
            log.exception("/ig get failed for %s", url)
            try:
                await interaction.followup.send(
                    "Sorry — I couldn't download that one. Check the link, or the "
                    "bot may need valid Instagram cookies.", ephemeral=True)
            except discord.HTTPException:
                pass

    @ig.command(name="add", description="Forward an Instagram account's new posts")
    @app_commands.describe(username="Instagram @username",
                           channel="Where to post (default: this channel/thread)",
                           tag="Optional role or person to ping on each new post")
    async def add(self, interaction: discord.Interaction, username: str,
                  channel: Optional[Target] = None, tag: Optional[Tag] = None):
        await interaction.response.defer(ephemeral=True)
        username = instagram.normalize_username(username)
        burner = self._burner_for(username)
        if burner is None:
            await interaction.followup.send(
                "❌ No Instagram cookies are configured, so monitoring is off. "
                "Set `IG_COOKIES` to a burner cookies.txt first.", ephemeral=True)
            return
        _bi, cookies, proxy = burner
        target = channel or interaction.channel
        mtype, mid = mentions.parse_target(tag)
        # Seed baseline = current newest post id (via this account's assigned burner).
        try:
            recent = await asyncio.to_thread(instagram.list_recent, username, 1, cookies, proxy)
        except Exception as e:
            log.warning("ig add: couldn't read @%s (%s)", username, _short(e))
            await interaction.followup.send(
                f"❌ Couldn't read **@{username}**. Check the spelling, and that the bot's "
                f"Instagram cookies are valid (private accounts need the burner to follow them).",
                ephemeral=True)
            return
        baseline = recent[0]["id"] if recent else None
        await db.add_subscription(self.bot.db_path, "instagram", username, str(target.id),
                                  str(interaction.guild_id), "post", mtype, mid, baseline)
        ping = f" and ping {mentions.mention_string(mtype, mid)}" if mtype else ""
        await interaction.followup.send(
            f"✅ Watching **@{username}** → {target.mention}{ping}. New posts will show up there.\n"
            f"_(Instagram is polled slowly to keep the account safe — expect new posts within "
            f"~10–30 min depending on how many accounts are watched.)_",
            ephemeral=True)

    @ig.command(name="remove", description="Stop forwarding an Instagram account")
    @app_commands.describe(username="Instagram @username", channel="Only this channel (default: everywhere)")
    async def remove(self, interaction: discord.Interaction, username: str,
                     channel: Optional[Target] = None):
        await interaction.response.defer(ephemeral=True)
        username = instagram.normalize_username(username)
        n = await db.remove_subscription(self.bot.db_path, "instagram", username,
                                         str(channel.id) if channel else None)
        if n:
            await interaction.followup.send(f"✅ Removed **@{username}** ({n} subscription(s)).", ephemeral=True)
        else:
            await interaction.followup.send(f"ℹ️ **@{username}** wasn't being watched.", ephemeral=True)

    @ig.command(name="list", description="Show watched Instagram accounts")
    async def list_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rows = await db.list_subscriptions(self.bot.db_path, "instagram", str(interaction.guild_id))
        if not rows:
            await interaction.followup.send("No Instagram accounts watched yet. Use `/ig add`.", ephemeral=True)
            return
        lines = []
        for username, channel_id, _ctype, mtype, mid, _last, enabled in rows:
            mark = "" if enabled else " *(paused)*"
            lines.append(f"• **@{username}** → <#{channel_id}>{mentions.label(mtype, mid)}{mark}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    # ---- auto-detect listener --------------------------------------------

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

    # ---- paced scheduler (per-burner, slow) -------------------------------

    def _spacing(self, account_count):
        target = float(self.bot.cfg.get("ig_sweep_target_seconds", 900))
        floor = float(self.bot.cfg.get("ig_min_request_spacing", 20))
        return max(floor, target / max(account_count, 1))

    def _jittered(self, spacing):
        j = float(self.bot.cfg.get("ig_request_jitter", 5))
        return max(1.0, spacing + random.uniform(-j, j))

    async def _run_poller(self, bi):
        await self.bot.wait_until_ready()
        log.info("instagram poller %d alive (of %d burner(s))", bi, len(self.bot.ig_burners))
        while not self.bot.is_closed():
            try:
                await self._one_sweep(bi)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("ig poller %d sweep crashed; backing off 30s", bi)
                await asyncio.sleep(30)

    async def _one_sweep(self, bi):
        cookies = self.bot.ig_burners[bi]["cookies"]
        proxy = self.bot.ig_burners[bi]["proxy"]

        rows = await db.get_enabled(self.bot.db_path, "instagram", "post")
        by_user = defaultdict(list)
        for username, channel_id, mtype, mid, last_seen in rows:
            # Only handle accounts assigned to THIS burner.
            if self._burner_for(username)[0] != bi:
                continue
            by_user[username].append((channel_id, mtype, mid, last_seen))
        if not by_user:
            await asyncio.sleep(30)  # nothing on this burner yet — idle
            return

        spacing = self._spacing(len(by_user)) * self._backoff[bi]
        failures = 0
        for username, subs in by_user.items():
            if not await self._check_account(username, subs, cookies, proxy):
                failures += 1
            await asyncio.sleep(self._jittered(spacing))

        if failures / len(by_user) >= 0.3:
            self._backoff[bi] = min(self._backoff[bi] * 2, 8.0)
            log.warning("ig poll[%d]: %d/%d accounts failed — slowing down (spacing x%.0f)",
                        bi, failures, len(by_user), self._backoff[bi])
        elif failures == 0 and self._backoff[bi] > 1.0:
            self._backoff[bi] = max(self._backoff[bi] / 2, 1.0)
            log.info("ig poll[%d]: recovered — easing back (spacing x%.1f)", bi, self._backoff[bi])

    async def _check_account(self, username, subs, cookies, proxy):
        scan = int(self.bot.cfg.get("ig_playlist_scan_count", 3))
        try:
            recent = await asyncio.to_thread(instagram.list_recent, username, scan, cookies, proxy)
        except Exception as e:
            log.warning("ig poll: couldn't list @%s (%s)", username, _short(e))
            return False
        await monitor.forward_new(self.bot, "instagram", username, subs, recent, handle_url,
                                  self._workdir(), cookies, proxy, "Instagram")
        return True


async def setup(bot):
    await bot.add_cog(Instagram(bot))
