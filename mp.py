from concurrent.futures import ThreadPoolExecutor
import os
import platform
import subprocess
import time
import sys
import shutil
import typer
import requests
import yt_dlp
import zipfile
import io
from rich.console import Console
from rich.table import Table
from rich.progress import track, Progress
from getmusic import get_music
import json

__version__ = "1.1.1"

console = Console()
app = typer.Typer()

HISTORY_FILE = "play_history.txt"

def get_player():
    """
    Returns the command list for the best available audio player.
    Windows: Auto-downloads ffplay.exe if missing.
    Linux/Mac: Checks for installed ffplay or mpv.
    """
    system = platform.system()

    # Recommended flags for streaming stability
    # -infbuf: Don't limit the input buffer (prevents stopping if download is slow)
    # -reconnect 1: Try to reconnect if the stream drops
    ffplay_flags = ["-nodisp", "-autoexit", "-loglevel", "quiet", "-infbuf"] 

    # 1. Check for installed players (Linux/Mac/Windows with PATH)
    if shutil.which("ffplay"):
        return ["ffplay"] + ffplay_flags
    
    if shutil.which("mpv"):
        return ["mpv", "--no-video"]

    # 2. Windows-Specific: Look for local portable ffplay.exe
    if system == "Windows":
        local_exe = os.path.abspath("ffplay.exe")
        if os.path.exists(local_exe):
            return [local_exe] + ffplay_flags
        
        # Auto-download if missing on Windows
        return download_ffplay_windows(ffplay_flags)

    # 3. Linux/Mac Missing Player Error
    console.print(f"\n[bold red]Error: No compatible audio player found on {system}.[/bold red]")
    if system == "Linux":
        console.print("Please install FFmpeg:\n  [green]sudo apt install ffmpeg[/green]  (Ubuntu/Debian)\n  [green]sudo pacman -S ffmpeg[/green]    (Arch)")
    elif system == "Darwin": # macOS
        console.print("Please install FFmpeg:\n  [green]brew install ffmpeg[/green]")
    
    sys.exit(1)

def download_ffplay_windows(flags):
    """Downloads ffplay.exe for Windows users."""
    console.print("\n[bold yellow]System audio components missing.[/bold yellow]")
    console.print("Downloading [bold]FFplay[/bold] (Portable Audio Engine)...")
    
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    
    try:
        with console.status("[bold green]Downloading (approx. 30MB)...[/bold green]"):
            r = requests.get(url)
            r.raise_for_status()
            
        with console.status("[bold green]Extracting ffplay.exe...[/bold green]"):
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                # Find ffplay.exe inside the zip
                for file in z.namelist():
                    if file.endswith("bin/ffplay.exe"):
                        with open("ffplay.exe", "wb") as f:
                            f.write(z.read(file))
                        break
        
        console.print("[bold green]Audio engine ready![/bold green]")
        return [os.path.abspath("ffplay.exe")] + flags

    except Exception as e:
        console.print(f"[bold red]Download failed:[/bold red] {e}")
        sys.exit(1)

def log_history(name, video_id):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{name} | https://www.youtube.com/watch?v={video_id}\n")

@app.command(short_help="show help")
def help():
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Command", width=14)
    table.add_column("Description", style="dim", width=50)
    table.add_row("search", "search for a song")
    table.add_row("play", "Play a song")
    table.add_row("show-history", "Show the play history")
    table.add_row("clear-history", "Clear the play history")

    console.print("""[bold green ]
      mmmm   mmmmmm    mmmm   mm#mm
    #"       #    m   #   "     #   
    "#mmm    #mmm#m  #          #   
        "#   #       #    "     #   
    "mmm#"   #        "mmmm   mm#mm
    [/bold green ]""", justify="center", style="bold green", highlight=False)
    console.print("\n[blue]Cross-Platform CLI Music Player[/blue]", justify="center")
    console.print("\n")
    console.print(table, justify="center", style="bold green", highlight=False)

@app.command(short_help="search")
def search(query: str):
    console.print(f"Searching for: [bold green]{query}[/bold green] ...........", style="bold green", justify="center")
    for i in track(range(4), description="Processing..."):
        time.sleep(0.5)

    results = get_music(query)
   
    if results:
        table = Table(show_header=True, header_style="bold red")
        table.add_column("No.", style="dim", width=6)
        table.add_column("Title", min_width=20)
        table.add_column("Artists", min_width=20)
        table.add_column("Album", min_width=20)
        table.add_column("Duration", justify="right")
        for i, song in enumerate(results, start=1):
            table.add_row(str(i), song['title'], song['artists'], song['album'], song['duration'])
        console.print(table, justify="center", style="bold green", highlight=False)
    else:
        console.print("No results found.", style="bold red")

@app.command(short_help="play")
def play(query: str):
    """
    Search for a song and stream it immediately.
    """
    # 1. Search
    with console.status(f"[bold green]Searching for '{query}'...[/bold green]"):
        results = get_music(query)

    if not results:
        console.print("[bold red]No music found.[/bold red]")
        return

    song = results[0]
    title = song['title']
    video_id = song['videoId']
    artist = song['artists']

    log_history(title, video_id)
    console.print(f"[bold blue]Found:[/bold blue] {title} by {artist}")

    # 2. Get Player Command (Handles Win/Linux/Mac)
    player_cmd = get_player()

    # 3. Extract Stream
    stream_url = None
    ydl_opts = {'format': 'bestaudio/best', 'quiet': True, 'noplaylist': True}

    with console.status("[bold green]Extracting audio stream...[/bold green]"):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                stream_url = info.get('url')
        except Exception as e:
            console.print(f"[bold red]Error extracting stream:[/bold red] {e}")
            return

    if not stream_url:
        console.print("[bold red]Could not retrieve audio stream.[/bold red]")
        return

    # 4. Play
    console.print(f"[bold green]Now Playing:[/bold green] {title} 🎵")
    console.print("[dim]Press Ctrl+C to stop playback.[/dim]")
    
    try:
        # Append URL to the player command
        full_cmd = player_cmd + [stream_url]
        subprocess.run(full_cmd, check=True)
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Playback stopped.[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]Player Error:[/bold red] {e}")

@app.command()
def show_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            console.print(f.read(), style="bold green")
    else:
        console.print("No history found.", style="bold red")

@app.command()
def clear_history():
    if os.path.exists(HISTORY_FILE):
        os.remove(HISTORY_FILE)
        console.print("History cleared.", style="bold green")

if __name__ == "__main__":
    app()