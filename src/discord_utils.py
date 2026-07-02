"""Small Discord helpers shared by the on-demand cogs."""
import discord

from src.log import get_logger

log = get_logger(__name__)

_warned_perms = False


async def suppress_link_embeds(message, cfg):
    """Remove Discord's auto-generated link-preview embed from `message`.

    Called after the bot has reposted the media, so Discord has already had time
    to generate the embed and setting the flag removes it. Editing someone else's
    message needs the Manage Messages permission; without it we warn once and skip.
    """
    global _warned_perms
    if not cfg.get("suppress_link_embeds", True):
        return
    try:
        await message.edit(suppress=True)
    except discord.Forbidden:
        if not _warned_perms:
            _warned_perms = True
            log.warning("can't suppress link embeds — give the bot the 'Manage Messages' "
                        "permission in that channel/server")
    except discord.HTTPException:
        pass  # message deleted, already suppressed, etc. — nothing to do
