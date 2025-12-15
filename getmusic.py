from ytmusicapi import YTMusic
import os

id = None

def get_music(query):
    # Get the directory where this script is located
    base_dir = os.path.dirname(os.path.abspath(__file__))
    auth_path = os.path.join(base_dir, "headers_auth.json")

    if not os.path.exists(auth_path):
        print(f"Please provide headers_auth.json file at {auth_path}")
        return []

    ytmusic = YTMusic(auth_path)
    search_results = ytmusic.search(query, filter='songs')
    songs = []
    for result in search_results:
        song_info = {
            'title': result['title'],
            'artists': ', '.join([artist['name'] for artist in result['artists']]),
            'album': result['album']['name'] if result.get('album') else 'Single',
            'duration': result['duration'],
            'videoId': result['videoId']
        }
        
        songs.append(song_info)

    return songs







if __name__ == "__main__":
    query = input("Enter song name or artist: ")
    results = get_music(query)
    if results:
        for i, song in enumerate(results, start=1):
            print(f"{i}. {song['title']} by {song['artists']} [{song['album']}] - {song['duration']}")
    else:
        print("No results found.")