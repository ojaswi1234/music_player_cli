import os
import platform
import subprocess
import time
import sys
import shutil
import select
import typer
import requests
import yt_dlp
import zipfile
import io
import random
import math
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.align import Align
from rich import box

# External project modules
from .getmusic import get_music
from tinydb import TinyDB, Query 

def get_key():
    """Cross-platform keyboard input."""
    if platform.system() == "Windows":
        import msvcrt
        if msvcrt.kbhit():
            return msvcrt.getch()
    else:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
                return sys.stdin.read(1).encode()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return None

__version__ = "2.0.8"

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
    colors = ["dim", "red", "cyan", "indigo", "magenta", "green", "yellow", "orange", "bright_white"]

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
        "[bold red]● OFFLINE (LOCAL)[/bold red]" if is_offline
    else "[bold green]● STREAMING (YOUTUBE)[/bold green]"
)

    content = f"""
[bold white]TITLE :[/bold white] [yellow]{title}[/yellow]
[bold white]ARTIST:[/bold white] [cyan]{artist}[/cyan]
[bold white]STATUS:[/bold white] {source_tag}
{vis}
    """.rstrip()

    return Panel(Align.center(content), title="[bold green]NOW PLAYING[/bold green]", border_style="green")



def get_controls_panel(repeat_mode: bool = False):
    status = "[bold green]ON[/bold green]" if repeat_mode else "[bold red]OFF[/bold red]"
    return Panel(
        Align.center(f"[bold white]ACTIVE SESSION[/bold white] | REPEAT: {status}\n[dim]Press Ctrl+C to stop | Press Ctrl+R to toggle Repeat[/dim]"),
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
def auto_install_dependencies(system):
    """Uses subprocess to install ffmpeg and mpv based on the OS."""
    try:
        if system == "Darwin":  # macOS
            if shutil.which("brew"):
                console.print("[yellow]macOS detected. Installing via Homebrew...[/yellow]")
                subprocess.run(["brew", "install", "ffmpeg", "mpv"], check=True)
            else:
                console.print("[red]Homebrew not found. Please install Homebrew first.[/red]")
        
        elif system == "Linux":
            # Check for common Linux package managers
            if shutil.which("apt"):
                console.print("[yellow]Linux (Debian/Ubuntu) detected. Installing via apt...[/yellow]")
                # Using sudo may require user password input in terminal
                subprocess.run(["sudo", "apt", "update"], check=True)
                subprocess.run(["sudo", "apt", "install", "-y", "ffmpeg", "mpv"], check=True)
            elif shutil.which("pacman"):
                console.print("[yellow]Arch Linux detected. Installing via pacman...[/yellow]")
                subprocess.run(["sudo", "pacman", "-S", "--noconfirm", "ffmpeg", "mpv"], check=True)
            elif shutil.which("dnf"):
                console.print("[yellow]Fedora detected. Installing via dnf...[/yellow]")
                subprocess.run(["sudo", "dnf", "install", "-y", "ffmpeg", "mpv"], check=True)
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Installation failed:[/bold red] {e}")

def get_player_command():
    """Checks for binaries. Uses local Trinity on Windows, system mpv on Linux/Mac."""
    system = platform.system()
    
    if system == "Windows":
        ffplay_flags = ["-nodisp", "-autoexit", "-loglevel", "quiet", "-infbuf"] 
        if all(os.path.exists(p) for p in [FFPLAY_PATH, FFMPEG_PATH, FFPROBE_PATH]):
            return [FFPLAY_PATH] + ffplay_flags
        return download_trinity_windows(ffplay_flags)
    
    # LINUX/MAC: Look for mpv first as it's the most stable
    mpv_path = shutil.which("mpv")
    if mpv_path:
        return [mpv_path, "--no-video", "--gapless-audio=yes"]
    
    # Fallback to ffplay only if mpv is missing
    ffplay_path = shutil.which("ffplay")
    if ffplay_path:
        return [ffplay_path, "-nodisp", "-autoexit", "-loglevel", "quiet"]

    console.print("[bold red]Error: No player found.[/bold red] Please run: sudo apt install mpv")
    sys.exit(1)


def download_trinity_windows(flags):
    """Fixed: Path-agnostic extraction for Windows binaries."""
    console.print("\n[bold yellow]Requirement Missing: Audio Engine not found.[/bold yellow]")
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    buffer = io.BytesIO()

    with Progress(SpinnerColumn(), TextColumn("[green]Fetching Engine..."), BarColumn(), console=console) as progress:
        task = progress.add_task("Downloading", total=total_size)
        for chunk in response.iter_content(chunk_size=8192):
            buffer.write(chunk)
            progress.update(task, advance=len(chunk))
    
    buffer.seek(0)
    with zipfile.ZipFile(buffer) as z:
        for member in z.namelist():
            filename = os.path.basename(member)
            # Extracts specifically into your local .spci/bin folder
            if filename == "ffplay.exe":
                with open(FFPLAY_PATH, "wb") as f: f.write(z.read(member))
            elif filename == "ffmpeg.exe":
                with open(FFMPEG_PATH, "wb") as f: f.write(z.read(member))
            elif filename == "ffprobe.exe":
                with open(FFPROBE_PATH, "wb") as f: f.write(z.read(member))
    return [FFPLAY_PATH] + flags



def log_history(name, video_id):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{name} | {video_id}\n")

# --- USER COMMANDS ---


@app.command()
def setup():
    subprocess.run(["pip", "install", "-e", "."], check=True) 

@app.command(short_help="Add song to storage (Raw format for mpv)")
def add_fav(video_id: str):
    """Downloads raw audio without needing ffmpeg conversion on Linux/Mac."""
    system = platform.system()
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    # On Windows, we still use our local ffmpeg to make .mp3s
    # On Linux/Mac, we download the raw file to avoid ffmpeg dependencies
    if system == "Windows":
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(FAV_DIR, video_id),
            'ffmpeg_location': BIN_DIR,
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '64'}],
        }
    else:
        # NO POST-PROCESSING: Just get the raw audio file (usually .webm or .m4a)
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(FAV_DIR, f"{video_id}.%(ext)s"),
            'quiet': True,
        }

    with console.status(f"[bold green]Downloading '{video_id}'...[/bold green]"):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # Find exactly what file was saved
                ext = info.get('ext', 'mp3') if system == "Windows" else info['ext']
                final_path = os.path.join(FAV_DIR, f"{video_id}.{ext}")

                fav_table.upsert({
                    'video_id': video_id,
                    'title': info.get('title'),
                    'artist': info.get('uploader'),
                    'path': final_path
                }, Query().video_id == video_id)
            console.print(f"[bold green]Success![/bold green] Saved as {info['ext']} for mpv playback.")
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
    table.add_row("add-fav", "Add a song to favorites for offline playback")
    table.add_row("show-fav", "Show offline favorite songs")
    table.add_row("delete-fav", "Delete a song from offline favorites")
    table.add_row("show-history", "Show the play history")
    table.add_row("clear-history", "Clear the play history")
    table.add_row("setup", "setup the environment to global")

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


