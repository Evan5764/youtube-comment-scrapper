import logging
from typing import Any, Dict, List, Optional

from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
)

from utils.request_handler import RequestHandler

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

def get_video_comments(
    api_key: str,
    video_id: str,
    max_comments: int,
    request_handler: RequestHandler,
) -> List[Dict[str, Any]]:
    """
    Uses the YouTube Data API commentThreads endpoint to fetch top-level comments.
    """
    url = f"{YOUTUBE_API_BASE}/commentThreads"
    params: Dict[str, Any] = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": 100,
        "textFormat": "plainText",
        "order": "relevance",
        "key": api_key,
    }

    comments: List[Dict[str, Any]] = []

    while True:
        data = request_handler.get_json(url, params=params, expected_status_codes=(200, 403, 404))
        if not data:
            break

        if "error" in data:
            # Possible when comments are disabled or access is restricted.
            logger.warning(
                "Error fetching comments for %s: %s",
                video_id,
                data.get("error"),
            )
            break

        for item in data.get("items", []):
            snippet = (
                item.get("snippet", {}) or {}
            ).get("topLevelComment", {}).get("snippet", {}) or {}

            comment = {
                "comment_id": item.get("id"),
                "comment_author_name": snippet.get("authorDisplayName"),
                "comment_text": snippet.get("textDisplay") or snippet.get("textOriginal"),
                "comment_date": snippet.get("publishedAt"),
                "comment_likes": int(snippet.get("likeCount", 0) or 0),
                "comment_replies": int(
                    (item.get("snippet", {}) or {}).get("totalReplyCount", 0) or 0
                ),
            }
            comments.append(comment)

            if len(comments) >= max_comments:
                return comments

        next_token = data.get("nextPageToken")
        if not next_token:
            break
        params["pageToken"] = next_token

    return comments

def get_captions_for_video(
    video_id: str,
    preferred_languages: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Uses youtube-transcript-api to fetch an available transcript for the video,
    preferring the given languages and falling back to an auto-generated one.
    Returns a dict with language code, language name, and joined caption text.
    """
    if preferred_languages is None:
        preferred_languages = ["en"]

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    except (TranscriptsDisabled, NoTranscriptFound):
        logger.info("No transcripts available for video %s", video_id)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list transcripts for %s: %s", video_id, exc)
        return None

    transcript = None

    # Try exact language code match first.
    for lang in preferred_languages:
        try:
            transcript = transcript_list.find_manually_created_transcript([lang])
            break
        except NoTranscriptFound:
            try:
                transcript = transcript_list.find_generated_transcript([lang])
                break
            except NoTranscriptFound:
                continue

    # Fall back to first manually created or any available transcript.
    if transcript is None:
        try:
            transcript = transcript_list.find_manually_created_transcript(
                [t.language_code for t in transcript_list]
            )
        except NoTranscriptFound:
            try:
                transcript = transcript_list.find_generated_transcript(
                    [t.language_code for t in transcript_list]
                )
            except NoTranscriptFound:
                logger.info("Could not find any transcript for %s", video_id)
                return None

    try:
        entries = transcript.fetch()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to fetch transcript for %s: %s", video_id, exc)
        return None

    full_text = " ".join((e.get("text") or "").strip() for e in entries if e.get("text"))
    full_text = " ".join(full_text.split())  # Normalize whitespace

    return {
        "language_code": transcript.language_code,
        "language_name": transcript.language,
        "text": full_text,
    }