import yt_dlp
from pathlib import Path

SANDBOX_DIR = Path(__file__).resolve().parent.parent.parent / "root"

DOWNLOADS_DIR = SANDBOX_DIR / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

VIDEO_DIR = DOWNLOADS_DIR / "video"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_DIR = DOWNLOADS_DIR / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def download_video(
    url: str,
    output_path: str | Path = VIDEO_DIR,
    quality: str = "1080p",
    format: str = "mp4/mkv",
) -> str:
    """
    Download video with the specified quality.

    :param url: Video URL
    :param output_path: Directory or filename template for saving
    :param quality: Format string (default "best")
    """
    ydl_opts: yt_dlp._Params = {
        "outtmpl": f"{output_path}/%(title)s.%(ext)s",
        "format": f"bv*[height<={quality}]+ba/bv*[height<={quality}]",
        "merge_output_format": format,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            return f"Downloaded video to {output_path}"
    except Exception as e:
        return f"Error downloading video: {e}"


def download_audio(
    url: str,
    output_path: str | Path = AUDIO_DIR,
    audio_format: str = "mp3",
) -> str:
    """
    Extract audio from video and save as given format.

    :param url: Video URL
    :param output_path: Directory or filename template for saving
    :param audio_format: Desired audio format (e.g., mp3, flac, wav)
    :param audio_quality: Bitrate/quality (e.g., "128K", "192K")
    """
    ydl_opts: yt_dlp._Params = {
        "outtmpl": f"{output_path}/%(title)s.%(ext)s",
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
            }
        ],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            return f"Downloaded audio to {output_path}"
    except Exception as e:
        return f"Error downloading audio: {e}"
