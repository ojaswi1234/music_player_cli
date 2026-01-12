from ytmusicapi import YTMusic
import os

def get_music(query):
    """
    Fetches music from YouTube Music. 
    Now works even without headers_auth.json by falling back to guest mode.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    auth_path = os.path.join(base_dir, "headers_auth.json")

    try:
        # 1. Try to use the auth file if it exists
        if os.path.exists(auth_path):
            ytmusic = YTMusic(auth_path)
        else:
            # 2. If missing, just use Guest Mode! 
            # This is the 'Better Solution' that avoids the error.
            ytmusic = YTMusic()
            
        search_results = ytmusic.search(query, filter='songs')
        songs = []
        
        for result in search_results:
            songs.append({
                'title': result.get('title'),
                'videoId': result.get('videoId'),
                'artists': ', '.join([artist['name'] for artist in result.get('artists', [])]),
                'album': result.get('album', {}).get('name', 'Single'),
                'duration': result.get('duration', 'N/A'),
            })
        return songs

    except Exception as e:
        # Silently fail or log the error without crashing the UI
        return []

if __name__ == "__main__":
    query = input("Enter song name: ")
    print(get_music(query))