import logging
from typing import Any, Dict, Optional

from utils.request_handler import RequestHandler

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

def get_video_details(
    api_key: str,
    video_id: str,
    request_handler: RequestHandler,
) -> Optional[Dict[str, Any]]:
    """
    Returns a normalized dictionary of video metadata and statistics.
    """
    url = f"{YOUTUBE_API_BASE}/videos"
    params = {
        "part": "snippet,statistics,contentDetails",
        "id": video_id,
        "key": api_key,
    }

    data = request_handler.get_json(url, params=params)
    if not data or "items" not in data or not data["items"]:
        logger.warning(f"No video details found for {video_id}")
        return None

    item = data["items"][0]
    snippet = item.get("snippet", {}) or {}
    statistics = item.get("statistics", {}) or {}
    content_details = item.get("contentDetails", {}) or {}

    video_url = f"https://www.youtube.com/watch?v={video_id}"

    # Duration is ISO8601; we keep raw and expose as-is plus seconds.
    duration_iso = content_details.get("duration")
    duration_seconds = _parse_iso8601_duration_seconds(duration_iso) if duration_iso else None

    normalized = {
        "video_id": video_id,
        "video_title": snippet.get("title"),
        "video_url": video_url,
        "video_duration": duration_seconds,
        "video_views": int(statistics.get("viewCount", 0) or 0),
        "video_likes": int(statistics.get("likeCount", 0) or 0),
        "video_comments": int(statistics.get("commentCount", 0) or 0),
        "video_date": snippet.get("publishedAt"),
        "channel_id": snippet.get("channelId"),
    }
    return normalized

def _parse_iso8601_duration_seconds(duration: str) -> Optional[int]:
    """
    Parses ISO 8601 duration (e.g., 'PT1H2M30S') into total seconds.
    """
    if not duration or not duration.startswith("P"):
        return None

    # Very small manual parser to avoid extra dependencies.
    # Format: PnYnMnDTnHnMnS or subset.
    time_part = duration
    if "T" in duration:
        date_part, time_part = duration.split("T")
    else:
        date_part, time_part = duration, ""

    seconds = 0

    def _extract(part: str, designator: str) -> int:
        if designator not in part:
            return 0
        num = ""
        for ch in part.split(designator)[0][::-1]:
            if ch.isdigit():
                num = ch + num
            else:
                break
        return int(num or 0)

    if time_part:
        # hours
        if "H" in time_part:
            seconds += _extract(time_part.split("H")[0] + "H", "H") * 3600
            time_part = time_part.split("H", 1)[1]
        # minutes
        if "M" in time_part:
            seconds += _extract(time_part.split("M")[0] + "M", "M") * 60
            time_part = time_part.split("M", 1)[1]
        # seconds
        if "S" in time_part:
            seconds += _extract(time_part.split("S")[0] + "S", "S")

    return seconds or None