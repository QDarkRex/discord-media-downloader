# STATUS — current state & next steps

_Snapshot for whoever picks this up next. Pair with [`AGENTS.md`](AGENTS.md) (how it works) and
[`CHANGELOG.md`](CHANGELOG.md) (history)._

Last updated: **2026-07-09**.

---

## Deployment status

- **Live server:** caddy VPS, container `tiktokbot`, bot **Aerox Joget#4488**. Running **1 Instagram
  burner, no proxy** (playtest, ~10 accounts). TikTok monitoring anonymous.
- **⚠️ `main` is AHEAD of what's deployed.** The last commit actually deployed to the server was the
  TikTok native-resolution fix (`bee6f9e`). **Not yet deployed:**
  - `c07011c` — Instagram story ID-mismatch fix.
  - `f58e45a` — experimental Playwright TikTok-story watcher.
- **To deploy:** bundle → copy → `docker compose up -d --build` (see [AGENTS.md §9](AGENTS.md#9-deployment)).
  **Read the Playwright warning below before deploying `f58e45a`.**

## ⚠️ Playwright TikTok-story watcher — deploy carefully

- Adds Chromium to the image (`playwright install --with-deps chromium`) → image grows to ~1 GB, slower
  build, more disk (VPS has ~20 GB).
- **Chromium at runtime needs more RAM than `compose.yml`'s `mem_limit: 512m`.** If
  `tiktok_story_enabled: true`, a story check will likely **OOM-kill the container**.
  - **Do this first:** raise `mem_limit` to **≥ 1.5g** and confirm the host (1.9 GB VPS) has headroom, or
    move the bot to a bigger box. Only then set `tiktok_story_enabled: true`.
- It is **opt-in** (`tiktok_story_enabled` defaults to `false`), so deploying is safe **as long as it stays
  off** — but the bigger image still builds. If you don't want Chromium on the small VPS, either deploy an
  image built without the Playwright commit, or run the story watcher on a separate host.

## What works (verified locally / in production)

- **TikTok:** on-demand download + account monitoring, **native resolution** (h265 1080p), `tag:` pinging,
  thread targets. Runs anonymously (cookies optional).
- **Instagram:** `/ig get` on-demand, **post monitoring**, **story monitoring** (`/ig add type:posts|stories|both`),
  burner sharding, `tag:` pinging, thread targets. Requires burner cookies.

## Experimental / unverified — needs real-world validation

- **IG story fix (`c07011c`)** — not yet confirmed live. If stories still don't appear, work
  [AGENTS.md §7](AGENTS.md#7-instagram-stories-debugging) (H1 subscription type → H2 baseline → H3 code).
- **TikTok Playwright story watcher (`f58e45a`)** — best-effort; **not tested against a live TikTok story**.
  Known risks: fragile UI selectors, and false positives (may sniff regular profile-grid videos as
  "stories"). Validate before trusting; keep disabled otherwise.

## Roadmap / open items

1. **Deploy the 2 pending commits** — with the `mem_limit` bump if enabling TikTok stories.
2. **Verify IG story forwarding live** (AGENTS.md §7).
3. **Scale Instagram to ~45 accounts:** add an **ISP (static residential) proxy** and wire the 2nd burner:
   `IG_COOKIES=/bot/data/ig_cookies.txt,/bot/data/ig_cookies2.txt` + `IG_PROXIES=<proxy>`.
   `data/ig_cookies2.txt` is already uploaded. See AGENTS.md §3.
4. **Validate / iterate the TikTok story watcher** (selectors, false-positive filtering) — or leave it off.
5. **Server migration** (VPS → local box): copy the whole `~/tiktokbot` folder **including `data/`**, then
   `docker compose up -d --build`. All state is in `data/tiktok.db`; nothing to re-add. Stop the old
   instance first (same bot token can't run twice).

## Key facts

- All monitoring state → `data/tiktok.db`. Cookies → `data/*.txt`. Secrets → `.env`. (`data/` + `.env`
  are gitignored.)
- Repo: `github.com/QDarkRex/discord-media-downloader`. Two slash groups: `/tt`, `/ig`.
- Open GitHub issues track the roadmap items above.
