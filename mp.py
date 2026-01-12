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
import math
import webbrowser  # Required for auto-opening Chrome
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.align import Align
from rich import box
import questionary

# External project modules
from getmusic import get_music
from tinydb import TinyDB, Query 

__version__ = "2.3.0"

console = Console()
app = typer.Typer()

HISTORY_FILE = "play_history.txt"

# --- CONFIGURATION & PATHS ---
APP_DIR = os.path.join(os.path.expanduser("~"), ".spci")
BIN_DIR = os.path.join(APP_DIR, "bin")
FAV_DIR = os.path.join(APP_DIR, "fav_audio")
FAV_DB_PATH = os.path.join(APP_DIR, "favorites.json")

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

# --- HELPERS ---

def get_browser():
    """Retrieves the preferred browser for cookies from the DB."""
    res = config_table.get(Query().key == 'browser')
    return res['value'] if res else None

def get_ydl_opts(extra_params=None, use_cookies=True):
    """Strictly uses the manual cookies.txt file for authentication."""
    manual_cookies = os.path.join(APP_DIR, "cookies.txt")
    
    opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'nocheckcertificates': True,
        'ignoreerrors': True,
    }

    if use_cookies and os.path.exists(manual_cookies):
        opts['cookiefile'] = manual_cookies
        
    if extra_params:
        opts.update(extra_params)
    return opts

# --- UI COMPONENTS ---

def make_layout() -> Layout:
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

