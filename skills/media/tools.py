"""Media skill: YouTube search and yt-dlp downloads into the sandbox."""

from __future__ import annotations

from omen.core.tools import ToolResult, tool

from . import download
from .YoutubeSearch import YoutubeSearch


@tool
def search_youtube(query: str, max_results: int = 5) -> ToolResult:
    """Search YouTube. Returns titles, channels, durations and links.

    Args:
        query: What to search for.
        max_results: How many results (1-8).
    """
    videos = YoutubeSearch().search(query, max_results=min(max(max_results, 1), 8))
    if not videos:
        return ToolResult(f"No videos found for '{query}'.", details={"type": "video_results", "query": query, "results": []})
    lines = [
        f"{i}. {v.get('title')} ({v.get('channel')}, {v.get('duration')})\n   {v.get('url')}"
        for i, v in enumerate(videos, 1)
    ]
    return ToolResult("\n".join(lines), details={"type": "video_results", "query": query, "results": videos})


def _done(message: str, kind: str, url: str) -> ToolResult:
    if message.startswith("Error"):
        return ToolResult(message, error="exception")
    return ToolResult(message, details={"type": "download", "kind": kind, "url": url})


@tool
def download_audio(url: str) -> ToolResult:
    """Download the audio of a video (mp3) into downloads/audio.

    Args:
        url: Full video URL.
    """
    return _done(download.download_audio(url), "audio", url)


@tool
def download_video(url: str) -> ToolResult:
    """Download a video (up to 1080p) into downloads/video.

    Args:
        url: Full video URL.
    """
    return _done(download.download_video(url), "video", url)


TOOLS = [search_youtube, download_audio, download_video]
