from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name='spci-sonic-pulse',
    version='2.0.6',
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        'typer',
        'rich',
        'requests',
        'yt-dlp',
        'python-vlc',
        'ytmusicapi',
        'tinydb'
        
    ],
    entry_points={
        'console_scripts': [
            'spci=spci.mp:app',
        ],
    },
)