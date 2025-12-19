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
import random
from rich.console import Console
from rich.table import Table
from rich.progress import track, Progress, SpinnerColumn, BarColumn, TextColumn
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.align import Align
from rich import box
from getmusic import get_music
import json

__version__ = "1.2.0"

console = Console()
app = typer.Typer()

HISTORY_FILE = "play_history.txt"

# Global configuration for binary storage
APP_DIR = os.path.join(os.path.expanduser("~"), ".spci")
BIN_DIR = os.path.join(APP_DIR, "bin")
FFPLAY_PATH = os.path.join(BIN_DIR, "ffplay.exe")

# --- UI COMPONENTS ---

def make_layout() -> Layout:
    """Define the grid layout for the music player UI."""
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
        Align.center(f"[bold cyan]SPCI MUSIC PLAYER[/bold cyan] v{__version__} | developed by [bold blue][link=https://github.com/ojaswi1234]@ojaswi1234[/link][/bold blue]"),
        box=box.ROUNDED,
        style="white on black"
    )

def get_now_playing_panel(title, artist, visualizer_bars):
    """Generates the Now Playing panel with a visualizer."""
    # Create a fake visualizer string
    vis_string = ""
    for _ in range(30):
        height = random.choice([" ", "▂", "▃", "▄", "▅", "▆", "▇", "█"])
        vis_string += f"[green]{height}[/green]"
    
    content = f"""
[bold white]Title:[/bold white] [yellow]{title}[/yellow]
[bold white]Artist:[/bold white] [cyan]{artist}[/cyan]

[bold magenta]Visualizer:[/bold magenta]
{vis_string}
{vis_string}
    """
    return Panel(content, title="[bold red]Now Playing[/bold red]", border_style="red")

def get_controls_panel():
    return Panel(
        Align.center("[bold white]Playing...[/bold white]\n[dim]Press Ctrl+C to Stop[/dim]"),
        title="Controls",
        border_style="blue"
    )

def get_history_panel():
    """Reads history file and shows last 5 songs."""
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                lines = f.readlines()[-5:] # Get last 5
            history_text = "".join([f"[dim]• {line.split('|')[0].strip()}[/dim]\n" for line in lines])
        else:
            history_text = "[dim]No history yet.[/dim]"
    except:
        history_text = "[red]Error reading history[/red]"

    return Panel(history_text, title="Recent History", border_style="green")

# --- BACKEND LOGIC (Unchanged) ---

