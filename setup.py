from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name='spci-sonic-pulse',
    version='2.0.9',
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="MIT",
   classifiers = [
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Topic :: Multimedia :: Sound/Audio :: Players",
    "Topic :: Multimedia :: Sound/Audio :: Analysis",
    "Environment :: Console",
    "Intended Audience :: End Users/Desktop",
    "Development Status :: 5 - Production/Stable",
    ],
    keywords = ["music-player", "cli", "terminal", "youtube", "audio", "rich-ui", "sonic-pulse"],
    install_requires=[
        'typer',
        'rich',
        'requests',
        'yt-dlp',
        'python-vlc',
        'ytmusicapi',
        'tinydb'
        
    ],
    python_requires='>=3.6',
    
    entry_points={
        'console_scripts': [
            'spci=spci.mp:app',
        ],
    },
)