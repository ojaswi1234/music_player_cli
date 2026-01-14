# SPCI - Sonic Pulse CLI Music Player

A powerful and lightweight command-line music player that lets you search, play, and manage your favorite music directly from your terminal.

## Features

- **Search:** Find music online.
- **Play:** Play songs instantly (checks offline favorites first).
- **Favorites:** Save songs locally for offline access.
- **History:** Keep track of your recently played tracks.
- **Rich UI:** Beautiful terminal interface powered by `rich`.

## Installation

### Prerequisites

- **Python 3.8+**
- **VLC Media Player:** Ensure VLC is installed on your system as it is used for audio playback.
- **FFmpeg:** Required for processing audio streams.

### Install via PyPI

```bash
pip install spci-sonic-pulse
```

## Usage

Once installed, you can use the `spci` command:

```bash
# Search for music
spci search "Your Song Name"

# Play a song
spci play "Your Song Name"

# View favorites
spci show-fav

# View play history
spci show-history

# Initial setup (if required)
spci setup
```

## Commands

- `search`: Find music online.
- `play`: Play a song (checks offline first).
- `show-fav`: View and manage your offline favorites.
- `add-fav`: Add a song to your favorites.
- `delete-fav`: Remove a song from your favorites.
- `show-history`: Display playback history.
- `clear-history`: Clear your playback history.
- `setup`: Run initial configuration.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