def get_player():
    """
    Returns the command list for the best available audio player.
    Windows: Auto-downloads ffplay.exe if missing.
    Linux/Mac: Checks for installed ffplay or mpv.
    """
    system = platform.system()

    # Recommended flags for streaming stability
    ffplay_flags = ["-nodisp", "-autoexit", "-loglevel", "quiet", "-infbuf"] 

    if shutil.which("ffplay"):
        return ["ffplay"] + ffplay_flags
    
    if shutil.which("mpv"):
        return ["mpv", "--no-video"]

    if system == "Windows":
        # Check global location first
        if os.path.exists(FFPLAY_PATH):
            return [FFPLAY_PATH] + ffplay_flags

        local_exe = os.path.abspath("ffplay.exe")
        if os.path.exists(local_exe):
            return [local_exe] + ffplay_flags
        return download_ffplay_windows(ffplay_flags)
    elif system in ["Linux","MacOS" ]:
        subprocess.run(["apt-get", "install", "mpv"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if shutil.which("mpv"):
            return ["mpv", "--no-video"]
        

    console.print(f"\n[bold red]Error: No compatible audio player found on {system}.[/bold red]")
    sys.exit(1)

def download_ffplay_windows(flags):
    """Downloads ffplay.exe for Windows users."""
    console.print("\n[bold yellow]System audio components missing.[/bold yellow]")
    console.print(f"Downloading [bold]FFplay[/bold] to {FFPLAY_PATH}...")
    
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    
    try:
        # Ensure the global bin directory exists
        os.makedirs(BIN_DIR, exist_ok=True)

        response = requests.get(url, stream=True)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        
        buffer = io.BytesIO()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console
        ) as progress:
            task = progress.add_task("[green]Downloading...", total=total_size)
            for chunk in response.iter_content(chunk_size=8192):
                buffer.write(chunk)
                progress.update(task, advance=len(chunk))
        
        buffer.seek(0) # Reset pointer to start of file for reading

        with console.status("[bold green]Extracting ffplay.exe...[/bold green]"):
            with zipfile.ZipFile(buffer) as z:
                for file in z.namelist():
                    if file.endswith("bin/ffplay.exe"):
                        with open(FFPLAY_PATH, "wb") as f:
                            f.write(z.read(file))
                        break
        
        console.print("[bold green]Audio engine ready![/bold green]")
        return [FFPLAY_PATH] + flags

    except Exception as e:
        console.print(f"[bold red]Download failed:[/bold red] {e}")
        sys.exit(1)

def log_history(name, video_id):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{name} | https://www.youtube.com/watch?v={video_id}\n")
        

@app.command(short_help="steps to convert spci to global instead of local")
def setup_help():
   console.print("[bold green]For making SPCI a global command, please use [    pip install -e .   ] command inside its folder.[/bold green]")
        

@app.command(short_help="show help")
def help():
    table = Table(show_header=True, header_style="bold blue", box=box.ROUNDED)
    table.add_column("Command", width=14, style="cyan")
    table.add_column("Description", style="dim", width=50)
    table.add_row("search", "Search for a song")
    table.add_row("play", "Play a song")
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

@app.command(short_help="search")
def search(query: str):
    console.print(f"Searching for: [bold green]{query}[/bold green] ...", style="bold green", justify="center")
    
    # Use a nice spinner while searching
    with console.status("[bold green]Fetching results...[/bold green]", spinner="dots"):
        results = get_music(query)
   
    if results:
        table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
        table.add_column("No.", style="dim", width=4)
        table.add_column("Title", min_width=20, style="bold white")
        table.add_column("Artists", min_width=20, style="cyan")
        table.add_column("Album", min_width=20, style="dim")
        table.add_column("Duration", justify="right", style="green")
        
        for i, song in enumerate(results, start=1):
            table.add_row(str(i), song['title'], song['artists'], song['album'], song['duration'])
        
        console.print(table, justify="center")
    else:
        console.print("[bold red]No results found.[/bold red]")

@app.command(short_help="play")
def play(query: str):
    """
    Search for a song and stream it immediately with a cool UI.
    """
    # 1. Search
    with console.status(f"[bold green]Searching for '{query}'...[/bold green]", spinner="point"):
        results = get_music(query)

    if not results:
        console.print("[bold red]No music found.. (try searching with different keywords)[/bold red]")
        return

    song = results[0]
    title = song['title']
    video_id = song['videoId']
    artist = song['artists']

    log_history(title, video_id)

    # 2. Extract Stream
    stream_url = None
    ydl_opts = {'format': 'bestaudio[ext=m4a]/best', 'quiet': True, 'noplaylist': True}

    with console.status("[bold green]Extracting audio stream...[/bold green]", spinner="earth"):
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

    # 3. Setup UI Layout
    player_cmd = get_player()
    full_cmd = player_cmd + [stream_url]
    
    layout = make_layout()
    layout["header"].update(get_header())
    layout["right"].update(get_history_panel())
    layout["footer"].update(get_controls_panel())

    # 4. Play with Live UI
    try:
        # Live Loop: Updates the visualizer while the song plays
        with Live(layout, refresh_per_second=4, screen=True) as live:
            for i in range(10):
                # Start the player process
                process = subprocess.Popen(full_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                while process.poll() is None: # While process is running
                    # Update visualizer animation
                    layout["left"].update(get_now_playing_panel(title, artist, None))
                    time.sleep(0.25)
        
        console.print("[bold yellow]Playback finished.[/bold yellow]")

    except KeyboardInterrupt:
        process.kill() # Ensure player stops
        console.print("\n[bold yellow]Playback stopped by user.[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]Player Error:[/bold red] {e}")

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