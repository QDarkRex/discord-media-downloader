# Changelog

Reverse-chronological summary of what shipped. See `git log` for full detail and
[`STATUS.md`](STATUS.md) for what is currently deployed vs. pending.

## Unreleased on the server (pushed to `main`, not yet deployed)

- **Experimental TikTok story watcher** (`f58e45a`) — yt-dlp can't list TikTok stories, so
  `src/tiktok_story.py` uses a logged-in Playwright/Chromium session to open a profile, click the
  avatar/story entry, and sniff `tiktok.com/@user/video/<id>` URLs from network responses. Opt-in
  (`tiktok_story_enabled`, default off) + `TIKTOK_STORY_COOKIES`. Separate slow poller in
  `cogs/tracking.py`. **Needs a `mem_limit` bump before enabling — see STATUS.md.**
- **Instagram story ID-mismatch fix** (`c07011c`) — `download_stories` now reads the item id from the
  metadata sidecar (`media_id`/`id`, filename-digits fallback), and `_forward_stories` computes new items
  from the downloaded set itself instead of intersecting list-vs-download ids (which could silently skip &
  advance past items).

## Deployed

- **`AGENTS.md`** handoff doc (`a211e5b`).
- **TikTok native resolution** (`bee6f9e`) — pick highest-res rendition, not h264-capped 720p (TikTok 1080p
  is often h265-only). `tiktok_native` config; h265 may not inline-preview (accepted trade-off).
- **Instagram story monitoring** (`40517d8`) — `list_stories`/`download_stories`; `/ig add type:posts|stories|both`;
  poller sweeps post + story subs; shared `instagram_post.post_media()`.
- **Auto-suppress link-preview embeds** — after reposting a pasted TikTok/IG link, strip Discord's redundant
  preview embed (`suppress_link_embeds`, needs Manage Messages).
- **Multi-burner IG sharding** (`89fc8bd`, `fe1b2ae`) — `IG_COOKIES` accepts several cookie files;
  `IG_PROXIES` pairs a proxy per burner; accounts sharded by `md5(username)`; one poller per burner.
- **Phase 1: IG post monitoring + tagging** (`f821bb7`) — unified platform-aware `subscriptions` table
  (migrated from the old TikTok-only `accounts` table); `/ig` monitoring group; `tag:` (role/person/@everyone)
  + thread targets on both `/tt` and `/ig`; shared `monitor.forward_new`.
- **Instagram on-demand `/ig`** — gallery-dl engine; native-resolution posts/reels/carousels; merged into the
  TikTok bot as one container.
- **TikTok bot base** — yt-dlp engine; `/tt` account monitoring (paced scheduler, adaptive backoff) + paste
  auto-detect; ffmpeg compression for oversize; non-root, resource-capped Docker.
