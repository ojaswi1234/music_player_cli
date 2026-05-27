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
import shlex
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.align import Align
from rich import box
from rich.text import Text
import socket
import json
import string
from typing import List
from rich.cells import cell_len
# External project modules
from getmusic import get_music
from tinydb import TinyDB, Query 

class MyLogger:
    def debug(self, msg):
        pass
    def warning(self, msg):
        pass
    def error(self, msg):
        pass

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

__version__ = "2.1.5"

console = Console()
app = typer.Typer(add_completion=False)

HISTORY_FILE = "play_history.txt"

# --- CONFIGURATION & PATHS ---
# Storing everything in a hidden folder in the User's home directory
APP_DIR = os.path.join(os.path.expanduser("~"), ".spci")
BIN_DIR = os.path.join(APP_DIR, "bin")
FAV_DIR = os.path.join(APP_DIR, "fav_audio") # Store actual .mp3 files here
FAV_DB_PATH = os.path.join(APP_DIR, "favorites.json") # NoSQL Metadata
IPC_SOCKET = os.path.join(APP_DIR, "mpvsocket")
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
playlist_table = db.table('playlists')

# --- UI COMPONENTS --


def sanitize_text(text):
    """
    Smart Hinglish Engine: Converts Hindi to natural sounding English.
    Follows modern Schwa-deletion rules (Tum hi ho, NOT Tuma hi ho).
    """
    if not text: return "Unknown"
    text = str(text)
    
    # 1. Skip if no Hindi detected
    if not any("\u0900" <= char <= "\u097f" for char in text):
        return text

    # 2. Character Maps
    vowels = {'अ':'a', 'आ':'aa', 'इ':'i', 'ई':'ee', 'उ':'u', 'ऊ':'oo', 'ए':'e', 'ऐ':'ai', 'ओ':'o', 'औ':'au'}
    consonants = {
        'क':'k', 'ख':'kh', 'ग':'g', 'घ':'gh', 'ङ':'n', 'च':'ch', 'छ':'chh', 'ज':'j', 'झ':'jh', 'ञ':'n',
        'ट':'t', 'ठ':'th', 'ड':'d', 'ढ':'dh', 'ण':'n', 'त':'t', 'थ':'th', 'द':'d', 'ध':'dh', 'न':'n',
        'प':'p', 'फ':'ph', 'ब':'b', 'भ':'bh', 'म':'m', 'य':'y', 'र':'r', 'ल':'l', 'व':'v', 'श':'sh', 'ष':'sh', 'स':'s', 'ह':'h'
    }
    matras = {'ा':'a', 'ि':'i', 'ी':'ee', 'ु':'u', 'ू':'oo', 'े':'e', 'ै':'ai', 'ो':'o', 'ौ':'au', 'ं':'n', 'ः':'h', '्':''}

    result = ""
    words = text.split()
    
    for word in words:
        rewritten_word = ""
        for i, char in enumerate(word):
            if char in vowels:
                rewritten_word += vowels[char]
            elif char in consonants:
                # Look ahead to see if there is a matra or if it's the end of the word
                next_char = word[i+1] if i+1 < len(word) else None
                
                rewritten_word += consonants[char]
                
                # SMART RULE: Only add 'a' if NOT at end of word and NOT followed by a matra
                if next_char and next_char in consonants:
                    rewritten_word += "a"
            elif char in matras:
                rewritten_word += matras[char]
            else:
                rewritten_word += char # Keep spaces/special chars
        
        result += rewritten_word + " "
    
    return result.strip().title()

class MPVController:
    """Handles IPC communication with mpv on Unix-based systems."""
    def __init__(self, socket_path):
        self.socket_path = socket_path

    def _send_command(self, command):
        if platform.system() == "Windows": return None
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(self.socket_path)
                msg = json.dumps({"command": command}) + "\n"
                client.sendall(msg.encode())
                response = client.recv(1024).decode()
                return json.loads(response).get("data")
        except:
            return None

    def get_pos(self): return self._send_command(["get_property", "time-pos"])
    def get_duration(self): return self._send_command(["get_property", "duration"])
    def toggle_pause(self): return self._send_command(["cycle", "pause"])

