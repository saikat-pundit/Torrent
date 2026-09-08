import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

def download_audio(url):
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
        url
    ]
    
    result = subprocess.run(opts, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return None
    
    audio_files = list(Path(".").glob("*.mp3"))
    if not audio_files:
        return None
    
    return str(max(audio_files, key=lambda f: f.stat().st_mtime))

def main():
    url = os.environ.get("YOUTUBE_URL") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not url:
        sys.exit(1)
    
    audio_file = download_audio(url)
    if audio_file:
        info = {
            "file_name": Path(audio_file).name,
            "size": Path(audio_file).stat().st_size,
            "timestamp": datetime.now().isoformat()
        }
        with open("release_info.json", "w") as f:
            json.dump(info, f)
        print(f"SUCCESS:{audio_file}")

if __name__ == "__main__":
    main()
