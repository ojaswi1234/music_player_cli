from concurrent.futures import ThreadPoolExecutor
import os
import platform
import subprocess
import time
import sys
import ctypes
import typer
import requests
import yt_dlp
from rich.console import Console
from rich.table import Table
from rich.progress import track, Progress
from getmusic import get_music
import json

__version__ = "1.0.0"

console = Console()
app = typer.Typer()

# --- AUTOMATIC VLC INSTALLATION LOGIC ---
def install_vlc():
    """
    Attempts to install VLC Media Player matching the Python architecture.
    Returns True if installation commands ran successfully, False otherwise.
    """
    console.print("\n[bold red]VLC Media Player not found![/bold red]")
    console.print("VLC is required to stream audio. Attempting automatic installation...\n")

    # 1. Try installing via Winget (cleanest method on Windows 10/11)
    try:
        console.print("[yellow]Method 1: Trying Windows Package Manager (Winget)...[/yellow]")
        # --silent argument attempts to install without nagging prompts
        subprocess.run(["winget", "install", "-e", "--id", "VideoLAN.VLC", "--silent"], check=True)
        console.print("[bold green]VLC installed successfully via Winget![/bold green]")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        console.print("[red]Winget failed or not available.[/red]")

    # 2. Fallback: Direct Download
    console.print("[yellow]Method 2: Downloading installer directly...[/yellow]")
    
    # Check architecture (Match VLC bits to Python bits)
    is_64bits = sys.maxsize > 2**32
    vlc_ver = "3.0.21"
    base_url = "https://get.videolan.org/vlc"
    
    if is_64bits:
        url = f"{base_url}/{vlc_ver}/win64/vlc-{vlc_ver}-win64.exe"
    else:
        url = f"{base_url}/{vlc_ver}/win32/vlc-{vlc_ver}-win32.exe"
    
    installer_name = "vlc_installer.exe"
    
    try:
        with console.status(f"[bold green]Downloading VLC ({vlc_ver})...[/bold green]"):
            response = requests.get(url, stream=True)
            with open(installer_name, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        console.print("[bold green]Download complete. Launching installer...[/bold green]")
        console.print("[bold yellow]Please follow the installation prompts (Click 'Next' -> 'Install').[/bold yellow]")
        
        # Run the installer and wait for it to finish
        subprocess.run([installer_name], check=True)
        
        # Cleanup
        if os.path.exists(installer_name):
            os.remove(installer_name)
            
        return True
    except Exception as e:
        console.print(f"[bold red]Installation failed:[/bold red] {e}")
        return False

# --- SAFE IMPORT (RUNS ONCE AT STARTUP) ---
# This block ensures VLC is available before the app even starts.
try:
    # Try to import VLC. If installed, this works.
    import vlc
    # Check if the DLL actually loads (sometimes import succeeds but DLL is missing)
    instance = vlc.Instance()
    instance.release()
except (OSError, FileNotFoundError, AttributeError, NameError, ImportError):
    # If ANY error occurs during import/loading, try to install
    success = install_vlc()
    if success:
        print("\n**************************************************")
        print("VLC Installed Successfully!")
        print("Please RESTART this script to apply changes.")
        print("**************************************************\n")
        sys.exit(0)
    else:
        print("Could not install VLC automatically.")
        print("Please install it manually from: https://www.videolan.org/vlc/")
        sys.exit(1)

# ----------------------------------------

HISTORY_FILE = "play_history.txt"

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
    table.add_row("pause", "Pause the current song")
    table.add_row("stop", "Stop the current song")
    table.add_row("next", "Play the next song")
    table.add_row("previous", "Play the previous song")
    table.add_row("show-history", "Show the play history")
    table.add_row("clear-history", "Clear the play history")
    table.add_row("repeat", "Turn On/Off repeat mode")

    console.print("""[bold green ]
      mmmm   mmmmmm    mmmm   mm#mm
    #"       #    m   #   "     #   
    "#mmm    #mmm#m  #          #   
        "#   #       #    "     #   
    "mmm#"   #        "mmmm   mm#mm
    [/bold green ]""", justify="center", style="bold green", highlight=False)
    console.print(
    "\n"+
    f"[bold green size=24]Version: {__version__}[/bold green size=24]"+
    "\n"+
        "[blue]A Simple Music Player CLI Application[/blue]"
    ,justify="center", style="bold green", highlight=False
    )
    console.print("\n")
    console.print(table, justify="center", style="bold green", highlight=False)

@app.command(short_help="search")
def search(query: str):
    global last_search_results
    console.print(f"Searching for: [bold green]{query}[/bold green] ...........", style="bold green", justify="center")
    console.print("\n")
    console.print("Here are some results! 🎵", style="bold green", justify="center")
    console.print("\n")
    for i in track(range(4), description="Processing..."):
        time.sleep(1)

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
    Search for a song and stream it immediately without downloading.
    """
    # 1. Search for the song using your existing get_music function
    with console.status(f"[bold green]Searching for '{query}'...[/bold green]"):
        results = get_music(query)

    if not results:
        console.print("[bold red]No music found.[/bold red]")
        return

    # Automatically pick the first result
    song = results[0]
    title = song['title']
    video_id = song['videoId']
    artist = song['artists']

    # Log to history
    log_history(title, video_id)

    console.print(f"[bold blue]Found:[/bold blue] {title} by {artist}")

    # 2. Extract the stream URL using yt-dlp
    stream_url = None
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'noplaylist': True,
    }

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

    # 3. Play using VLC
    console.print(f"[bold green]Now Playing:[/bold green] {title} 🎵")
    console.print("[dim]Press Ctrl+C to stop playback.[/dim]")
    
    # REMOVED: install_vlc() - This was redundant and caused re-installation loops.
    
    # Initialize VLC
    instance = vlc.Instance()
    player = instance.media_player_new()
    media = instance.media_new(stream_url)
    player.set_media(media)
    
    player.play()

    # Keep the script running while playing
    try:
        while True:
            state = player.get_state()
            # Stop if the song has ended
            if state == vlc.State.Ended:
                break
            # Small sleep to prevent high CPU usage
            time.sleep(0.5)
    except KeyboardInterrupt:
        player.stop()
        console.print("\n[bold yellow]Playback stopped.[/bold yellow]")

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