from pathlib import Path
from typing import Optional
from pytubefix import YouTube, Search
from pytubefix.cli import on_progress


class YouTubeBrowser:
    """Handles downloading YouTube videos and audio."""

    def __init__(self, client: str = "TV", output_path: str = "downloads"):
        """
        Initialize the YouTube Client.

        Args:
            output_path: Directory where downloads will be saved.
        """
        self.output_path = Path(output_path)
        self.output_path.mkdir(parents=True, exist_ok=True)

        self.client = client
        self.Search = None

        self.videos_list = []
        self._next_video_result_index = 0
        self.shorts_list = []
        self._next_short_result_index = 0

    def search(self, query: str):
        """
        Search YouTube using pytubefix.Search.

        Args:
            query: Search query
        """
        self.Search = Search(query, client="ANDROID_VR")

        if self.Search.videos:
            for video in self.Search.videos:
                self.videos_list.append(
                    {
                        "title": video.title,
                        "url": video.watch_url,
                        "embed_url": video.embed_url,
                        "channel_id": video.channel_id,
                        "channel_url": video.channel_url,
                        "duration": video.length,
                        "views": video.views,
                    }
                )
                self._next_video_result_index += 1

        if self.Search.shorts:
            for short in self.Search.shorts:
                self.shorts_list.append(
                    {
                        "title": short.title,
                        "url": short.watch_url,
                        "embed_url": short.embed_url,
                        "channel_id": short.channel_id,
                        "channel_url": short.channel_url,
                        "duration": short.length,
                        "views": short.views,
                    }
                )
                self._next_short_result_index += 1

    def get_next_result_set(self):

        if self.Search is not None:
            self.Search.get_next_results()

            for video in self.Search.videos[self._next_video_result_index :]:
                self.videos_list.append(
                    {
                        "title": video.title,
                        "url": video.watch_url,
                        "embed_url": video.embed_url,
                        "channel_id": video.channel_id,
                        "channel_url": video.channel_url,
                        "duration": video.length,
                        "views": video.views,
                    }
                )
                self._next_video_result_index += 1

            for short in self.Search.shorts[self._next_short_result_index :]:
                self.shorts_list.append(
                    {
                        "title": short.title,
                        "url": short.watch_url,
                        "embed_url": short.embed_url,
                        "channel_id": short.channel_id,
                        "channel_url": short.channel_url,
                        "duration": short.length,
                        "views": short.views,
                    }
                )
                self._next_short_result_index += 1

    def videos(self):
        return self.videos_list

    def shorts(self):
        return self.shorts_list

    def results(self):
        return self.videos_list + self.shorts_list

    def download_video(
        self,
        url: str,
        quality: str = "1080p",
        output_path: Optional[str] = None,
    ) -> str:
        """
        Download a YouTube video.

        Args:
            url: YouTube video URL
            quality: Video quality (e.g., '720p', '1080p', 'highest', 'lowest')
            output_path: Custom output directory

        Returns:
            Path to the downloaded file
        """
        try:
            yt = YouTube(url, on_progress_callback=on_progress, client=self.client)

            print(f"Fetching streams for: {yt.title}")

            # Get stream based on quality preference
            if quality == "highest":
                stream = yt.streams.filter(progressive=True, subtype="mp4").order_by("resolution").last()
            elif quality == "lowest":
                stream = yt.streams.filter(progressive=True, subtype="mp4").order_by("resolution").first()
            else:
                stream = (
                    yt.streams.filter(progressive=True, res=quality, subtype="mp4")
                    .order_by("resolution")
                )
                if len(stream) > 0:
                    stream = stream.last()
                if not stream:
                    stream = (
                        yt.streams.filter(progressive=True, subtype="mp4").order_by("resolution")
                    )
                    if len(stream) > 0:
                        stream = stream.last()
                    else:
                        raise Exception(f"No suitable streams found for {url}")

            # Set output path and filename
            output_dir = Path(output_path) if output_path else self.output_path
            output_dir.mkdir(parents=True, exist_ok=True)

            print(f"Downloading: {yt.title}")
            print(f"Quality: {stream.resolution}")
            print(f"Filesize: {stream.filesize_approx / (1024 * 1024):.2f} MB")

            # Download the video
            file_path = stream.download(
                output_path=str(output_dir),
            )
            return file_path

        except Exception as e:
            print(f"Error downloading video: {str(e)}")
            raise

    def download_audio(
        self,
        url: str,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Download audio from a YouTube video.

        Args:
            url: YouTube video URL
            output_path: Custom output directory

        Returns:
            Path to the downloaded audio file
        """
        try:
            yt = YouTube(url, on_progress_callback=on_progress, client=self.client)

            # Get the best audio stream
            stream = yt.streams.get_audio_only()

            # Set output path and filename
            output_dir = Path(output_path) if output_path else self.output_path
            output_dir = output_dir / "audio"
            output_dir.mkdir(parents=True, exist_ok=True)

            print(f"\nDownloading audio: {yt.title}")

            # Download the audio
            file_path = stream.download(
                output_path=str(output_dir),
            )

            print(f"\nAudio download complete: {file_path}")
            return file_path

        except Exception as e:
            print(f"Error downloading audio: {str(e)}")
            raise


if __name__ == "__main__":
    # Rich-powered CLI for searching and downloading videos/audio

    from rich.console import Console
    from rich.table import Table
    from rich.prompt import Prompt, Confirm
    from rich.panel import Panel
    from rich.align import Align
    from rich.text import Text

    import time

    console = Console()

    def _format_views(v):
        try:
            n = int(v or 0)
        except Exception:
            return "-"
        for unit in ["", "K", "M", "B", "T"]:
            if abs(n) < 1000:
                return f"{n}{unit}"
            n //= 1000
        return f"{n}P"

    def _format_duration(seconds):
        try:
            s = int(seconds or 0)
        except Exception:
            return "-"
        h, r = divmod(s, 3600)
        m, s = divmod(r, 60)
        if h:
            return f"{h:d}:{m:02d}:{s:02d}"
        return f"{m:d}:{s:02d}"

    def _render_results(client):
        # Keep kind info for nicer display
        combined = [("Video", it) for it in client.videos()] + [
            ("Short", it) for it in client.shorts()
        ]
        if not combined:
            console.print("[yellow]No results.[/yellow]")
            return combined

        table = Table(show_header=True, header_style="bold magenta", expand=True)
        table.add_column("#", justify="right", width=4)
        table.add_column("Title", overflow="fold")
        table.add_column("Type", width=7)
        table.add_column("Duration", width=9)
        table.add_column("Views", width=8, justify="right")
        table.add_column("Channel", overflow="fold")

        for idx, (kind, item) in enumerate(combined, 1):
            table.add_row(
                str(idx),
                item.get("title") or "-",
                kind,
                _format_duration(item.get("duration")),
                _format_views(item.get("views")),
                (item.get("channel_id") or item.get("channel_url") or "-"),
            )
        console.print(table)
        return combined

    def _search_flow():
        query = Prompt.ask("[bold cyan]Search query[/bold cyan]").strip()
        if not query:
            return

        client = YouTubeBrowser()
        with console.status("[bold green]Searching...[/bold green]"):
            try:
                start = time.time()
                client.search(query)
                end = time.time()
                console.print(f"[green]Search completed in {end - start:.2f} seconds.[/green]")
            except Exception as e:
                console.print(f"[red]Search failed:[/red] {e}")
                return

        while True:
            console.print(Panel.fit(Text(f"Results for: {query}", style="bold cyan")))
            combined = _render_results(client)
            choice = (
                Prompt.ask(
                    "[bold]Enter index to download[/bold] • [b]m[/b]=more • [b]b[/b]=back",
                    default="b",
                )
                .strip()
                .lower()
            )

            if choice == "b":
                return
            if choice == "m":
                with console.status("[bold green]Loading more...[/bold green]"):
                    try:
                        client.get_next_result_set()
                    except Exception as e:
                        console.print(f"[red]Failed to load more:[/red] {e}")
                continue

            if not choice.isdigit():
                console.print(
                    "[yellow]Please enter a valid index, 'm', or 'b'.[/yellow]"
                )
                continue

            idx = int(choice)
            if idx < 1 or idx > len(combined):
                console.print("[yellow]Index out of range.[/yellow]")
                continue

            kind, item = combined[idx - 1]
            url = item.get("url")
            if not url:
                console.print("[red]Item has no URL.[/red]")
                continue

            mode = Prompt.ask(
                "Download [b]video[/b] or [b]audio[/b]?",
                choices=["video", "audio"],
                default="video",
            )
            if mode == "audio":
                try:
                    console.print(Panel.fit("Downloading audio...", style="green"))
                    path = client.download_audio(url)
                    console.print(f"[green]Saved:[/green] {path}")
                except Exception as e:
                    console.print(f"[red]Audio download failed:[/red] {e}")
            else:
                quality = Prompt.ask(
                    "Quality",
                    choices=["highest", "1080p", "720p", "480p", "360p", "lowest"],
                    default="1080p",
                )
                try:
                    console.print(
                        Panel.fit(f"Downloading video ({quality})...", style="green")
                    )
                    path = client.download_video(url, quality=quality)
                    console.print(f"[green]Saved:[/green] {path}")
                except Exception as e:
                    console.print(f"[red]Video download failed:[/red] {e}")

            if not Confirm.ask("Download another from these results?", default=False):
                return

    def _download_by_url():
        url = Prompt.ask("[bold cyan]YouTube URL[/bold cyan]").strip()
        if not url:
            return
        client = YouTubeBrowser()

        mode = Prompt.ask(
            "Download [b]video[/b] or [b]audio[/b]?",
            choices=["video", "audio"],
            default="video",
        )
        if mode == "audio":
            try:
                console.print(Panel.fit("Downloading audio...", style="green"))
                path = client.download_audio(url)
                console.print(f"[green]Saved:[/green] {path}")
            except Exception as e:
                console.print(f"[red]Audio download failed:[/red] {e}")
            return

        quality = Prompt.ask(
            "Quality",
            choices=["highest", "1080p", "720p", "480p", "360p", "lowest"],
            default="1080p",
        )
        try:
            console.print(Panel.fit(f"Downloading video ({quality})...", style="green"))
            path = client.download_video(url, quality=quality)
            console.print(f"[green]Saved:[/green] {path}")
        except Exception as e:
            console.print(f"[red]Video download failed:[/red] {e}")

    def main():
        console.print(
            Panel(
                Align.center(
                    Text("YouTube Downloader", style="bold white"),
                    vertical="middle",
                ),
                subtitle=Text("Search and download videos or audio", style="green"),
                style="blue",
            )
        )
        while True:
            console.print("\n[bold]Choose an option:[/bold]")
            console.print("  [b]1[/b]. Search")
            console.print("  [b]2[/b]. Download by URL")
            console.print("  [b]q[/b]. Quit")
            cmd = Prompt.ask("Your choice", choices=["1", "2", "q"], default="q")
            if cmd == "1":
                _search_flow()
            elif cmd == "2":
                _download_by_url()
            else:
                break

    main()
