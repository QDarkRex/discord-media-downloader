# discord-media-downloader

A small, self-hosted Discord bot that brings TikTok and Instagram media into your server:

- **TikTok** - monitor accounts and auto-forward new videos to a channel/thread, plus
  paste-a-link on-demand downloads. Experimental Story monitoring is available behind an
  explicit Playwright + burner-cookie toggle.
- **Instagram** - on-demand downloads (`/ig get`) of posts, reels, and carousels
  (photos and videos) at native resolution, plus monitoring of new posts and stories.
- **Tag on new content** - optionally ping a role or person when a tracked account posts.

Built with Python + [discord.py](https://github.com/Rapptz/discord.py), packaged as a single
Docker container. Engines: [yt-dlp](https://github.com/yt-dlp/yt-dlp) (TikTok),
[gallery-dl](https://github.com/mikf/gallery-dl) (Instagram), and Playwright Chromium
for experimental TikTok Story discovery.

## Features

- **`/tt` group** - `add` / `remove` / `list` / `get <url>`. `add` takes optional
  `tag`, `channel`, and `type:` (`videos`, experimental `stories`, or `both`). Normal
  video monitoring uses yt-dlp; Story monitoring uses a separate slow Playwright watcher.
- **`/ig` group** - `get <url>`, plus `add` / `remove` / `list` to forward an account's
  new posts and/or stories (`type:` posts | stories | both), with the same tag + thread
  options. Instagram monitoring is sharded across burner cookies and polled slowly.
- **Auto-detect** - paste a TikTok or Instagram link in any channel the bot can see and
  it downloads it automatically, then suppresses Discord's redundant preview embed
  (toggles in `configs.yml`).
- **Upload-cap aware** - oversized videos are ffmpeg-compressed to fit Discord's limit;
  if a file still will not fit, the bot posts the source link instead.
- **Hardened** - non-root container, RAM/CPU/PID caps, subprocess timeouts, optional proxy.

## Quick start

```bash
cp .env.example .env      # paste your BOT_TOKEN
docker compose up -d --build
docker compose logs -f    # look for "is online" and "synced N slash command(s)"
```

In the Discord Developer Portal: enable the **Message Content Intent**, and invite the bot
with the `bot` + `applications.commands` scopes.

## Configuration

`configs.yml` is mounted into the container, so settings-only changes need just
`docker compose restart`. Code or dependency changes need `docker compose up -d --build`.

| Setting | What it does |
| --- | --- |
| `max_upload_mb` | Discord upload cap. 10 (none), 50 (Level 2 boost), 100 (Level 3). |
| `auto_detect_links` | Auto-download TikTok/Instagram links pasted in chat. |
| `sweep_target_seconds` | How often each tracked TikTok video account is re-checked. |
| `tiktok_story_enabled` | Experimental TikTok Story monitor. Requires burner cookies. |
| `tiktok_story_sweep_target_seconds` | How often each tracked TikTok Story account is re-checked. Keep this slow. |
| `compress_oversize` | ffmpeg-compress videos over the cap before falling back to a link. |
| `download_timeout` / `max_files_per_post` | Instagram download guardrails. |

### Cookies

- **TikTok videos** run fine anonymously. `TIKTOK_COOKIES` is optional, for reliability at scale.
- **TikTok Stories** need `TIKTOK_STORY_COOKIES` (or they fall back to `TIKTOK_COOKIES`) from
  a logged-in burner account. The watcher uses Playwright to open the profile and click the
  story/avatar entry point, so the burner may appear as a story viewer and this can break when
  TikTok changes the web UI.
- **Instagram** requires login to view individual posts. `/ig` needs `IG_COOKIES` set to a
  Netscape `cookies.txt` exported from a logged-in burner account.

See [`DEPLOY.md`](DEPLOY.md) for deploying to a server.

## Notes

Personal, self-hosted use. Respect the source platforms' terms and the rights of creators
whose content you download.