class NarrativeEngine:
    """Maps playback state to atmospheric phases and lore."""
    PHASES = [
        (0.15, "Intro", "Calm"),
        (0.40, "Build", "Focused"),
        (0.70, "Peak", "Intense"),
        (0.90, "Release", "Resonant"),
        (1.00, "Outro", "Ethereal")
    ]
    
    LORE_LINES = {
        "Intro": ["Signal acquired.", "Initial frequency sweep...", "Rhythm initializing."],
        "Build": ["Energy climbing.", "Patterns converging.", "The sequence accelerates."],
        "Peak": ["Rhythm locks in.", "Maximum resonance.", "The track commits."],
        "Release": ["Vibrations settling.", "Echoes in the void.", "Momentum dissipating."],
        "Outro": ["Fade to black.", "Harmonics drifting.", "Silence approaching."]
    }

    def __init__(self):
        self.cached_duration = 0

    def get_state(self, pos, duration):
        if not duration or duration <= 0: duration = self.cached_duration or 1
        self.cached_duration = duration
        ratio = pos / duration
        
        phase_name, mood = "Outro", "Ethereal"
        for threshold, name, md in self.PHASES:
            if ratio <= threshold:
                phase_name, mood = name, md
                break
        
        lore_pool = self.LORE_LINES.get(phase_name, ["..."])
        lore = lore_pool[int(pos // 6) % len(lore_pool)]
        return phase_name, mood, lore
    
    
def make_layout() -> Layout:
    """Creates a structured grid for the CLI interface."""
    layout = Layout(name="root")
    layout.split(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=5)
    )
    layout["main"].split_row(
        Layout(name="left", ratio=3),
        Layout(name="right", ratio=1),
    )
    return layout

def get_header():
    return Panel(
        Align.center(f"[bold cyan]SPCI SONIC PULSE[/bold cyan] v{__version__} | [bold yellow]Play once, play again & again[/bold yellow]"),
        box=box.ROUNDED,
        style="white on black"
    )
    
def get_now_playing_panel(title, artist, is_offline, pos, duration):
    # 1. Natural Transliteration
    safe_title = sanitize_text(title)
    safe_artist = sanitize_text(artist)
    
    # 2. Logic for Narrative Engine
    engine = NarrativeEngine()
    phase, mood, lore = engine.get_state(pos, duration)
    
    # 3. Visual Safety Truncation
    if cell_len(safe_title) > 35: safe_title = safe_title[:32] + "..."
    if cell_len(safe_artist) > 20: safe_artist = safe_artist[:17] + "..."

    # 4. Progress Bar (Sleek Visuals)
    bar_width = 25
    ratio = (pos / duration) if duration > 0 else 0
    filled = int(bar_width * ratio)
    bar = f"[white]█[/white]" * filled + "[dim]░[/dim]" * (bar_width - filled)
    
    time_str = f"{int(pos//60):02}:{int(pos%60):02} / {int(duration//60):02}:{int(duration%60):02}"
    
    # 5. Build Grid
    grid = Table.grid(padding=(0, 1))
    grid.add_column(justify="right", width=12, style="bold white")
    grid.add_column(justify="left", width=45) # Anchor column

    grid.add_row("TRACK", f"[bold yellow]{safe_title}[/bold yellow]")
    grid.add_row("ARTIST", f"[cyan]{safe_artist}[/cyan]")
    grid.add_row("PHASE", f"[bold magenta]{phase}[/bold magenta] [dim]({mood})[/dim]")
    grid.add_row("LORE", f"[italic green]“{lore}”[/italic green]")
    grid.add_row("", "")
    grid.add_row("[white]PROGRESS[/white]", f"{bar} [bold cyan]{time_str}[/bold cyan]")

    source = "[bold red]OFFLINE[/bold red]" if is_offline else "[bold green]STREAMING[/bold green]"
    return Panel(
        Align.center(grid, vertical="middle"),
        title=f"[bold green]SONIC PULSE ENGINE[/bold green] [dim]|[/dim] {source}",
        border_style="green",
        box=box.DOUBLE,
        expand=True
    )

def get_controls_panel(repeat_mode: bool = False):
    status = "[bold green]ON[/bold green]" if repeat_mode else "[bold red]OFF[/bold red]"
    return Panel(
        Align.center(f"[bold white]ACTIVE SESSION[/bold white] | REPEAT: {status}\n[dim]Ctrl+C: Stop | Ctrl+R: Repeat | Ctrl+P: Pause | n: Next[/dim]"),
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
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()[-3:]
            
            for line in lines:
                # The data is already romanized, now we just handle length
                raw_text = line.split('|')[0].strip()
                text_obj = Text(f"» {raw_text}", style="dim")
                # Truncate to a safe width for the sidebar
                text_obj.truncate(22, overflow="ellipsis")
                content += f"{text_obj}\n"
        else:
            content += "[dim]No recent plays.[/dim]"
    except Exception as e:
        content = f"[red]History Error[/red]"

    return Panel(
        content, 
        title="SPCI Stats", 
        border_style="green",
        box=box.ROUNDED,
        safe_box=True
    )

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
        return [mpv_path, "--no-video", "--gapless-audio=yes", f"--input-ipc-server={IPC_SOCKET}"]
    
    # Fallback to ffplay only if mpv is missing
    ffplay_path = shutil.which("ffplay")
    if ffplay_path:
        return [ffplay_path, "-nodisp", "-autoexit", "-loglevel", "quiet"]

    console.print("[bold red]Error:[/bold red] Required audio engine (mpv or ffplay) not found. [bold green]Installing now...[/bold green]")
    
    auto_install_dependencies(system)
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
    safe_name = sanitize_text(name)
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{safe_name} | {video_id}\n")

# --- SHELL LOGIC ---

def shell():
    # Call existing help() to show ASCII art and commands on entry
    help()
    
    while True:
        try:
            cmd_line = console.input("[bold cyan]spci> [/bold cyan]").strip()
            if not cmd_line:
                continue
            
            args = shlex.split(cmd_line)
            if args[0].lower() in ["exit", "quit"]:
                console.print("[yellow]Shutting down Sonic Pulse...[/yellow]")
                break
            
            # Use the existing Typer app to run the command
            try:
                # We need to call it with the arguments
                app(args)
            except SystemExit:
                # Typer/Click might exit the process on error or completion
                pass
        except KeyboardInterrupt:
            console.print("\n[yellow]Type 'exit' or 'quit' to close the shell.[/yellow]")
        except Exception as e:
            console.print(f"[bold red]Shell Error:[/bold red] {e}")

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
            'postprocessors': [{'key': 'FFmpegExtractAudio',
                                'preferredcodec': 'mp3',
                                'preferredquality': '64'}],
            'logger': MyLogger(),
            'no_warnings': True,
        }
    else:
        # NO POST-PROCESSING: Just get the raw audio file (usually .webm or .m4a)
        ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(FAV_DIR, video_id),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '64', # This ensures the file size remains small
        }],
        'quiet': True,
        'logger': MyLogger(),
        'no_warnings': True,
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
    # Create the table with expand=True so it fills the terminal width elegantly
    table = Table(show_header=True, header_style="bold blue", box=box.ROUNDED, expand=True)

