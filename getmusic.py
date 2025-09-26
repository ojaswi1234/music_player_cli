from ytmusicapi import YTMusic
import os

id = None

def get_music(query):
    if not os.path.exists("headers_auth.json"):
        print("Please provide headers_auth.json file from your browser's YouTube Music session.")
        return []

    ytmusic = YTMusic('headers_auth.json')
    search_results = ytmusic.search(query, filter='songs')
    songs = []
    for result in search_results:
        song_info = {
            'title': result['title'],
            'artists': ', '.join([artist['name'] for artist in result['artists']]),
            'album': result['album']['name'] if 'album' in result else 'Single',
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