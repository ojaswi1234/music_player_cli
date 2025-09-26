from concurrent.futures import ThreadPoolExecutor
import os
import platform
import subprocess
import time
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import track, Progress
from getmusic import get_music
import json

__version__ = "1.0.0"

console = Console()
app = typer.Typer()


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