def get_now_playing_panel(title, artist, is_offline=False):
    """Advanced Sine-Wave Visualizer."""
    t = time.time() * 10 
    blocks = [" ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
    vis_string = ""
    num_bars = 40
    
    for i in range(num_bars):
        wave = math.sin(t + i * 0.5) * 0.5 + math.sin(t * 1.5 + i * 0.2) * 0.3
        index = int((abs(wave) * (len(blocks) - 1)))
        bar = blocks[index]
        if index < 3: vis_string += f"[green]{bar}[/green]"
        elif index < 6: vis_string += f"[yellow]{bar}[/yellow]"
        else: vis_string += f"[bold red]{bar}[/bold red]"

    source_tag = "[bold green]● OFFLINE[/bold green]" if is_offline else "[bold blue]● STREAMING[/bold blue]"
    content = f"\n[bold white]TITLE :[/bold white] [yellow]{title}[/yellow]\n[bold white]ARTIST:[/bold white] [cyan]{artist}[/cyan]\n[bold white]STATUS:[/bold white] {source_tag}\n\n[bold white]SONIC PULSE:[/bold white]\n{vis_string}\n{vis_string}"
    return Panel(content, title="[bold red]NOW PLAYING[/bold red]", border_style="red")

def get_controls_panel():
    return Panel(
        Align.center("[bold white]ACTIVE SESSION[/bold white]\n[dim]Press Ctrl+C to stop playback and return to terminal[/dim]"),
        title="Controls",
        border_style="blue"
    )

def get_stats_panel():
    try:
        fav_count = len(fav_table.all())
        content = f"[bold green]Offline Songs: {fav_count}[/bold green]\n\n[bold white]Recent Activity:[/bold white]\n"
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
    system = platform.system()
    ffplay_flags = ["-nodisp", "-autoexit", "-loglevel", "quiet", "-infbuf"] 

    if system == "Windows":
        if all(os.path.exists(p) for p in [FFPLAY_PATH, FFMPEG_PATH, FFPROBE_PATH]):
            return [FFPLAY_PATH] + ffplay_flags
        return download_trinity_windows(ffplay_flags)
    
    if shutil.which("mpv"): return ["mpv", "--no-video", "--no-terminal"]
    if shutil.which("ffplay"): return ["ffplay"] + ffplay_flags
        
    console.print("[bold red]Setup Failure:[/bold red] No player found. Run 'pkg install ffmpeg mpv' (Termux).")
    sys.exit(1)

def download_trinity_windows(flags):
    console.print("\n[bold yellow]Downloading Audio Engine...[/bold yellow]")
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    try:
        response = requests.get(url, stream=True)
        buffer = io.BytesIO()
        with Progress(SpinnerColumn(), BarColumn(), TextColumn("[progress.percentage]{task.percentage:>3.0f}%"), console=console) as progress:
            task = progress.add_task("[green]Fetching Engine...", total=int(response.headers.get('content-length', 0)))
            for chunk in response.iter_content(chunk_size=8192):
                buffer.write(chunk)
                progress.update(task, advance=len(chunk))
        buffer.seek(0)
        with zipfile.ZipFile(buffer) as z:
            for file in z.namelist():
                if file.endswith("bin/ffplay.exe"): open(FFPLAY_PATH, "wb").write(z.read(file))
                elif file.endswith("bin/ffmpeg.exe"): open(FFMPEG_PATH, "wb").write(z.read(file))
                elif file.endswith("bin/ffprobe.exe"): open(FFPROBE_PATH, "wb").write(z.read(file))
        return [FFPLAY_PATH] + flags
    except Exception as e:
        console.print(f"[bold red]Installation Failed: {e}[/bold red]"); sys.exit(1)

def log_history(name, video_id):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{name} | {video_id}\n")
        
# --- USER COMMANDS ---
  # Add this to your imports

@app.command()
def login():
    """Manual Session Setup: Link your YouTube Music cookies.txt."""
    console.print(get_header())
    
    cookie_path = os.path.join(APP_DIR, "cookies.txt")

    # --- STEP 1: Check for existing file ---
    if os.path.exists(cookie_path):
        console.print(f"[bold green]✔ Found:[/bold green] cookies.txt is present in {APP_DIR}")
        action = questionary.select(
            "What would you like to do?",
            choices=[
                "Verify current session",
                "Replace/Update cookies.txt",
                "Exit"
            ],
            pointer="➔"
        ).ask()
    else:
        console.print(f"[bold yellow]⚠ Missing:[/bold yellow] No cookies.txt found in {APP_DIR}")
        action = questionary.select(
            "Session not found. How to proceed?",
            choices=[
                "I have the file (Verify now)",
                "How do I get this file?",
                "Exit"
            ],
            pointer="➔"
        ).ask()

    # --- STEP 2: Handle Actions ---
    if action == "Exit" or action is None:
        return

    if action == "How do I get this file?":
        console.print(Panel(
            f"[white]1. Install the [bold cyan]'Get cookies.txt LOCALLY'[/bold cyan] extension in your browser.\n"
            "2. Go to [bold]music.youtube.com[/bold] and ensure you are logged in.\n"
            "3. Click the extension and export the cookies.\n"
            f"4. Save/Rename the file as [bold]cookies.txt[/bold] and move it to:\n"
            f"[yellow]{APP_DIR}[/yellow][/white]",
            title="Setup Guide", border_style="blue"
        ))
        if questionary.confirm("Open extension download page now?").ask():
            webbrowser.open("https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc")
        return

    if action in ["Verify current session", "I have the file (Verify now)", "Replace/Update cookies.txt"]:
        if not os.path.exists(cookie_path):
            console.print(f"[bold red]Error:[/bold red] Please place the file in {APP_DIR} before verifying.")
            return

        # --- STEP 3: Final Verification ---
        with console.status("[bold green]Verifying session with cookies.txt...[/bold green]"):
            try:
                ydl_opts = get_ydl_opts(use_cookies=True)
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # Test extraction on a standard video to verify the cookies work
                    ydl.extract_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ", download=False)
                console.print("\n[bold green]Success![/bold green] SPCI is authenticated and ready to play.")
            except Exception as e:
                console.print(f"\n[bold red]Verification Failed:[/bold red] {e}")
                console.print("[dim]Note: Ensure the exported file is in 'Netscape' format and you are logged in.[/dim]")           

@app.command()
def add_fav(video_id: str):
    """Downloads a song for offline playback at 128kbps."""
    if platform.system() == "Windows": get_player_command()
    local_path = os.path.join(FAV_DIR, f"{video_id}.mp3")
    
    # Retry logic for cookie/decryption failures
    for use_cookies in [True, False]:
        ydl_opts = get_ydl_opts({
            'format': 'bestaudio/best',
            'outtmpl': local_path.replace('.mp3', ''),
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '128'}],
        }, use_cookies=use_cookies)
        
        if platform.system() == "Windows": ydl_opts['ffmpeg_location'] = BIN_DIR 

        with console.status(f"[bold green]Buffering {video_id}...[/bold green]"):
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
                    fav_table.upsert({'video_id': video_id, 'title': info.get('title'), 'artist': info.get('uploader'), 'path': local_path}, Query().video_id == video_id)
                console.print(f"\n[bold green]Success![/bold green] '{info.get('title')}' saved offline.")
                return
            except Exception as e:
                if "cookie" in str(e).lower() and use_cookies:
                    console.print(f"[yellow]Cookie access failed, retrying in Guest Mode...[/yellow]")
                    continue
                console.print(f"[bold red]Download Error:[/bold red] {e}")
                return

