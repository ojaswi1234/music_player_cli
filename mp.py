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
import random
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.align import Align
from rich import box
import math
import random
from rich.panel import Panel

# External project modules
from getmusic import get_music
from tinydb import TinyDB, Query 

__version__ = "2.0.0"

console = Console()
app = typer.Typer()

HISTORY_FILE = "play_history.txt"

# --- CONFIGURATION & PATHS ---
# Storing everything in a hidden folder in the User's home directory
APP_DIR = os.path.join(os.path.expanduser("~"), ".spci")
BIN_DIR = os.path.join(APP_DIR, "bin")
FAV_DIR = os.path.join(APP_DIR, "fav_audio") # Store actual .mp3 files here
FAV_DB_PATH = os.path.join(APP_DIR, "favorites.json") # NoSQL Metadata

# Windows Binary Paths
FFPLAY_PATH = os.path.join(BIN_DIR, "ffplay.exe")
FFMPEG_PATH = os.path.join(BIN_DIR, "ffmpeg.exe")
FFPROBE_PATH = os.path.join(BIN_DIR, "ffprobe.exe")

# Initialize directories
os.makedirs(BIN_DIR, exist_ok=True)
os.makedirs(FAV_DIR, exist_ok=True)

# Initialize NoSQL Database
db = TinyDB(FAV_DB_PATH)
fav_table = db.table('favorites')

# --- UI COMPONENTS ---

def make_layout() -> Layout:
    """Creates a structured grid for the CLI interface."""
    layout = Layout(name="root")
    layout.split(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=7)
    )
    layout["main"].split_row(
        Layout(name="left", ratio=2),
        Layout(name="right", ratio=1),
    )
    return layout

def get_header():
    return Panel(
        Align.center(f"[bold cyan]SPCI SONIC PULSE[/bold cyan] v{__version__} | [bold yellow]Play once, play again & again[/bold yellow]"),
        box=box.ROUNDED,
        style="white on black"
    )


