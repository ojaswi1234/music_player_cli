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
config_table = db.table('config')

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
        Align.center(f"[bold cyan]SPCI SONIC PULSE[/bold cyan] v{__version__} | [bold yellow]Play once, play again & again[/bold yellow] | developed by [bold blue][link=https://github.com/ojaswi1234]@ojaswi1234[/bold blue]", vertical="middle"),
        box=box.ROUNDED,
        style="white on black"
    )

import math
import time

def get_now_playing_panel(title, artist, is_offline=False):
    """An advanced visualizer using sine-wave logic for smooth motion."""
    # We use time to create a 'shifting' effect
    t = time.time() * 10 
    
    # Unicode block characters for a smooth 'gradient' look
    # From shortest to tallest:  ▂ ▃ ▄ ▅ ▆ ▇ █
    blocks = [" ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
    
    vis_string = ""
    num_bars = 40
    
    for i in range(num_bars):
        # We combine two sine waves to make the motion look complex and 'musical'
        # Wave 1: slow pulse | Wave 2: faster jitter
        wave = math.sin(t + i * 0.5) * 0.5 + math.sin(t * 1.5 + i * 0.2) * 0.3
        
        # Normalize wave value (-1.0 to 1.0) to index (0 to 7)
        # We use abs() to make the 'pulse' go upwards from a baseline
        index = int((abs(wave) * (len(blocks) - 1)))
        
        # Add color based on height: green for low, yellow for mid, red for peak
        bar = blocks[index]
        if index < 3:
            vis_string += f"[green]{bar}[/green]"
        elif index < 6:
            vis_string += f"[yellow]{bar}[/yellow]"
        else:
            vis_string += f"[bold red]{bar}[/bold red]"

    source_tag = "[bold green]● OFFLINE[/bold green]" if is_offline else "[bold blue]● STREAMING[/bold blue]"
    
    content = f"""
[bold white]TITLE :[/bold white] [yellow]{title}[/yellow]
[bold white]ARTIST:[/bold white] [cyan]{artist}[/cyan]
[bold white]STATUS:[/bold white] {source_tag}

[bold white]SONIC PULSE:[/bold white]
{vis_string}
{vis_string}
    """
    return Panel(content, title="[bold red]NOW PLAYING[/bold red]", border_style="red")

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

def get_ydl_opts(extra_params=None):
    res = config_table.get(Query().key == 'browser')
    browser = res['value'] if res else None

    opts = {
        'quiet': True,
        'noplaylist': True,
    }

    if browser:
        # This acts as your 'Google Login'
        opts['cookiesfrombrowser'] = (browser,) 
        
    if extra_params:
        opts.update(extra_params)
    return opts

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
    
    if system != "Windows":
        if shutil.which("mpv"):
            return ["mpv", "--no-video", "--no-terminal"]
        if shutil.which("ffplay"):
            return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]
        
    console.print("[bold red]Critical Setup Failure:[/bold red] No compatible audio player found.")
    console.print("INSTALLING FFMPEG.....")
    subprocess.run("pip install ffmpeg-python mpv ", shell=True)
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

@app.command()
def login():
    """Link SPCI to your browser. No files, no codes, no headers."""
    console.print("[bold cyan]SPCI Browser-Link Setup[/bold cyan]")

    console.print(Panel(
        """[white]
1. Open your browser and log in to YouTube.
2. [bold red]Close the browser completely[/bold red] (to release the cookie file).
3. Type the browser name below when prompted.
        [/white]""",
        title="[yellow]Instructions[/yellow]",
        border_style="yellow"
    ))

    browser = typer.prompt("Which browser has your YouTube login? (chrome, edge, firefox, opera)")
    
    # Save this to your TinyDB config
    config_table.upsert({'key': 'browser', 'value': browser.lower()}, Query().key == 'browser')
    
    console.print(f"\n[bold green]Success![/bold green] SPCI will now 'borrow' cookies from {browser}.")
    console.print("[dim]Note: Ensure the browser is closed if you get a 'database is locked' error.[/dim]")

@app.command(short_help="Save a song for offline playback using VideoID")
def add_fav(video_id: str):
    """Downloads a song for offline playback (Modified for Cross-Platform)."""
    
    # MODIFIED: Removed the hard dependency on 'FFMPEG_PATH' check for non-windows
    if platform.system() == "Windows":
        get_player_command() # This ensures the .exe files are downloaded on Windows
        
    local_path = os.path.join(FAV_DIR, f"{video_id}.mp3")
    
    # MODIFIED: Quality reduced to '128' to save 33% disk space per your request
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': local_path.replace('.mp3', ''),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128', # Reduced from 192 to 128
        }],
        'quiet': True,
    }

    # MODIFIED: Dynamic FFmpeg Location
    # We only tell yt-dlp where ffmpeg is on Windows. 
    # On Termux/Linux, it will automatically find it in the system path.
    if platform.system() == "Windows":
        ydl_opts['ffmpeg_location'] = BIN_DIR 

    # MODIFIED: Added the browser-cookie logic so 'add_fav' can download age-restricted songs
    browser = get_browser()
    if browser:
        ydl_opts['cookiesfrombrowser'] = (browser,)

    with console.status(f"[bold green]Buffering {video_id}...[/bold green]"):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
                
                # Update NoSQL DB
                fav_table.upsert({
                    'video_id': video_id,
                    'title': info.get('title'),
                    'artist': info.get('uploader'),
                    'path': local_path
                }, Query().video_id == video_id)
                
            console.print(f"\n[bold green]Success![/bold green] '{info.get('title')}' saved to offline library.")
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")

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
    table.add_row("login", "Link SPCI to your browser for authenticated access")
    table.add_row("search", "Search for a song")
    table.add_row("play", "Play a song")
    table.add_row("add_fav", "Add a song to favorites")
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
        with Live(layout, refresh_per_second=10, screen=True):
            cmd = get_player_command() + [audio_source]
            process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            while process.poll() is None:
                layout["left"].update(get_now_playing_panel(title, artist, is_offline))
                time.sleep(0.1)
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
        

@app.command()
def setup_help():
    console.print(Panel(
        """[white] run [bold]( pip install -e . )[/bold] in the directory to install SPCI in global mode[/white]"""
    ))

if __name__ == "__main__":
    app()