@app.command()
def play(query: str):
    """Plays music, checking offline favorites before YouTube."""
    Song = Query()
    offline_entry = fav_table.get((Song.video_id == query) | (Song.title == query))

    if offline_entry and os.path.exists(offline_entry['path']):
        title, artist, audio_source, is_offline = offline_entry['title'], offline_entry['artist'], offline_entry['path'], True
    else:
        try:
            with console.status(f"[bold green]Searching online for '{query}'...[/bold green]"):
                results = get_music(query)
                if not results: return
                song = results[0]
                vid, title, artist = song['videoId'], song['title'], song['artists']
                check = fav_table.get(Song.video_id == vid)
                if check and os.path.exists(check['path']):
                    audio_source, is_offline = check['path'], True
                else:
                    audio_source = None
                    for use_cookies in [True, False]:
                        try:
                            with yt_dlp.YoutubeDL(get_ydl_opts(use_cookies=use_cookies)) as ydl:
                                info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
                                audio_source, is_offline = info.get('url'), False
                                break
                        except Exception as e:
                            if "cookie" in str(e).lower() and use_cookies:
                                console.print(f"[yellow]Cookie access failed, retrying in Guest Mode...[/yellow]")
                                continue
                            raise
                    if not audio_source:
                        console.print(f"[bold red]Error:[/bold red] Could not get audio stream")
                        return
        except Exception as e: console.print(f"[bold red]Error:[/bold red] {e}"); return

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
    except KeyboardInterrupt: process.terminate()

@app.command()
def show_fav():
    """Lists all offline favorite songs."""
    favs = fav_table.all()
    if not favs: console.print("[dim]No favorites found.[/dim]"); return
    table = Table(title="OFFLINE FAVORITES", box=box.HEAVY_EDGE)
    table.add_column("No.", style="dim"); table.add_column("Song Title"); table.add_column("Artist"); table.add_column("Video ID")
    for i, song in enumerate(favs, start=1): table.add_row(str(i), song['title'], song['artist'], song['video_id'])
    console.print(table, justify="center")

@app.command()
def search(query: str):
    """Searches YouTube Music."""
    with console.status(f"[bold green]Searching for '{query}'...[/bold green]"):
        results = get_music(query)
    if results:
        table = Table(title=f"Results for: {query}", box=box.MINIMAL_DOUBLE_HEAD)
        table.add_column("ID", style="green"); table.add_column("Title"); table.add_column("Artist"); table.add_column("Length", justify="right")
        for s in results: table.add_row(s['videoId'], s['title'], s['artists'], s['duration'])
        console.print(table, justify="center")

@app.command()
def delete_fav(video_id: str):
    """Removes a song from disk and database."""
    Song = Query()
    item = fav_table.get(Song.video_id == video_id)
    if item:
        if os.path.exists(item['path']): os.remove(item['path'])
        fav_table.remove(Song.video_id == video_id)
        console.print(f"[bold red]Deleted![/bold red] '{item['title']}' removed.")
    else: console.print("[red]ID not found.[/red]")

@app.command()
def show_history():
    """Displays play history."""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f: history_text = f.read()
        console.print(Panel(history_text, title="History", border_style="blue"))
    else: console.print("[dim]No history found.[/dim]")

@app.command()
def clear_history():
    """Clears history file."""
    if os.path.exists(HISTORY_FILE): os.remove(HISTORY_FILE)
    console.print("[green]History cleared.[/green]")

@app.command(short_help="show help")
def help():
    """Displays the help menu with all commands."""
    table = Table(show_header=True, header_style="bold blue", box=box.ROUNDED)
    table.add_column("Command", width=14, style="cyan")
    table.add_column("Description", style="dim", width=50)
    table.add_row("login", "Auto-link Chrome session for authenticated access")
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

@app.command()
def setup_help():
    """Instructions for global installation."""
    console.print(Panel("Run [bold]pip install -e .[/bold] to enable 'spci' command globally."))

if __name__ == "__main__": app()