# Using 'ratio' allows columns to grow proportionally to terminal size
# Here, the Command column gets 60% of the space, and Description gets 40%
    table.add_column("Command", style="cyan", ratio=3) 
    table.add_column("Description", style="dim", ratio=2)

# I've removed the leading spaces from your strings as Rich handles padding automatically
    table.add_row("search \"song name\"", "Search for a song")
    table.add_row(
    "play <VideoID> [bold yellow](offline)[/bold yellow]\n[dim]or[/dim]\n\"song name\" [bold yellow](online)[/bold yellow]", 
    "Play a song from local storage or search and stream online."
)
    table.add_row("add-fav \"<VideoID>\"", "Add to favorites")
    table.add_row("show-fav", "Show offline favorites")
    table.add_row("delete-fav \"<VideoID>\"", "Remove from favorites")
    table.add_row("add-pl <IDs...>", "Create a playlist")
    table.add_row("del-pl <ID/Name>", "Delete a playlist")
    table.add_row("play-pl <ID/Name>", "Play a playlist")
    table.add_row("view-pl", "View all playlists")
    table.add_row("find-pl <ID/Name>", "Find a playlist")
    table.add_row("show-history", "Show playback history")
    table.add_row("clear-history", "Clear playback history")
    table.add_row("quit / exit", "Exit the interactive shell")
   

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
    """Searches Online and displays results with Natural Hinglish transliteration."""
    with console.status(f"[bold green]Searching for '{query}'...[/bold green]"):
        results = get_music(query)
   
    if results:
        table = Table(title=f"Results: {query}", box=box.SQUARE, expand=True)
        table.add_column("ID", style="green", no_wrap=True, width=12)
        table.add_column("Title", style="bold white", ratio=3)
        table.add_column("Channel", style="cyan", ratio=1)
        table.add_column("Time", justify="right", width=8)
        
        for song in results:
            # Use the Smart Hinglish Engine to sanitize titles and artists
            safe_title = sanitize_text(song['title'])
            safe_artist = sanitize_text(song['artists'])

            # Visual truncation for table safety
            t_text = Text(safe_title)
            t_text.truncate(40, overflow="ellipsis")

            a_text = Text(safe_artist)
            a_text.truncate(15, overflow="ellipsis")
            
            table.add_row(song['videoId'], t_text, a_text, song['duration'])
        
        console.print(table, justify="center")
    else:
        console.print("[bold red]No results found.[/bold red]")

