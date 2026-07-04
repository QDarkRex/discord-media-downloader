"""Experimental TikTok Story discovery via Playwright.

yt-dlp can download a TikTok story URL once we have it, but it cannot list a
profile's active stories. This module uses a logged-in browser session to visit a
profile, click likely story/avatar entry points, and sniff TikTok video URLs from
network responses opened by the story viewer.

This is intentionally conservative and best-effort. TikTok's web UI is not a
stable API, so callers should treat an empty list as "nothing discovered" rather
than a hard failure unless Playwright itself raises.
"""
import asyncio
import json
import os
import re
from urllib.parse import urlparse

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from src import tiktok
from src.log import get_logger

log = get_logger(__name__)

_VIDEO_URL_RE = re.compile(
    r"https?://(?:www\.)?tiktok\.com/@(?P<user>[\w.-]+)/video/(?P<id>\d+)",
    re.IGNORECASE,
)
_NUMERIC_ID_RE = re.compile(r"^\d{12,}$")
_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _proxy_arg(proxy):
    if not proxy:
        return None
    parsed = urlparse(proxy)
    if not parsed.scheme or not parsed.hostname:
        return {"server": proxy}
    server = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        server += f":{parsed.port}"
    out = {"server": server}
    if parsed.username:
        out["username"] = parsed.username
    if parsed.password:
        out["password"] = parsed.password
    return out


def _cookies_from_netscape(path):
    """Read a Netscape cookies.txt file into Playwright cookie dictionaries."""
    cookies = []
    if not path or not os.path.exists(path):
        return cookies
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") and not line.startswith("#HttpOnly_"):
                continue
            http_only = line.startswith("#HttpOnly_")
            if http_only:
                line = line[len("#HttpOnly_"):]
            parts = line.split("\t")
            if len(parts) != 7:
                continue
            domain, _flag, path_part, secure, expiry, name, value = parts
            try:
                expires = int(expiry)
            except ValueError:
                expires = -1
            cookie = {
                "name": name,
                "value": value,
                "domain": domain,
                "path": path_part or "/",
                "secure": secure.upper() == "TRUE",
                "httpOnly": http_only,
            }
            if expires > 0:
                cookie["expires"] = expires
            cookies.append(cookie)
    return cookies


def _add_video_url(found, url, expected_username):
    match = _VIDEO_URL_RE.search(url or "")
    if not match:
        return
    username = tiktok.normalize_username(match.group("user"))
    if username != expected_username:
        return
    vid = match.group("id")
    found[vid] = f"https://www.tiktok.com/@{username}/video/{vid}"


def _walk_json(obj, expected_username, found):
    """Best-effort TikTok JSON scanner.

    We only return canonical tiktok.com/@user/video/<id> URLs, never raw CDN URLs,
    because the existing posting pipeline expects a normal TikTok URL and lets
    yt-dlp choose the native rendition.
    """
    if isinstance(obj, dict):
        for value in obj.values():
            if isinstance(value, str):
                _add_video_url(found, value, expected_username)

        # Common TikTok object shapes use aweme_id/id plus author.unique_id.
        vid = obj.get("aweme_id") or obj.get("id")
        author = obj.get("author") or obj.get("author_info") or {}
        unique_id = None
        if isinstance(author, dict):
            unique_id = author.get("unique_id") or author.get("nickname")
        if isinstance(vid, str) and _NUMERIC_ID_RE.match(vid):
            if tiktok.normalize_username(unique_id or expected_username) == expected_username:
                found[vid] = f"https://www.tiktok.com/@{expected_username}/video/{vid}"

        for value in obj.values():
            _walk_json(value, expected_username, found)
    elif isinstance(obj, list):
        for value in obj:
            _walk_json(value, expected_username, found)


async def _try_click_story_entry(page, username, click_timeout_ms):
    """Click the most likely avatar/story entry point.

    TikTok changes selectors often, so this intentionally tries several small,
    bounded candidates. A failed click just means "no story entry found".
    """
    selectors = [
        'a[href*="/story"]',
        '[data-e2e="user-avatar"]',
        f'img[alt*="{username}" i]',
        'main header img',
        'main button:has(img)',
    ]
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            await loc.click(timeout=click_timeout_ms)
            return selector
        except Exception:
            continue

    # Last resort: click near the top-left-ish profile avatar region. It is crude,
    # but bounded and only used in the experimental watcher.
    try:
        await page.mouse.click(120, 220)
        return "coordinate:120,220"
    except Exception:
        return None


async def list_stories(username, cookies=None, proxy=None, timeout=45):
    """Discover active TikTok story video URLs for one username.

    Returns [{"id", "url"}, ...] newest-first-ish. Ordering is not guaranteed by
    TikTok's story viewer, so callers should still rely on last_seen de-duplication.
    """
    username = tiktok.normalize_username(username)
    found = {}
    timeout_ms = int(timeout * 1000)
    profile_url = f"https://www.tiktok.com/@{username}"

    async with async_playwright() as pw:
        launch_kwargs = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        proxy_arg = _proxy_arg(proxy)
        if proxy_arg:
            launch_kwargs["proxy"] = proxy_arg
        browser = await pw.chromium.launch(**launch_kwargs)
        try:
            context = await browser.new_context(
                user_agent=_DESKTOP_UA,
                viewport={"width": 1365, "height": 900},
                locale="en-US",
            )
            cookie_rows = _cookies_from_netscape(cookies)
            if cookie_rows:
                await context.add_cookies(cookie_rows)

            page = await context.new_page()

            async def handle_response(response):
                url = response.url
                _add_video_url(found, url, username)
                if not any(key in url.lower() for key in ("story", "aweme", "item", "detail", "api")):
                    return
                ctype = (response.headers.get("content-type") or "").lower()
                if "json" not in ctype and "text" not in ctype:
                    return
                try:
                    text = await response.text()
                    data = json.loads(text)
                except Exception:
                    return
                _walk_json(data, username, found)

            page.on("response", lambda response: asyncio.create_task(handle_response(response)))

            await page.goto(profile_url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_timeout(2500)

            # Start collecting only after the profile page is loaded, so regular
            # profile-grid videos are less likely to be mistaken for stories.
            clicked = await _try_click_story_entry(page, username, min(5000, timeout_ms))
            if not clicked:
                log.debug("tiktok story: no clickable story/avatar entry for @%s", username)
                return []

            await page.wait_for_timeout(7000)

            # Some story viewers lazy-load the next item only after a click/tap.
            for _ in range(2):
                try:
                    await page.mouse.click(1180, 450)
                    await page.wait_for_timeout(1200)
                except PlaywrightTimeoutError:
                    break

            log.debug("tiktok story: @%s clicked %s, found %d candidate(s)",
                      username, clicked, len(found))
        finally:
            await browser.close()

    # Numeric ids are time-ordered enough for de-duping; newest first.
    return [{"id": vid, "url": found[vid]} for vid in sorted(found, key=int, reverse=True)]


def list_stories_sync(username, cookies=None, proxy=None, timeout=45):
    """Sync wrapper for command add-time checks if needed."""
    return asyncio.run(list_stories(username, cookies, proxy, timeout))
