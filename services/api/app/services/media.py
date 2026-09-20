"""
Work out how a content item's media should be presented.

One pure function, so the rule lives in exactly one place and is unit tested. The
result is what the player uses to decide between a YouTube embed, an HTML5 video,
an authenticated file viewer, or nothing.

Only well-formed https YouTube ids and http(s) direct-media URLs are accepted;
anything else resolves to no media rather than being passed to the browser.
"""

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlparse

YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com", "www.youtube-nocookie.com"}
DIRECT_VIDEO_EXTENSIONS = (".mp4", ".webm", ".ogg", ".mov", ".m4v")
DIRECT_AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".oga")


@dataclass(frozen=True)
class MediaSource:
    """provider: youtube | html5_video | html5_audio | file"""
    provider: str
    video_id: Optional[str] = None
    url: Optional[str] = None
    mime_type: Optional[str] = None


def parse_youtube_id(url: Optional[str]) -> Optional[str]:
    """Extract an 11-character video id from any common YouTube URL form, else None."""
    if not url:
        return None
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None

    host = (parsed.hostname or "").lower()
    candidate: Optional[str] = None
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host in YOUTUBE_HOSTS:
        if parsed.path == "/watch":
            candidate = (parse_qs(parsed.query).get("v") or [None])[0]
        else:
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 2 and parts[0] in ("embed", "shorts", "live", "v"):
                candidate = parts[1]
    return candidate if candidate and YOUTUBE_ID.match(candidate) else None


def _extension_of(url: str) -> str:
    return urlparse(url).path.lower()


def resolve_media(
    *,
    content_type: str,
    source_type: str,
    content_url: Optional[str],
    source_url: Optional[str],
    file_endpoint: str,
    file_mime_type: Optional[str] = None,
) -> Optional[MediaSource]:
    """
    Decide how to present an item's media.

    `file_endpoint` is the authenticated API path that streams an uploaded file; it
    is only used for items whose `source_type` is "upload".
    """
    # YouTube: from an explicit source URL, or a content URL that happens to be one.
    for candidate in (source_url, content_url):
        video_id = parse_youtube_id(candidate)
        if video_id:
            return MediaSource(provider="youtube", video_id=video_id)

    if source_type == "upload" and content_url:
        return MediaSource(provider="file", url=file_endpoint, mime_type=file_mime_type)

    if content_url and urlparse(content_url).scheme in ("http", "https"):
        path = _extension_of(content_url)
        if path.endswith(DIRECT_VIDEO_EXTENSIONS):
            return MediaSource(provider="html5_video", url=content_url)
        if path.endswith(DIRECT_AUDIO_EXTENSIONS):
            return MediaSource(provider="html5_audio", url=content_url)
    return None