@app.command(name="add-pl", short_help="Add a new playlist")
def add_pl(song_ids: List[str]):
    """Creates a new playlist with the given song IDs."""
    playlist_name = typer.prompt("Enter playlist name")
    playlist_id = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    playlist_table.insert({
        "id": playlist_id,
        "name": playlist_name,
        "songs": song_ids
    })
    console.print(f"[bold green]Playlist '{playlist_name}' created with ID: {playlist_id}[/bold green]")

@app.command(name="del-pl", short_help="Delete a playlist")
def del_pl(identifier: str):
    """Deletes a playlist by ID or Name."""
    Playlist = Query()
    removed = playlist_table.remove((Playlist.id == identifier) | (Playlist.name == identifier))
    if removed:
        console.print(f"[bold green]Playlist deleted.[/bold green]")
    else:
        console.print(f"[bold red]Playlist not found.[/bold red]")

@app.command(name="view-pl", short_help="View all playlists")
def view_pl():
    """Lists all saved playlists."""
    playlists = playlist_table.all()
    if not playlists:
        return console.print("[yellow]No playlists found.[/yellow]")
    
    table = Table(title="Your Playlists", box=box.ROUNDED)
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Songs", style="magenta")
    
    for pl in playlists:
        table.add_row(pl['id'], pl['name'], str(len(pl['songs'])))
    
    console.print(table)

@app.command(name="find-pl", short_help="Find a playlist")
def find_pl(identifier: str):
    """Shows details of a specific playlist."""
    Playlist = Query()
    pl = playlist_table.get((Playlist.id == identifier) | (Playlist.name == identifier))
    if pl:
        console.print(f"[bold cyan]ID:[/bold cyan] {pl['id']}")
        console.print(f"[bold green]Name:[/bold green] {pl['name']}")
        console.print(f"[bold magenta]Songs:[/bold magenta] {', '.join(pl['songs'])}")
    else:
        console.print(f"[bold red]Playlist not found.[/bold red]")

