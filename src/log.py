import logging
import sys

_CONFIGURED = False


def setup_logging(level=logging.INFO):
    """Configure root logging once, writing to stdout (Docker-friendly)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                          datefmt="%Y-%m-%d %H:%M:%S")
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    # discord.py is chatty at INFO; keep it to warnings
    logging.getLogger("discord").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name):
    return logging.getLogger(name)
