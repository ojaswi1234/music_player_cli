import yt_dlp
import os

def get_music(query):
    """
    Searches YouTube and filters results to include only song-length videos.
    """
    # Define your maximum duration in seconds (e.g., 6 minutes)
    MAX_DURATION = 360 

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'nocheckcertificate': True,
    }
    
    # We add "audio" and "song" to the query for better results
    search_query = f"ytsearch15:{query} song audio"
    
    songs = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(search_query, download=False)
            
            if 'entries' in result:
                for entry in result['entries']:
                    duration_sec = entry.get('duration')
                    
                    # FILTER: Skip videos that are too long or have no duration info
                    if not duration_sec or duration_sec > MAX_DURATION:
                        continue
                        
                    duration_str = f"{int(duration_sec // 60)}:{int(duration_sec % 60):02d}"
                        
                    songs.append({
                        'title': entry.get('title'),
                        'videoId': entry.get('id'),
                        'artists': entry.get('uploader') or "Unknown",
                        'album': "YouTube",
                        'duration': duration_str
                    })
    except Exception as e:
        print(f"\n[bold red][!] Search Error:[/bold red] {e}")
        
    return songs

if __name__ == "__main__":
    query = input("Search YouTube: ")
    results = get_music(query)
    if results:
        for i, song in enumerate(results, start=1):
            print(f"{i}. {song['title']} by {song['artists']} - {song['duration']}")