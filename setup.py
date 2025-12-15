from setuptools import setup

setup(
    name='spci',
    version='1.0.0',
    py_modules=['mp', 'getmusic'],
    install_requires=[
        'typer',
        'rich',
        'requests',
        'yt-dlp',
        'python-vlc',
        'ytmusicapi'
    ],
    entry_points={
        'console_scripts': [
            'musicplayer=mp:app',
        ],
    },
)