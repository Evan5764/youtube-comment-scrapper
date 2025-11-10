import logging
from typing import Any, Dict, List, Optional

from utils.request_handler import RequestHandler
from utils.parser_helpers import extract_channel_identifier

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

def _fetch_channel_resource(
    api_key: str,
    *, channel_id: Optional[str] = None, handle: Optional[str] = None,
    request_handler: RequestHandler,
) -> Optional[Dict[str, Any]]:
    params: Dict[str, Any] = {
        "part": "snippet,statistics,contentDetails",
        "maxResults": 1,
        "key": api_key,
    }

    if channel_id:
        params["id"] = channel_id
    elif handle:
        # Uses YouTube handle (e.g., @bitbash-demos)
        params["forHandle"] = handle.lstrip("@")
    else:
        raise ValueError("Either channel_id or handle must be provided.")

    url = f"{YOUTUBE_API_BASE}/channels"
    data = request_handler.get_json(url, params=params)
    if not data or "items" not in data or not data["items"]:
        logger.warning("No channel items returned from API.")
        return None
    return data["items"][0]

def _normalize_channel(channel_item: Dict[str, Any]) -> Dict[str, Any]:
    snippet = channel_item.get("snippet", {}) or {}
    statistics = channel_item.get("statistics", {}) or {}
    content_details = channel_item.get("contentDetails", {}) or {}
    uploads_playlist_id = (
        content_details.get("relatedPlaylists", {}) or {}
    ).get("uploads")

    channel_id = channel_item.get("id")
    custom_url = snippet.get("customUrl") or f"https://www.youtube.com/channel/{channel_id}"

    channel_data = {
        "channel_id": channel_id,
        "channel_url": custom_url,
        "channel_name": snippet.get("title"),
        "channel_description": snippet.get("description"),
        "channel_location": snippet.get("country"),
        "channel_views": int(statistics.get("viewCount", 0) or 0),
        "channel_subscribers": int(statistics.get("subscriberCount", 0) or 0),
        "uploads_playlist_id": uploads_playlist_id,
    }
    return channel_data

def get_channel_details_from_url(
    api_key: str,
    url: str,
    request_handler: RequestHandler,
) -> Optional[Dict[str, Any]]:
    identifier = extract_channel_identifier(url)
    if not identifier:
        logger.warning(f"Unable to identify channel from URL: {url}")
        return None

    id_type = identifier["type"]
    value = identifier["value"]
    if id_type == "channel_id":
        raw = _fetch_channel_resource(
            api_key, channel_id=value, request_handler=request_handler
        )
    elif id_type == "handle":
        raw = _fetch_channel_resource(
            api_key, handle=value, request_handler=request_handler
        )
    else:
        logger.warning(f"Unsupported channel identifier type '{id_type}' for URL {url}")
        return None

    if not raw:
        return None

    return _normalize_channel(raw)

def get_channel_details_by_id(
    api_key: str,
    channel_id: str,
    request_handler: RequestHandler,
) -> Optional[Dict[str, Any]]:
    raw = _fetch_channel_resource(
        api_key, channel_id=channel_id, request_handler=request_handler
    )
    if not raw:
        return None
    return _normalize_channel(raw)

def get_recent_videos_for_channel(
    api_key: str,
    channel_id: str,
    request_handler: RequestHandler,
    max_videos: int = 30,
) -> List[str]:
    """
    Uses the channel's uploads playlist to fetch recent video IDs.
    """
    channel = get_channel_details_by_id(api_key, channel_id, request_handler)
    if not channel:
        logger.warning(f"Cannot fetch recent videos: no channel details for {channel_id}")
        return []

    uploads_playlist_id = channel.get("uploads_playlist_id")
    if not uploads_playlist_id:
        logger.warning(f"No uploads playlist for channel {channel_id}")
        return []

    url = f"{YOUTUBE_API_BASE}/playlistItems"
    params: Dict[str, Any] = {
        "part": "contentDetails",
        "playlistId": uploads_playlist_id,
        "maxResults": 50,
        "key": api_key,
    }

    video_ids: List[str] = []
    while True:
        data = request_handler.get_json(url, params=params)
        if not data or "items" not in data:
            break

        for item in data.get("items", []):
            vid = (
                item.get("contentDetails", {}) or {}
            ).get("videoId")
            if vid:
                video_ids.append(vid)
                if len(video_ids) >= max_videos:
                    return video_ids

        next_token = data.get("nextPageToken")
        if not next_token:
            break
        params["pageToken"] = next_token

    return video_ids