"""
YouTube as a learning-content source.

Three layers, kept apart so the fragile part is small and testable:

  1. `validate_youtube_url`  - strict, offline. Only individual video links on YouTube's own
     hosts are accepted; the id is validated before anything is requested.
  2. Pure parsers over page and caption data (`extract_player_response`,
     `parse_caption_tracks`, `parse_json3`, ...). Unit tested against recorded shapes.
  3. `YouTubeClient`  - the HTTP calls. The only hosts it ever contacts are youtube.com
     (oEmbed and the watch page) and caption URLs that themselves point at youtube.com,
     so an administrator-supplied URL can never make the server fetch an arbitrary address.

Metadata comes from YouTube's official oEmbed endpoint (title, channel, thumbnail). Length,
description and captions come from the watch page's embedded player data, which is not a
documented API: if it changes or is unreachable those parts degrade to "unknown" with a
recorded warning, and the administrator can paste a transcript. Nothing is invented.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

import httpx

from app.ingestion.errors import InvalidUrl, SourceUnavailable, VideoUnavailable
from app.services.media import YOUTUBE_HOSTS, parse_youtube_id

MAX_URL_LENGTH = 2048
PLAYER_MARKERS = ("ytInitialPlayerResponse = ", "ytInitialPlayerResponse=")
PARAGRAPH_GAP_SECONDS = 45
USER_AGENT = "Mozilla/5.0 (compatible; AdaptiveLMS-Ingestion/1.0)"


# --------------------------------------------------------------------------- validation
def validate_youtube_url(url: str) -> str:
    """Return the 11-character video id, or raise InvalidUrl with a specific reason."""
    text = (url or "").strip()
    if not text:
        raise InvalidUrl("Enter a YouTube video link.")
    if len(text) > MAX_URL_LENGTH:
        raise InvalidUrl("That link is too long.")

    try:
        parsed = urlparse(text)
    except ValueError:
        raise InvalidUrl("That does not look like a valid link.")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise InvalidUrl("That does not look like a valid link. Paste the full address starting with https://.")

    host = (parsed.hostname or "").lower()
    if host != "youtu.be" and host not in YOUTUBE_HOSTS:
        raise InvalidUrl("Only YouTube links are supported.")

    video_id = parse_youtube_id(text)
    if not video_id:
        if "list=" in (parsed.query or "") or parsed.path.startswith(("/playlist", "/channel", "/@", "/c/", "/user/")):
            raise InvalidUrl("Playlists and channels are not supported. Paste the link to a single video.")
        raise InvalidUrl("Could not find a video id in that link.")
    return video_id


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


# ------------------------------------------------------------------------ pure parsers
@dataclass(frozen=True)
class CaptionTrack:
    url: str
    language: str
    kind: str  # "manual" | "auto"
    name: str = ""


@dataclass(frozen=True)
class Segment:
    start_seconds: float
    text: str


def extract_player_response(html: str) -> Optional[Dict[str, Any]]:
    """The player data object embedded in a watch page, or None if it is not there."""
    for marker in PLAYER_MARKERS:
        index = html.find(marker)
        if index == -1:
            continue
        try:
            data, _ = json.JSONDecoder().raw_decode(html[index + len(marker):])
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return None


def parse_video_details(player: Dict[str, Any]) -> Dict[str, Any]:
    details = player.get("videoDetails") or {}
    length = details.get("lengthSeconds")
    return {
        "title": details.get("title"),
        "author": details.get("author"),
        "duration_seconds": int(length) if isinstance(length, str) and length.isdigit() else None,
        "description": details.get("shortDescription"),
    }


def is_playable(player: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    status = player.get("playabilityStatus") or {}
    if status.get("status") in (None, "OK"):
        return True, None
    return False, status.get("reason") or status.get("status")


def parse_caption_tracks(player: Dict[str, Any]) -> List[CaptionTrack]:
    renderer = (player.get("captions") or {}).get("playerCaptionsTracklistRenderer") or {}
    tracks = []
    for raw in renderer.get("captionTracks") or []:
        url = raw.get("baseUrl")
        if not url:
            continue
        name = ((raw.get("name") or {}).get("simpleText")) or ""
        tracks.append(
            CaptionTrack(
                url=url,
                language=raw.get("languageCode") or "",
                kind="auto" if raw.get("kind") == "asr" else "manual",
                name=name,
            )
        )
    return tracks


def choose_track(tracks: List[CaptionTrack], preferred: tuple[str, ...] = ("en",)) -> Optional[CaptionTrack]:
    """Prefer a human-made track in a preferred language, then an automatic one, then anything."""
    if not tracks:
        return None

    def language_rank(track: CaptionTrack) -> int:
        code = track.language.lower()
        for rank, wanted in enumerate(preferred):
            if code == wanted or code.startswith(wanted + "-"):
                return rank
        return len(preferred)

    return sorted(tracks, key=lambda t: (language_rank(t), t.kind != "manual"))[0]


def is_youtube_caption_url(url: str) -> bool:
    """Caption URLs are followed only if they point at YouTube itself over https."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == "youtube.com" or host.endswith(".youtube.com"))


