"""Turn a slash-command mention target into a stored (type, id) pair, and build the
ping line + AllowedMentions used when forwarding a new item."""
import discord


def parse_target(target):
    """`target` is a discord.Role, discord.Member/User, or None (from a MENTIONABLE
    app-command option). Returns (mention_type, mention_id) for the DB."""
    if target is None:
        return (None, None)
    if isinstance(target, discord.Role):
        if target.is_default():          # the @everyone role
            return ("everyone", None)
        return ("role", str(target.id))
    return ("user", str(target.id))      # Member / User


def mention_string(mention_type, mention_id):
    if mention_type == "everyone":
        return "@everyone"
    if mention_type == "role":
        return f"<@&{mention_id}>"
    if mention_type == "user":
        return f"<@{mention_id}>"
    return ""


def label(mention_type, mention_id):
    """Human-readable form for /list output (no actual ping)."""
    s = mention_string(mention_type, mention_id)
    return f" — pings {s}" if s else ""


def _allowed(mention_type):
    if mention_type == "everyone":
        return discord.AllowedMentions(everyone=True)
    if mention_type == "role":
        return discord.AllowedMentions(roles=True)
    if mention_type == "user":
        return discord.AllowedMentions(users=True)
    return discord.AllowedMentions.none()


async def announce(channel, mention_type, mention_id, text):
    """Post the ping/announcement line. Mentions only resolve because we pass a
    matching AllowedMentions, so stray text can never accidentally ping."""
    prefix = mention_string(mention_type, mention_id)
    content = f"{prefix} {text}".strip() if prefix else text
    await channel.send(content=content, allowed_mentions=_allowed(mention_type))
