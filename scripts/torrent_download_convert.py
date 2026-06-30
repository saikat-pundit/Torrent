import os
import sys
import subprocess
import re
import shutil
import time
from pathlib import Path


def run(cmd, shell=False, show_output=False):
    """Run command with optional real-time output."""
    if isinstance(cmd, str) and not shell:
        shell = True
    
    if show_output:
        return subprocess.run(cmd, shell=shell, check=False)
    return subprocess.run(cmd, shell=shell, capture_output=True, text=True, check=False)


def install_deps():
    """Install system packages."""
    print("Installing dependencies...")
    run("sudo apt-get update -qq")
    run("sudo apt-get install -y -qq aria2 ffmpeg bc")


def download_torrent(magnet, download_dir):
    """Download torrent with 10-second progress updates."""
    print("Starting torrent download...")
    os.makedirs(download_dir, exist_ok=True)
    
    cmd = (
        f"aria2c --seed-time=0 --max-connection-per-server=16 --split=16 "
        f"--dir={download_dir} --console-log-level=notice --summary-interval=10 "
        f"--show-console-readout=true --human-readable=true \"{magnet}\""
    )
    
    result = subprocess.run(cmd, shell=True, check=False)
    if result.returncode != 0:
        print("Download failed!")
        sys.exit(1)
    print("Download complete.")


def get_quality_params(quality):
    """Return encoding parameters for selected quality."""
    configs = {
        "240p": {"scale": "scale=426:-2", "crf": "28", "preset": "medium", 
                 "pix_fmt": "yuv420p", "x265_opts": ""},
        "480p": {"scale": "scale=854:-2", "crf": "24", "preset": "medium", 
                 "pix_fmt": "yuv420p10le", 
                 "x265_opts": '-x265-params "psy-rd=2.0:psy-rdoq=5.0:aq-mode=3:deblock=-1,-1:no-sao=1"'},
        "720p": {"scale": "scale=1280:-2", "crf": "23", "preset": "medium", 
                 "pix_fmt": "yuv420p10le", 
                 "x265_opts": '-x265-params "psy-rd=2.0:psy-rdoq=5.0:aq-mode=3:deblock=-1,-1:no-sao=1"'}
    }
    return configs.get(quality, configs["480p"])


def flatten_dir(directory):
    """Move all files from subdirectories to root directory."""
    print("Flattening directories...")
    dir_path = Path(directory)
    for f in dir_path.rglob("*"):
        if f.is_file() and f.parent != dir_path:
            dest = dir_path / f.name
            c = 1
            while dest.exists():
                dest = dir_path / f"{f.stem}_{c}{f.suffix}"
                c += 1
            shutil.move(str(f), str(dest))
    # Remove empty dirs
    for d in sorted(dir_path.rglob("*"), reverse=True):
        if d.is_dir() and d != dir_path:
            try: d.rmdir()
            except OSError: pass


def find_videos(directory):
    """Find all video files in directory."""
    exts = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm", ".wmv", ".m4v", ".ts", ".mpeg"}
    dir_path = Path(directory)
    if not dir_path.exists():
        return []
    return [f for f in dir_path.iterdir() if f.is_file() and f.suffix.lower() in exts]


def clean_name(name):
    """Remove special characters from filename."""
    name = re.sub(r'[:\/\\?*<>|"\'\[\]{}()!@#$%^&+=→-]', '', name)
    name = re.sub(r'  +', ' ', name).strip()
    name = name.replace(' ', '.')
    return name if name else "video"


