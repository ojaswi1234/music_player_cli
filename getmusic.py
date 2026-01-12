from ytmusicapi import YTMusic
import os

id = None

def get_music(query):
    # Get the directory where this script is located
    base_dir = os.path.dirname(os.path.abspath(__file__))
    auth_path = os.path.join(base_dir, "headers_auth.json")

    if not os.path.exists(auth_path):
        print(f"\n[!] Authentication file missing: {auth_path}")
        print("-" * 60)
        print("To generate 'headers_auth.json':")
        print("1. Open https://music.youtube.com in your browser (ensure you are logged in).")
        print("2. Open Developer Tools (F12), go to the 'Network' tab.")
        print("3. Search for any song to trigger network requests.")
        print("4. Find a request like 'search' or 'browse' (filter by 'XHR' or 'Fetch').")
        print("5. Right-click the request > Copy > Copy Request Headers.")
        print("6. Run the following command in your terminal:")
        print("   ytmusicapi browser")
        print("7. Paste the copied headers when prompted.")
        print(f"8. This will generate 'browser.json'. Rename it to 'headers_auth.json' and move it to: {base_dir}")
        print("-" * 60)
        return []

    ytmusic = YTMusic(auth_path)
    search_results = ytmusic.search(query, filter='songs')
    songs = []
    for result in search_results:
        song_info = {
            'title': result['title'],
            'videoId': result['videoId'],
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