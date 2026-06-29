# What this is (and what it'll do on your server)

Hey — I'd like to run a small personal bot on your server, next to the stuff you
already host. Here's exactly what it is and what it touches, so you can decide.

## What it does
It's a Discord bot that watches a list of **public** TikTok accounts and copies their
**new** videos into a private Discord channel — plus an on-demand "paste a link, get the
video" feature. That's it. Personal use, not redistribution.

## How it runs on your box
- **One Docker container** (`tiktokbot`) via its own `docker-compose`, in `~/tiktokbot/`.
  Same pattern as your other containers — nothing installed on the host itself.
- **Runs as a non-root user** (uid 1000) inside the container, not root.
- **Resource-capped** so it can never hog the machine or starve your other containers:
  - RAM: **512 MB** max
  - CPU: **2 cores** max
  - Processes: **256** max
- **`restart: unless-stopped`** so it survives reboots, like your other services.

## Network behaviour
- **Outbound only** — it talks to **TikTok** and **Discord**, nothing else.
- **No inbound/published ports.** It opens nothing on your server; nothing from the
  internet can reach it.
- Lives on its **own Docker network**; it doesn't touch your other containers.

## Footprint
- **Disk:** tiny — a small SQLite file. Videos are downloaded to a temp folder and
  **deleted right after** they're posted.
- **Bandwidth:** modest — a few small video downloads a day; the "check for new posts"
  requests are tiny.
- **CPU:** mostly idle. Brief blips only if a video is too big for Discord and needs
  re-compressing (capped at 2 cores).

## The IP question (the important one)
The bot reads TikTok like a logged-out visitor. The realistic worst case is TikTok
**rate-limiting** that request for a while — which only stops **the bot** from reading
TikTok. It does **not** affect your other containers, and it does **not** affect your own
TikTok use (you browse from your phone/home, a different IP). TikTok effectively never
*permanently* bans an IP for light read-only access like this.

To keep request volume low and polite, the bot:
- spreads its checks out (each account roughly every ~2.5 minutes, evenly paced + jitter),
- **automatically slows down** if TikTok starts pushing back, and
- can route **all** TikTok traffic through a **proxy** if you'd prefer your server's IP
  never be involved at all — then TikTok only ever sees the proxy. Your call.

## Security
- Runs unprivileged, resource-capped, no inbound ports, isolated network.
- Its secrets (a Discord token, and an optional throwaway-account cookie file) live in a
  `chmod 600` file, never in the image, never in git.

## If you ever want it gone
One command, leaves nothing behind:
```bash
cd ~/tiktokbot && docker compose down        # stop + remove the container
rm -rf ~/tiktokbot                            # (optional) wipe the files too
```
You can watch what it's doing anytime with `docker compose logs -f` (or in Portainer).

Totally fine if the answer's no — just wanted to give you the full picture. 🙏