def parse_json3(payload: Dict[str, Any]) -> List[Segment]:
    """Caption segments from YouTube's json3 caption format."""
    segments: List[Segment] = []
    for event in payload.get("events") or []:
        pieces = event.get("segs")
        if not pieces:
            continue
        text = "".join(piece.get("utf8", "") for piece in pieces).replace("\n", " ").strip()
        if text and text != "♪":
            segments.append(Segment(start_seconds=(event.get("tStartMs") or 0) / 1000.0, text=text))
    return segments


def segments_to_text(segments: List[Segment]) -> str:
    """Join caption segments into readable paragraphs (a new paragraph after each pause of ~45 s of speech)."""
    paragraphs: List[List[str]] = []
    current: List[str] = []
    paragraph_start = 0.0
    for segment in segments:
        if current and segment.start_seconds - paragraph_start >= PARAGRAPH_GAP_SECONDS:
            paragraphs.append(current)
            current = []
        if not current:
            paragraph_start = segment.start_seconds
        current.append(segment.text)
    if current:
        paragraphs.append(current)
    return "\n\n".join(re.sub(r"\s+", " ", " ".join(p)).strip() for p in paragraphs).strip()


# --------------------------------------------------------------------------- the client
@dataclass
class YouTubeVideo:
    video_id: str
    title: str
    author: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    description: Optional[str] = None
    transcript: Optional[str] = None
    transcript_language: Optional[str] = None
    transcript_kind: Optional[str] = None  # manual | auto
    warnings: List[str] = field(default_factory=list)


class YouTubeClient:
    """Fetches what YouTube will tell us about a video. `transport` lets tests supply canned responses."""

    def __init__(self, *, timeout: float = 15.0, transport: Optional[httpx.AsyncBaseTransport] = None):
        self._timeout = timeout
        self._transport = transport

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self._timeout,
            transport=self._transport,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
            cookies={"CONSENT": "YES+1"},
            follow_redirects=True,
            max_redirects=3,
        )

    async def fetch(self, video_id: str) -> YouTubeVideo:
        watch = canonical_url(video_id)
        async with self._http() as http:
            try:
                oembed = await http.get(
                    f"https://www.youtube.com/oembed?url={quote(watch, safe='')}&format=json"
                )
            except httpx.HTTPError as exc:
                raise SourceUnavailable(f"Could not reach YouTube: {exc}") from exc

            if oembed.status_code in (401, 403, 404):
                raise VideoUnavailable(
                    "That video does not exist, is private, or does not allow embedding, "
                    "so it cannot be used as course content."
                )
            if oembed.status_code >= 400:
                raise SourceUnavailable(f"YouTube answered with status {oembed.status_code}.")

            meta = oembed.json()
            video = YouTubeVideo(
                video_id=video_id,
                title=(meta.get("title") or "").strip() or f"YouTube video {video_id}",
                author=meta.get("author_name"),
                thumbnail_url=meta.get("thumbnail_url"),
            )

            player = await self._fetch_player(http, watch, video)
            if player is not None:
                details = parse_video_details(player)
                video.duration_seconds = details["duration_seconds"]
                video.description = details["description"]
                if video.duration_seconds is None:
                    video.warnings.append("The video length could not be read.")
                await self._fetch_transcript(http, player, video)
            return video

    async def _fetch_player(self, http: httpx.AsyncClient, watch: str, video: YouTubeVideo) -> Optional[Dict[str, Any]]:
        try:
            page = await http.get(watch)
            page.raise_for_status()
        except httpx.HTTPError as exc:
            video.warnings.append(f"The video page could not be read ({exc}); length and captions are unknown.")
            return None
        player = extract_player_response(page.text)
        if player is None:
            video.warnings.append("The video page did not contain player data; length and captions are unknown.")
            return None
        playable, reason = is_playable(player)
        if not playable:
            raise VideoUnavailable(f"This video cannot be played: {reason}")
        return player

    async def _fetch_transcript(self, http: httpx.AsyncClient, player: Dict[str, Any], video: YouTubeVideo) -> None:
        track = choose_track(parse_caption_tracks(player))
        if track is None:
            video.warnings.append("This video has no captions, so there is no transcript.")
            return
        if not is_youtube_caption_url(track.url):
            video.warnings.append("The captions were not served from YouTube and were ignored.")
            return
        try:
            response = await http.get(track.url + ("&" if "?" in track.url else "?") + "fmt=json3")
            response.raise_for_status()
            segments = parse_json3(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            video.warnings.append(f"The captions could not be downloaded ({exc}).")
            return
        text = segments_to_text(segments)
        if not text:
            video.warnings.append("The captions were empty.")
            return
        video.transcript = text
        video.transcript_language = track.language
        video.transcript_kind = track.kind
        if track.kind == "auto":
            video.warnings.append("The transcript is YouTube's automatic captions and may contain errors.")
