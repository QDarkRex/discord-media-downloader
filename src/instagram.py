"""Thin wrapper around gallery-dl for Instagram.

Why gallery-dl (not yt-dlp): Instagram walls almost everything behind a login,
and gallery-dl is the most reliable tool for it. It pulls **original/native
resolution** photos AND videos, and it understands carousels (a single post that
holds multiple images/videos) — downloading every item in one go.

One job here:
  * download(url) -> grab every media file in the post into a fresh temp dir and
    return their paths plus a little metadata (username/caption) for the caption.

Cookies: Instagram blocks most content for logged-out clients. Point IG_COOKIES at
a Netscape-format cookies.txt exported from a logged-in (ideally burner) account to
make downloads reliable. Without cookies only the occasional public post works, and
Instagram rate-limits an anonymous client quickly.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

# Matches instagram.com post/reel/tv/story/profile links (incl. share-suffixed ones).
_URL_RE = re.compile(r"https?://(?:www\.)?instagram\.com/[^\s<>()]+", re.IGNORECASE)

# What we treat as postable media (everything else gallery-dl writes — .json sidecars,
# .txt — is metadata we read then ignore). Note: .m4a is intentionally absent — see the
# `videos=merged` note below; we never want to post a bare audio stream.
_MEDIA_EXTS = {".mp4", ".mov", ".webm", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"}
_VIDEO_EXTS = {".mp4", ".mov", ".webm"}

# Instagram serves *lower*-quality video to non-Chrome clients (gallery-dl warns about
# this), so pin a desktop-Chrome UA to get native-resolution video.
_CHROME_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def find_links(text):
    """Return all Instagram URLs found in a string (used for chat auto-detect)."""
    return _URL_RE.findall(text or "")


def is_video(path):
    return os.path.splitext(path)[1].lower() in _VIDEO_EXTS


def _read_metadata(work_dir):
    """gallery-dl --write-metadata drops a <file>.json next to each media file.
    Read the first one we find for the post's username + caption."""
    for name in sorted(os.listdir(work_dir)):
        if not name.lower().endswith(".json"):
            continue
        try:
            with open(os.path.join(work_dir, name), "r", encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        username = meta.get("username") or meta.get("owner_username") or ""
        caption = meta.get("description") or meta.get("caption") or ""
        return {"username": username, "caption": caption}
    return {"username": "", "caption": ""}


def download(url, dest_dir, cookies=None, proxy=None, timeout=180, max_files=20):
    """Download every media file in an Instagram post into a fresh temp dir.

    Returns a dict:
      {"dir": <temp dir to clean up>, "media": [paths...], "username": str,
       "caption": str, "webpage_url": url}

    `media` is empty if Instagram returned nothing (private post, bad/expired link,
    or — most commonly — no/invalid cookies). Callers surface that to the user.
    """
    os.makedirs(dest_dir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="ig_", dir=dest_dir)

    # --directory (NOT --destination): write files flat into `work` with no
    #   extractor subfolders, so the os.listdir below actually finds them.
    # videos=merged: download the single highest-res progressive MP4 (audio baked
    #   in) instead of split DASH streams that would need a yt-dlp/ffmpeg merge.
    # user-agent: a desktop-Chrome UA, or Instagram serves lower-quality video.
    # Invoke via `python -m gallery_dl` (not the bare `gallery-dl` script) so it
    # resolves from the same environment regardless of PATH.
    cmd = [sys.executable, "-m", "gallery_dl", "--quiet", "--no-part",
           "--directory", work, "--write-metadata",
           "-o", "extractor.instagram.videos=merged",
           "-o", f"extractor.instagram.user-agent={_CHROME_UA}"]
    if cookies:
        cmd += ["--cookies", cookies]
    if proxy:
        # Route through a proxy so Instagram sees the proxy IP, not the host's.
        cmd += ["--proxy", proxy]
    cmd += ["--", url]

    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
    )

    media = sorted(
        os.path.join(work, n) for n in os.listdir(work)
        if os.path.splitext(n)[1].lower() in _MEDIA_EXTS
    )
    meta = _read_metadata(work)

    return {
        "dir": work,
        "media": media[:max_files],
        "username": meta["username"],
        "caption": meta["caption"],
        "webpage_url": url,
        "returncode": proc.returncode,
        "stderr": (proc.stderr or "").strip()[-400:],
    }


if __name__ == "__main__":
    # Local smoke test:  python -m src.instagram <instagram_url> [cookies.txt]
    import sys

    try:  # make emoji-laden captions printable on Windows' cp1252 console
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if len(sys.argv) < 2:
        print("usage: python -m src.instagram <instagram_url> [cookies.txt]")
        raise SystemExit(1)
    cookies = sys.argv[2] if len(sys.argv) > 2 else None
    res = download(sys.argv[1], os.path.join("data", "downloads"), cookies=cookies)
    res["sizes_mb"] = [round(os.path.getsize(p) / (1024 * 1024), 2) for p in res["media"]]
    print(json.dumps({k: v for k, v in res.items() if k != "dir"}, indent=2, ensure_ascii=False))
