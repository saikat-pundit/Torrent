#!/usr/bin/env python3
import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

def download_audio(url, cookies_file=None):
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except:
        subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp"], check=True)
    
    opts = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--no-playlist",
        "--output", "%(title)s.%(ext)s",
        "--quiet",
        "--no-warnings",
    ]
    
    if cookies_file and os.path.exists(cookies_file):
        opts.extend(["--cookies", cookies_file])
    
    opts.append(url)
    
    result = subprocess.run(opts, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return None
    
    audio_files = list(Path(".").glob("*.mp3"))
    if not audio_files:
        return None
    
    return str(max(audio_files, key=lambda f: f.stat().st_mtime))

def main():
    url = os.environ.get("YOUTUBE_URL")
    cookies = os.environ.get("COOKIES_FILE")
    
    if not url and len(sys.argv) > 1:
        url = sys.argv[1]
    if not url:
        sys.exit(1)
    
    audio_file = download_audio(url, cookies)
    if audio_file:
        info = {
            "file_name": Path(audio_file).name,
            "size": Path(audio_file).stat().st_size,
            "timestamp": datetime.now().isoformat()
        }
        with open("release_info.json", "w") as f:
            json.dump(info, f)
        print(f"SUCCESS:{audio_file}")
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
