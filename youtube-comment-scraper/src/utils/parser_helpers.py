import logging
import re
from typing import Dict, Optional
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

YOUTUBE_VIDEO_HOSTS = {
    "www.youtube.com",
    "youtube.com",
    "m.youtube.com",
    "youtu.be",
}

def extract_video_id(url: str) -> Optional[str]:
    """
    Extracts a YouTube video ID from common URL variants.
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse URL %s: %s", url, exc)
        return None

    if parsed.netloc not in YOUTUBE_VIDEO_HOSTS:
        return None

    # youtu.be/<id>
    if parsed.netloc == "youtu.be":
        vid = parsed.path.lstrip("/")
        return vid or None

    # youtube.com/watch?v=<id>
    if parsed.path.lower() == "/watch":
        qs = parse_qs(parsed.query)
        vid = qs.get("v", [None])[0]
        return vid

    # /shorts/<id>
    shorts_match = re.match(r"^/shorts/([^/?]+)", parsed.path)
    if shorts_match:
        return shorts_match.group(1)

    # Embed format: /embed/<id>
    embed_match = re.match(r"^/embed/([^/?]+)", parsed.path)
    if embed_match:
        return embed_match.group(1)

    return None

def extract_channel_identifier(url: str) -> Optional[Dict[str, str]]:
    """
    Tries to determine a channel identifier from URL and returns either:
      {"type": "channel_id", "value": "<id>"} or
      {"type": "handle", "value": "@handle"}
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse URL %s: %s", url, exc)
        return None

    if parsed.netloc not in {"www.youtube.com", "youtube.com", "m.youtube.com"}:
        return None

    path = parsed.path.rstrip("/")

    # /channel/<id>
    channel_match = re.match(r"^/channel/([^/]+)$", path)
    if channel_match:
        return {"type": "channel_id", "value": channel_match.group(1)}

    # /@handle
    handle_match = re.match(r"^/(@[^/]+)$", path)
    if handle_match:
        return {"type": "handle", "value": handle_match.group(1)}

    # Some channels use /c/<customName> or /user/<username>. These require
    # an additional lookup via YouTube Data API search in a robust solution.
    # Here we return None to keep logic explicit.
    return None

def is_video_url(url: str) -> bool:
    return extract_video_id(url) is not None

def is_channel_url(url: str) -> bool:
    return extract_channel_identifier(url) is not None