@app.command(short_help="Find music online")
def search(query: str):
    """Searches Online and displays results with their unique IDs."""
    with console.status(f"[bold green]Searching music online '{query}'...[/bold green]"):
        results = get_music(query)
   
    if results:
        table = Table(title=f"YouTube Results for: {query}", box=box.MINIMAL_DOUBLE_HEAD)
        table.add_column("ID", style="green")
        table.add_column("Title", style="bold white")
        table.add_column("Channel/Artist", style="cyan")
        table.add_column("Length", justify="right")
        
        for song in results:
            table.add_row(song['videoId'], song['title'], song['artists'], song['duration'])
        console.print(table, justify="center")
    else:
        console.print("[bold red]No results found.[/bold red]")
        
        
        

@app.command(short_help="Play a song (Checks offline first)")
def play(query: str):
    """Handles playback with robust variable initialization to prevent crashes."""
    Song = Query()
    offline_entry = fav_table.get((Song.video_id == query) | (Song.title == query))

    # 1. INITIALIZE VARIABLES (Prevents UnboundLocalError)
    title = "Unknown Title"
    artist = "Unknown Artist"
    vid = query
    audio_source = None
    is_offline = False
   

    if offline_entry:
        # Check for the file (supports multiple extensions for mpv)
        base_path = os.path.splitext(offline_entry['path'])[0]
        for ext in ['.webm', '.m4a', '.mp3', '.opus']:
            test_path = base_path + ext
            if os.path.exists(test_path):
                audio_source = test_path
                title = offline_entry.get('title', 'Unknown')
                artist = offline_entry.get('artist', 'Unknown')
                vid = offline_entry.get('video_id', query)
                is_offline = True
                break

    if not is_offline:
        # 2. ONLINE FALLBACK
        try:
            with console.status(f"[bold green]Searching online for '{query}'...[/bold green]"):
                results = get_music(query)
                if not results:
                    return console.print("[bold red]Song not found offline or online.[/bold red]")
                
                song = results[0]
                vid, title, artist = song['videoId'], song['title'], song['artists']
                
                # Double check search result against DB
                second_check = fav_table.get(Song.video_id == vid)
                if second_check and os.path.exists(second_check['path']):
                    audio_source, is_offline = second_check['path'], True
                else:
                    # Stream 64kbps to save bandwidth
                    ydl_opts = {'format': 'bestaudio[abr<=64]/bestaudio/best', 'quiet': True}
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
                        audio_source = info.get('url')
                    is_offline = False
        except Exception:
            return console.print("[bold red]Error:[/bold red] Check internet or favorites.")

    # 3. LOG HISTORY (Variables are now guaranteed to exist)
    log_history(title, vid)

    # UI EXECUTION
    layout = make_layout()
    repeat = False
    try:
        with Live(layout, refresh_per_second=20, screen=True):
            # Uses mpv or ffplay based on OS detection
            while True:
                process = subprocess.Popen(get_player_command() + [audio_source], 
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                t = 0.0
                while process.poll() is None:
                    key = get_key()
                    if key:
                        # Allow 'r' or Ctrl+R (0x12) to toggle repeat
                        if key in [b'r', b'R', b'\x12']:
                            repeat = not repeat
                            
                    layout["header"].update(get_header())
                    layout["left"].update(get_now_playing_panel(title, artist, is_offline, t))
                    layout["right"].update(get_stats_panel())
                    layout["footer"].update(get_controls_panel(repeat))
                    t += 0.12
                    time.sleep(0.05)
                if not repeat:
                    break
    except KeyboardInterrupt:
        if 'process' in locals():
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