import os

import yaml

DEFAULTS = {
    # Discord
    "prefix": "!",
    "activity_name": "TikTok",
    # Monitoring (paced scheduler)
    "sweep_target_seconds": 150,  # aim to re-check each account about this often
    "min_request_spacing": 1.5,   # safety floor: never fire TikTok requests faster than this
    "request_jitter": 0.5,        # +/- random seconds added to spacing (less robotic)
    "playlist_scan_count": 5,     # how many recent videos to scan per check
    # On-demand
    "auto_detect_links": True,   # auto-download TikTok/Instagram links pasted in chat
    # Instagram (/ig)
    "download_timeout": 180,     # kill a gallery-dl download that runs longer than this (seconds)
    "max_files_per_post": 20,    # safety cap on media files pulled from one IG carousel
    # Upload handling
    "max_upload_mb": 10,         # Discord free-tier upload cap (~10 MB)
    "compress_oversize": True,   # ffmpeg-compress videos over the cap before falling back to a link
    "compress_timeout": 120,     # kill an ffmpeg compress that runs longer than this (seconds)
}


def load_config(path="configs.yml"):
    """Load configs.yml merged over DEFAULTS. Missing file -> all defaults."""
    cfg = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
        cfg.update({k: v for k, v in user.items() if v is not None})
    return cfg