def resolve_audio(query: str):
    """Resolves a query (ID or Title) to a playable audio source and metadata."""
    Song = Query()
    offline_entry = fav_table.get((Song.video_id == query) | (Song.title == query))

    title = "Unknown Title"
    artist = "Unknown Artist"
    vid = query
    audio_source = None
    is_offline = False
    duration = 0

    if offline_entry:
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
        try:
            with console.status(f"[bold green]Searching online for '{query}'...[/bold green]"):
                results = get_music(query)
                if not results:
                    return None
                
                song = results[0]
                vid, title, artist = song['videoId'], song['title'], song['artists']
                
                second_check = fav_table.get(Song.video_id == vid)
                if second_check and os.path.exists(second_check['path']):
                    audio_source, is_offline = second_check['path'], True
                else:
                    ydl_opts = {
                        'format': 'bestaudio/best', 
                        'quiet': True,
                        'logger': MyLogger(),
                        'no_warnings': True,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
                        audio_source = info.get('url')
                        duration = info.get('duration', 0)
                    is_offline = False
        except Exception:
            return None

    return {
        "audio_source": audio_source,
        "title": title,
        "artist": artist,
        "vid": vid,
        "is_offline": is_offline,
        "duration": duration
    }

def playback_engine(queries: List[str], repeat_mode: bool = False):
    """Handles the UI and process management for one or more songs."""
    layout = make_layout()
    repeat = repeat_mode
    controller = MPVController(IPC_SOCKET)
    player_cmd = get_player_command()

    try:
        with Live(layout, refresh_per_second=20, screen=True):
            while True:
                for query in queries:
                    song_info = resolve_audio(query)
                    if not song_info:
                        continue
                    
                    audio_source = song_info['audio_source']
                    title = song_info['title']
                    artist = song_info['artist']
                    vid = song_info['vid']
                    is_offline = song_info['is_offline']
                    duration = song_info['duration']

                    log_history(title, vid)

                    process = subprocess.Popen(player_cmd + [audio_source],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    start_time = time.time()
                    skip = False
                    
                    while process.poll() is None:
                        key = get_key()
                        if key in [b'r', b'R', b'\x12']:
                            repeat = not repeat
                        elif key == b'\x10': # Ctrl+P
                            controller.toggle_pause()
                        elif key == b'n': # Next
                            process.terminate()
                            skip = True
                            break
                        
                        # State Polling
                        if platform.system() == "Windows":
                            cur_pos = time.time() - start_time
                            cur_dur = duration or 240
                        else:
                            cur_pos = controller.get_pos() or (time.time() - start_time)
                            cur_dur = controller.get_duration() or duration or 1

                        layout["header"].update(get_header())
                        layout["left"].update(get_now_playing_panel(title, artist, is_offline, cur_pos, cur_dur))
                        layout["right"].update(get_stats_panel())
                        layout["footer"].update(get_controls_panel(repeat))
                        time.sleep(0.05)
                    
                    if skip: continue
                if not repeat: break
    except KeyboardInterrupt:
        if 'process' in locals(): process.terminate()
        console.show_cursor()
        console.print("\n[yellow]Playback stopped.[/yellow]")

@app.command(name="play-pl", short_help="Play a playlist")
def play_pl(identifier: str):
    """Plays all songs in a playlist."""
    Playlist = Query()
    pl = playlist_table.get((Playlist.id == identifier) | (Playlist.name == identifier))
    if pl:
        playback_engine(pl['songs'])
    else:
        console.print(f"[bold red]Playlist not found.[/bold red]")

@app.command(short_help="Play a song (Checks offline first)")
def play(query: str):
    """Handles playback with robust variable initialization."""
    playback_engine([query])

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
        with open(HISTORY_FILE, encoding="utf-8") as f:
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


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """
    Sonic Pulse Command Interface - A powerful CLI music player.
    """
    if ctx.invoked_subcommand is None:
        shell()

if __name__ == "__main__":
    app()