def get_now_playing_panel(title, artist, is_offline=False, t=0.0):
    """
    Elegant ribbon visualizer:
    - Adapts to terminal size (console.size)
    - Smooth sine backbone + per-column micro-noise
    - Soft falloff with graded glyphs and color shift
    """
    # Terminal-aware sizing (keeps left panel compact)
    term = console.size
    viz_width = max(24, min(48, term.width // 3))
    viz_height = max(8, min(16, term.height // 4))

    cx = viz_width // 2
    cy = viz_height // 2

    # Glyph ramp from faint -> bold
    glyphs = [" ", "·", "•", "●", "█"]
    colors = ["dim", "cyan", "magenta", "green", "yellow"]

    # Parameters that control elegance
    base_freq = 0.9 + (viz_width / 80)        # spatial frequency
    speed = 1                             # temporal speed
    amplitude = (viz_height / 2.5)           # vertical swing
    smoothness = 1.6                         # how soft the falloff is

    # Build grid rows (top->bottom)
    grid_rows = []
    for y in range(viz_height):
        row = []
        for x in range(viz_width):
            # backbone: smooth sine across x, offset by time and small noise
            backbone = math.sin((x / viz_width) * base_freq * 2 * math.pi + t * speed)
            micro = math.sin((x * 0.7 + y * 0.4) * 0.4 + t * 1.7) * 0.15
            y_center = cy + (backbone + micro) * amplitude

            # distance from ribbon centerline for this column
            dist = abs(y - y_center)

            # normalized intensity (1 at center, decays to 0)
            intensity = max(0.0, 1.0 - (dist / smoothness))
            idx = int(intensity * (len(glyphs) - 1))

            # subtle phase-based color shift across x
            color_shift = int(((math.sin(t * 0.6 + x * 0.12) + 1) / 2) * (len(colors) - 1))
            color_idx = min(len(colors) - 1, max(0, idx + color_shift - 1))

            ch = glyphs[idx]
            color = colors[color_idx]
            # keep markup lean
            row.append(f"[{color}]{ch}[/{color}]")
        grid_rows.append("".join(row))

    vis = "\n".join(grid_rows)

    source_tag = (
        "[bold green]● OFFLINE (LOCAL)[/bold green]" if is_offline
        else "[bold blue]● STREAMING (YOUTUBE)[/bold blue]"
    )

    content = f"""
[bold white]TITLE :[/bold white] [yellow]{title}[/yellow]
[bold white]ARTIST:[/bold white] [cyan]{artist}[/cyan]
[bold white]STATUS:[/bold white] {source_tag}

{vis}
    """.rstrip()

    return Panel(Align.center(content), title="[bold red]NOW PLAYING[/bold red]", border_style="red")



def get_controls_panel():
    return Panel(
        Align.center("[bold white]ACTIVE SESSION[/bold white]\n[dim]Press Ctrl+C to stop playback and return to terminal[/dim]"),
        title="Controls",
        border_style="blue"
    )

def get_stats_panel():
    """Sidebar showing database status and history."""
    try:
        fav_count = len(fav_table.all())
        content = f"[bold green]Offline Songs: {fav_count}[/bold green]\n\n"
        content += "[bold white]Recent Activity:[/bold white]\n"
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                lines = f.readlines()[-3:]
            content += "".join([f"[dim]» {line.split('|')[0].strip()[:20]}...[/dim]\n" for line in lines])
        else:
            content += "[dim]No recent plays.[/dim]"
    except:
        content = "[red]DB Access Error[/red]"

    return Panel(content, title="SPCI Stats", border_style="green")

# --- CORE BACKEND LOGIC ---

def get_player_command():
    """Checks for binaries and returns the execution command."""
    system = platform.system()
    # -infbuf allows for smoother playback on slower networks
    ffplay_flags = ["-nodisp", "-autoexit", "-loglevel", "quiet", "-infbuf"] 

    if system == "Windows":
        # Check for the 'Trinity' of binaries
        if all(os.path.exists(p) for p in [FFPLAY_PATH, FFMPEG_PATH, FFPROBE_PATH]):
            return [FFPLAY_PATH] + ffplay_flags
        return download_trinity_windows(ffplay_flags)
    
    # Linux/Mac fallback
    if shutil.which("ffplay"): return ["ffplay"] + ffplay_flags
    console.print(f"[bold red]Error: ffplay not found. Please install ffmpeg on your system.[/bold red]")
    sys.exit(1)

def download_trinity_windows(flags):
    """Automatically downloads the required trio for Windows users."""
    console.print("\n[bold yellow]Requirement Missing: Audio Engine components not found.[/bold yellow]")
    console.print(f"Installing to: {BIN_DIR}")
    
    # Official Gyan.dev link for essential builds
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        buffer = io.BytesIO()

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TextColumn("[progress.percentage]{task.percentage:>3.0f}%"), console=console) as progress:
            task = progress.add_task("[green]Fetching Engine...", total=total_size)
            for chunk in response.iter_content(chunk_size=1024 * 8):
                buffer.write(chunk)
                progress.update(task, advance=len(chunk))
        
        buffer.seek(0)

        with console.status("[bold green]Extracting Player, Worker, and Analyzer...[/bold green]"):
            with zipfile.ZipFile(buffer) as z:
                for file in z.namelist():
                    if file.endswith("bin/ffplay.exe"):
                        with open(FFPLAY_PATH, "wb") as f: f.write(z.read(file))
                    elif file.endswith("bin/ffmpeg.exe"):
                        with open(FFMPEG_PATH, "wb") as f: f.write(z.read(file))
                    elif file.endswith("bin/ffprobe.exe"):
                        with open(FFPROBE_PATH, "wb") as f: f.write(z.read(file))
        
        console.print("[bold green]Installation Complete![/bold green]")
        return [FFPLAY_PATH] + flags
    except Exception as e:
        console.print(f"[bold red]Critical Setup Failure:[/bold red] {e}")
        sys.exit(1)

def log_history(name, video_id):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{name} | {video_id}\n")

# --- USER COMMANDS ---

@app.command(short_help="Save a song for offline playback using VideoID")
def add_fav(video_id: str):
    """Downloads audio bit-by-bit and registers it in the NoSQL database."""
    # Ensure worker (ffmpeg) exists
    get_player_command() 

    local_path = os.path.join(FAV_DIR, f"{video_id}.mp3")
    url = f"https://www.youtube.com/watch?v={video_id}"

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': local_path.replace('.mp3', ''),
        'ffmpeg_location': BIN_DIR, # CRITICAL: Points to your app's local binaries
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'noplaylist': True,
    }

    with console.status(f"[bold green]Buffering '{video_id}' to offline storage...[/bold green]"):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # NoSQL Update
                fav_table.upsert({
                    'video_id': video_id,
                    'title': info.get('title'),
                    'artist': info.get('uploader'),
                    'path': local_path
                }, Query().video_id == video_id)
            console.print(f"\n[bold green]Success![/bold green] '{info.get('title')}' is now stored offline.")
        except Exception as e:
            console.print(f"[bold red]Download Error:[/bold red] {e}")

@app.command(short_help="View and manage your offline favorites")
def show_fav():
    """Lists all structured data in the favorites NoSQL box."""
    favs = fav_table.all()
    if not favs:
        console.print("[dim]No offline songs found. Try 'add-fav <VideoID>'[/dim]")
        return

    table = Table(title="OFFLINE FAVORITES", box=box.HEAVY_EDGE)
    table.add_column("No.", style="dim")
    table.add_column("Song Title", style="bold white")
    table.add_column("Artist", style="cyan")
    table.add_column("Video ID", style="green")
    
    for i, song in enumerate(favs, start=1):
        table.add_row(str(i), song['title'], song['artist'], song['video_id'])
    
    console.print(table, justify="center")
    
  
    
@app.command(short_help="show help")
def help():
    table = Table(show_header=True, header_style="bold blue", box=box.ROUNDED)
    table.add_column("Command", width=14, style="cyan")
    table.add_column("Description", style="dim", width=50)
    table.add_row("search", "Search for a song")
    table.add_row("play", "Play a song")
    table.add_row("add-fav", "Add a song to favorites")
    table.add_row("show-fav", "Show offline favorite songs")
    table.add_row("delete-fav", "Delete a song from favorites")
    table.add_row("show-history", "Show the play history")
    table.add_row("clear-history", "Clear the play history")
    table.add_row("setup-help", "Steps to setup the environment to global")

    console.print(
    Panel(
        Align.center(
            """[bold green]
 ░██████╗██████╗░░█████╗░██╗
 ██╔════╝██╔══██╗██╔══██╗██║
 ╚█████╗░██████╔╝██║░░╚═╝██║
 ░╚═══██╗██╔═══╝░██║░░██╗██║
 ██████╔╝██║░░░░░╚█████╔╝██║
 ╚═════╝░╚═╝░░░░░░╚════╝░╚═╝
[/bold green]
[dim]Sonic Pulse Command Interface[/dim]
[dim]A simple yet elegant CLI music player[/dim]
""",
            vertical="middle"
        ),
        box=box.DOUBLE,
        style="green",
        subtitle="Welcome"
    ),
    Align.right("""developed by [bold blue][link=https://github.com/ojaswi1234]@ojaswi1234[/link][/bold blue]""")
)
    console.print(table, justify="center")


@app.command(short_help="Find music on YouTube")
def search(query: str):
    """Searches YouTube and displays results with their unique IDs."""
    with console.status(f"[bold green]Searching for '{query}'...[/bold green]"):
        results = get_music(query)
   
    if results:
        table = Table(title=f"Results for: {query}", box=box.MINIMAL_DOUBLE_HEAD)
        table.add_column("ID", style="green")
        table.add_column("Title", style="bold white")
        table.add_column("Artist", style="cyan")
        table.add_column("Length", justify="right")
        
        for song in results:
            table.add_row(song['videoId'], song['title'], song['artists'], song['duration'])
        console.print(table, justify="center")
    else:
        console.print("[bold red]No results found.[/bold red]")

@app.command(short_help="Play a song (Checks offline first)")
def play(query: str):
    """Modified logic to handle true offline playback."""
    
    # 1. IMMEDIATE LOCAL CHECK (By Title or Video ID)
    # We check if the query matches a title or ID already in our NoSQL DB
    Song = Query()
    offline_entry = fav_table.get((Song.video_id == query) | (Song.title == query))

    if offline_entry and os.path.exists(offline_entry['path']):
        # If found locally, PLAY IMMEDIATELY - No internet needed
        title, artist, audio_source = offline_entry['title'], offline_entry['artist'], offline_entry['path']
        is_offline = True
    else:
        # 2. ONLINE FALLBACK
        # Only search online if we didn't find it in our favorites
        try:
            with console.status(f"[bold green]Searching online for '{query}'...[/bold green]"):
                results = get_music(query)
                if not results:
                    console.print("[bold red]Song not found offline or online.[/bold red]")
                    return
                
                song = results[0]
                vid, title, artist = song['videoId'], song['title'], song['artists']
                
                # Check again if this specific ID from search results is offline
                second_check = fav_table.get(Song.video_id == vid)
                if second_check and os.path.exists(second_check['path']):
                    audio_source = second_check['path']
                    is_offline = True
                else:
                    # Final fallback: Get streaming URL (Requires Internet)
                    ydl_opts = {'format': 'bestaudio/best', 'quiet': True}
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
                        audio_source = info.get('url')
                    is_offline = False
        except Exception:
            console.print("[bold red]Offline Error:[/bold red] Song not in favorites and no internet connection found.")
            return

    # UI EXECUTION
    layout = make_layout()
    layout["header"].update(get_header())
    layout["right"].update(get_stats_panel())
    layout["footer"].update(get_controls_panel())

    try:
        with Live(layout, refresh_per_second=20, screen=True):
            cmd = get_player_command() + [audio_source]
            process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            t = 0.0
            while process.poll() is None:
                layout["left"].update(get_now_playing_panel(title, artist, is_offline, t))
                t += 0.12
                time.sleep(0.05)
    except KeyboardInterrupt:
        process.terminate()

@app.command(short_help="Remove a song from your offline favorites")
def delete_fav(video_id: str):
    """Deletes the local audio file and removes metadata from TinyDB."""
    Song = Query()
    item = fav_table.get(Song.video_id == video_id)

    if not item:
        console.print(f"[bold red]Error:[/bold red] Video ID '{video_id}' not found in favorites.")
        return

    # 1. Delete the physical file
    file_path = item.get('path')
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            console.print(f"[dim]Physical file removed: {video_id}.mp3[/dim]")
    except Exception as e:
        console.print(f"[bold yellow]Warning:[/bold yellow] Could not delete file: {e}")

    # 2. Remove from NoSQL Database
    fav_table.remove(Song.video_id == video_id)
    console.print(f"[bold green]Deleted![/bold green] '{item['title']}' has been removed from SPCI.")

@app.command()
def show_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            history_text = f.read()
        
        panel = Panel(
            history_text,
            title="[bold blue]Play History[/bold blue]",
            border_style="blue",
            box=box.ROUNDED
        )
        console.print(panel)
    else:
        console.print("[dim]No history found.[/dim]")

@app.command()
def clear_history():
    if os.path.exists(HISTORY_FILE):
        os.remove(HISTORY_FILE)
        console.print("[bold green]History cleared.[/bold green]")


if __name__ == "__main__":
    app()