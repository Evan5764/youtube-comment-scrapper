import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from extractors.channel_extractor import (
    get_channel_details_from_url,
    get_channel_details_by_id,
    get_recent_videos_for_channel,
)
from extractors.video_extractor import get_video_details
from extractors.comment_extractor import get_video_comments, get_captions_for_video
from utils.parser_helpers import (
    extract_video_id,
    is_video_url,
    is_channel_url,
)
from utils.request_handler import RequestHandler

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def load_settings() -> Dict[str, Any]:
    settings_path = PROJECT_ROOT / "src" / "config" / "settings.json"
    if not settings_path.exists():
        raise FileNotFoundError(f"settings.json not found at {settings_path}")

    with settings_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return data

def setup_logging(log_level: str = "INFO") -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

def load_input_urls() -> List[str]:
    input_path = PROJECT_ROOT / "data" / "input_urls.txt"
    if not input_path.exists():
        logging.warning("input_urls.txt not found; no URLs to process.")
        return []

    urls: List[str] = []
    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            urls.append(stripped)
    return urls

def build_record(
    channel: Dict[str, Any],
    video: Dict[str, Any],
    comment: Optional[Dict[str, Any]],
    caption_info: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "channel_id": channel.get("channel_id"),
        "channel_url": channel.get("channel_url"),
        "channel_name": channel.get("channel_name"),
        "channel_description": channel.get("channel_description"),
        "channel_location": channel.get("channel_location"),
        "channel_views": channel.get("channel_views"),
        "channel_subscribers": channel.get("channel_subscribers"),
        "video_id": video.get("video_id"),
        "video_title": video.get("video_title"),
        "video_url": video.get("video_url"),
        "video_duration": video.get("video_duration"),
        "video_views": video.get("video_views"),
        "video_likes": video.get("video_likes"),
        "video_comments": video.get("video_comments"),
        "video_date": video.get("video_date"),
        "caption_languageCode": None,
        "caption_languageName": None,
        "caption_text": None,
        "comment_id": None,
        "comment_author_name": None,
        "comment_text": None,
        "comment_date": None,
        "comment_likes": None,
        "comment_replies": None,
    }

    if caption_info:
        record["caption_languageCode"] = caption_info.get("language_code")
        record["caption_languageName"] = caption_info.get("language_name")
        record["caption_text"] = caption_info.get("text")

    if comment:
        record["comment_id"] = comment.get("comment_id")
        record["comment_author_name"] = comment.get("comment_author_name")
        record["comment_text"] = comment.get("comment_text")
        record["comment_date"] = comment.get("comment_date")
        record["comment_likes"] = comment.get("comment_likes")
        record["comment_replies"] = comment.get("comment_replies")

    return record

def process_video(
    api_key: str,
    video_id: str,
    request_handler: RequestHandler,
    settings: Dict[str, Any],
) -> List[Dict[str, Any]]:
    logger = logging.getLogger("main.process_video")
    records: List[Dict[str, Any]] = []

    video_details = get_video_details(api_key, video_id, request_handler)
    if not video_details:
        logger.warning(f"Skipping video {video_id}: could not fetch details.")
        return records

    channel_id = video_details.get("channel_id")
    if not channel_id:
        logger.warning(f"Video {video_id} has no channel_id in details; skipping.")
        return records

    channel_details = get_channel_details_by_id(api_key, channel_id, request_handler)
    if not channel_details:
        logger.warning(f"Skipping video {video_id}: could not fetch channel details.")
        return records

    comment_limit = int(settings.get("comment_limit", 100))
    fetch_captions = bool(settings.get("fetch_captions", True))
    caption_languages = settings.get("caption_languages") or ["en"]
    caption_info: Optional[Dict[str, Any]] = None

    if fetch_captions:
        caption_info = get_captions_for_video(
            video_id=video_id,
            preferred_languages=caption_languages,
        )

    comments = get_video_comments(
        api_key=api_key,
        video_id=video_id,
        max_comments=comment_limit,
        request_handler=request_handler,
    )

    if not comments:
        # Still emit at least one record with video and channel metadata.
        records.append(build_record(channel_details, video_details, None, caption_info))
        return records

    for c in comments:
        records.append(build_record(channel_details, video_details, c, caption_info))

    return records

def handle_channel_url(
    api_key: str,
    url: str,
    request_handler: RequestHandler,
    settings: Dict[str, Any],
) -> List[Dict[str, Any]]:
    logger = logging.getLogger("main.handle_channel_url")
    logger.info(f"Processing channel URL: {url}")
    all_records: List[Dict[str, Any]] = []

    channel_details = get_channel_details_from_url(api_key, url, request_handler)
    if not channel_details:
        logger.warning(f"Skipping channel {url}: could not fetch details.")
        return all_records

    max_videos = int(settings.get("max_videos_per_channel", 30))
    video_ids = get_recent_videos_for_channel(
        api_key=api_key,
        channel_id=channel_details["channel_id"],
        request_handler=request_handler,
        max_videos=max_videos,
    )

    if not video_ids:
        logger.info(f"No recent videos found for channel {channel_details['channel_id']}.")
        return all_records

    for vid in video_ids:
        records = process_video(api_key, vid, request_handler, settings)
        all_records.extend(records)

    return all_records

def handle_video_url(
    api_key: str,
    url: str,
    request_handler: RequestHandler,
    settings: Dict[str, Any],
) -> List[Dict[str, Any]]:
    logger = logging.getLogger("main.handle_video_url")
    logger.info(f"Processing video URL: {url}")
    video_id = extract_video_id(url)
    if not video_id:
        logger.warning(f"Could not extract video ID from URL: {url}")
        return []
    return process_video(api_key, video_id, request_handler, settings)

def write_output(records: List[Dict[str, Any]], settings: Dict[str, Any]) -> None:
    output_path = settings.get("output_file", "data/sample_output.json")
    output_path = Path(output_path)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    logging.getLogger("main").info(f"Wrote {len(records)} records to {output_path}")

def main() -> None:
    settings = load_settings()
    setup_logging(settings.get("log_level", "INFO"))
    logger = logging.getLogger("main")

    api_key = settings.get("youtube_api_key", "").strip()
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        logger.error(
            "You must set a valid 'youtube_api_key' in src/config/settings.json."
        )
        sys.exit(1)

    urls = load_input_urls()
    if not urls:
        logger.error("No input URLs found in data/input_urls.txt. Nothing to do.")
        sys.exit(1)

    request_handler = RequestHandler()

    all_records: List[Dict[str, Any]] = []

    for url in urls:
        try:
            if is_channel_url(url):
                records = handle_channel_url(api_key, url, request_handler, settings)
            elif is_video_url(url):
                records = handle_video_url(api_key, url, request_handler, settings)
            else:
                logger.warning(f"Unrecognized URL type, skipping: {url}")
                records = []
            all_records.extend(records)
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"Failed to process URL {url}: {exc}")

    if not all_records:
        logger.warning("No records produced. Check logs for errors.")
    else:
        write_output(all_records, settings)

if __name__ == "__main__":
    main()