def get_video_info(filepath):
    """Extract video metadata using ffprobe."""
    try:
        # Duration
        r = run(f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{filepath}"')
        duration = float(r.stdout.strip().split('.')[0])
        
        # FPS
        r = run(f'ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=noprint_wrappers=1:nokey=1 "{filepath}"')
        fps_str = r.stdout.strip()
        if '/' in fps_str:
            num, den = map(int, fps_str.split('/'))
            fps = num / den if den != 0 else 0
        else:
            fps = float(fps_str)
        
        # Audio channels
        r = run(f'ffprobe -v error -select_streams a:0 -show_entries stream=channels -of default=noprint_wrappers=1:nokey=1 "{filepath}"')
        channels = int(r.stdout.strip()) if r.stdout.strip().isdigit() else 2
        
        return {"duration": duration, "fps": fps, "channels": channels}
    except:
        return {"duration": 0, "fps": 24, "channels": 2}


def convert_video(input_file, output_file, params):
    """Convert video to H.265 with progress logging."""
    info = get_video_info(input_file)
    
    # Video filter
    vf = f"fps=24,{params['scale']}" if info["fps"] > 24 else params["scale"]
    
    # Audio options
    audio = "-c:a aac -b:a 128k -ac 2" if info["channels"] > 2 else "-c:a copy"
    
    # Build command
    cmd = (
        f'ffmpeg -nostdin -i "{input_file}" '
        f'-c:v libx265 -vf "{vf}" -preset {params["preset"]} '
        f'-crf {params["crf"]} -pix_fmt {params["pix_fmt"]} '
        f'{params["x265_opts"]} {audio} -c:s copy '
        f'-map 0:v:0 -map 0:a:0 '
        f'-progress pipe:1 -stats_period 10 -stats '
        f'"{output_file}"'
    )
    
    # Run with real-time output
    process = subprocess.Popen(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1
    )
    
    # Print progress every 10 seconds
    last_print = time.time()
    for line in process.stdout:
        current = time.time()
        if current - last_print >= 10:
            # Extract and display progress info
            if 'speed=' in line or 'frame=' in line:
                # Filter only progress lines
                progress_line = line.strip()
                if any(k in progress_line for k in ['frame=', 'fps=', 'speed=', 'size=', 'time=']):
                    print(f"  {progress_line}")
            last_print = current
    
    process.wait()
    return process.returncode


def format_size(bytes):
    """Convert bytes to human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024.0:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.1f} TB"


def main():
    magnet = os.environ.get('MAGNET_LINK')
    quality = os.environ.get('QUALITY', '480p')
    zip_name = os.environ.get('ZIP_NAME', 'converted_videos')
    
    if not magnet:
        print("Error: MAGNET_LINK not set!")
        sys.exit(1)
    
    print(f"Quality: {quality}")
    
    # Install deps
    install_deps()
    
    # Setup paths
    workspace = os.getcwd()
    download_dir = os.path.join(workspace, "download")
    
    # Download
    download_torrent(magnet, download_dir)
    
    # Prepare files
    print("Preparing files...")
    flatten_dir(download_dir)
    videos = find_videos(download_dir)
    
    if not videos:
        print(f"No video files found in {download_dir}")
        print("Contents:", list(Path(download_dir).iterdir()))
        sys.exit(1)
    
    print(f"Found {len(videos)} video file(s)")
    
    # Conversion params
    params = get_quality_params(quality)
    print(f"Quality: {params['crf']} CRF | {params['preset']} preset")
    
    # Convert
    used_names = set()
    for i, video in enumerate(videos, 1):
        clean = clean_name(video.stem)
        
        # Handle duplicates
        final_name = clean
        c = 1
        while final_name in used_names:
            final_name = f"{clean}_{c}"
            c += 1
        used_names.add(final_name)
        
        output = video.parent / f"{final_name}_converted.mkv"
        orig_size = format_size(video.stat().st_size)
        info = get_video_info(video)
        
        print(f"\n[{i}/{len(videos)}] {video.name}")
        print(f"  Size: {orig_size} | Duration: {int(info['duration']//60)}m{int(info['duration']%60)}s")
        print(f"  Converting...")
        
        # Convert
        exit_code = convert_video(video, output, params)
        
        if exit_code == 0 and output.exists() and output.stat().st_size > 0:
            new_size = format_size(output.stat().st_size)
            print(f"  Done: {output.name} ({new_size})")
            video.unlink()  # Remove original
        else:
            print(f"  Failed to convert: {video.name}")
            sys.exit(1)
            
    # Create zip file
    zip_path = os.path.join(workspace, f"{zip_name}.zip")
    print(f"\nCreating zip: {zip_name}.zip")
    
    import zipfile
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for f in Path(download_dir).iterdir():
            if f.is_file():
                zipf.write(f, f.name)
                print(f"  Added: {f.name}")
    
    print(f"Zip created: {zip_path} ({format_size(os.path.getsize(zip_path))})")
    
    # Summary
    print(f"\nAll conversions complete!")
    print("Final files:")
    for f in Path(download_dir).glob("*.mkv"):
        print(f"  {f.name} ({format_size(f.stat().st_size)})")


if __name__ == "__main__":
    main()
