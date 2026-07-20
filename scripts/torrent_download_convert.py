import os
import sys
import subprocess
import re
import shutil
import zipfile
from pathlib import Path


def run(cmd, shell=False):
    """Run command and return result."""
    if isinstance(cmd, str) and not shell:
        shell = True
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
    print("Download complete.\n")


def get_quality_params(quality):
    """Return encoding parameters with FPS caps for each quality."""
    configs = {
        "480p": {
            "scale": "scale=854:-2",
            "crf": "24",
            "preset": "medium",
            "pix_fmt": "yuv420p10le",
            "x265_opts": '-x265-params "psy-rd=2.0:psy-rdoq=5.0:aq-mode=3:deblock=-1,-1:no-sao=1"',
            "max_fps": 26,
            "codec": "libx265",
            "description": "H.265 480p"
        },
        "720p": {
            "scale": "scale=1280:-2",
            "crf": "23",
            "preset": "medium",
            "pix_fmt": "yuv420p10le",
            "x265_opts": '-x265-params "psy-rd=2.0:psy-rdoq=5.0:aq-mode=3:deblock=-1,-1:no-sao=1"',
            "max_fps": 30,
            "codec": "libx265",
            "description": "H.265 720p"
        },
        "480p-av1": {
    "scale": "scale=854:-2",
    "crf": "37",              # ← change from 35
    "preset": "7",            # ← change from 6 (faster)
    "pix_fmt": "yuv420p10le",
    "x265_opts": "",
    "max_fps": 25,            # ← change from 26
    "codec": "libsvtav1",
    "description": "AV1 480p (Ultra Storage)"
},
"720p-av1": {
    "scale": "scale=1280:-2",
    "crf": "34",
    "preset": "8",
    "pix_fmt": "yuv420p10le",
    "x265_opts": "",
    "max_fps": 30,
    "codec": "libsvtav1",
    "description": "AV1 720p"
}
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
    for d in sorted(dir_path.rglob("*"), reverse=True):
        if d.is_dir() and d != dir_path:
            try:
                d.rmdir()
            except OSError:
                pass


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
        r = run(f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{filepath}"')
        duration = float(r.stdout.strip().split('.')[0])

        r = run(f'ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=noprint_wrappers=1:nokey=1 "{filepath}"')
        fps_str = r.stdout.strip()
        if '/' in fps_str:
            num, den = map(int, fps_str.split('/'))
            fps = num / den if den != 0 else 0
        else:
            fps = float(fps_str) if fps_str else 0

        r = run(f'ffprobe -v error -select_streams a:0 -show_entries stream=channels -of default=noprint_wrappers=1:nokey=1 "{filepath}"')
        channels = int(r.stdout.strip()) if r.stdout.strip().isdigit() else 2

        return {"duration": duration, "fps": fps, "channels": channels}
    except:
        return {"duration": 0, "fps": 0, "channels": 2}


def convert_video(input_file, output_file, params):
    """Convert video to H.265 or AV1 with real-time stderr output."""
    info = get_video_info(input_file)
    
    # Build video filter with FPS cap
    vf_parts = []
    
    # Apply FPS cap: if source FPS > max_fps, cap it; otherwise keep original
    if info["fps"] > 0 and info["fps"] > params["max_fps"]:
        vf_parts.append(f"fps={params['max_fps']}")
    
    vf_parts.append(params["scale"])
    vf_filter = ",".join(vf_parts)
    
    # Build ffmpeg command based on codec
    if params["codec"] == "libsvtav1":
        # SVT-AV1 encoding - Keep ALL audio & subtitle tracks
        cmd = (
            f'ffmpeg -nostdin -i "{input_file}" '
            f'-map 0:v -map 0:a -map 0:s? '  # Keep all video, audio, subtitle tracks
            f'-c:v {params["codec"]} -vf "{vf_filter}" '
            f'-crf {params["crf"]} -preset {params["preset"]} '
            f'-pix_fmt {params["pix_fmt"]} '
            f'-svtav1-params "tune=0:enable-overlays=1" '
            f'-c:a aac -b:a 128k '  # Convert ALL audio tracks to 128k AAC
            f'-c:s copy '  # Keep ALL subtitles (no re-encoding)
            f'-stats_period 10 -stats '
            f'"{output_file}" -y'
        )
    else:
        # H.265 encoding - Keep ALL audio & subtitle tracks
        cmd = (
            f'ffmpeg -nostdin -i "{input_file}" '
            f'-map 0:v -map 0:a -map 0:s? '  # Keep all video, audio, subtitle tracks
            f'-c:v {params["codec"]} -vf "{vf_filter}" -preset {params["preset"]} '
            f'-crf {params["crf"]} -pix_fmt {params["pix_fmt"]} '
            f'{params["x265_opts"]} '
            f'-c:a aac -b:a 128k '  # Convert ALL audio tracks to 128k AAC
            f'-c:s copy '  # Keep ALL subtitles (no re-encoding)
            f'-stats_period 10 -stats '
            f'"{output_file}" -y'
        )
    
    # Run with stderr piped for real-time display
    process = subprocess.Popen(
        cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, bufsize=1
    )
    
    # Print stderr in real-time (FFmpeg sends stats to stderr)
    for line in process.stderr:
        print(line, end='', flush=True)
    
    process.wait()
    return process.returncode


def format_size(size_bytes):
    """Convert bytes to human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def main():
    magnet = os.environ.get('MAGNET_LINK')
    quality = os.environ.get('QUALITY', '480p')
    zip_name = os.environ.get('ZIP_NAME', 'converted_videos')
    
    if not magnet:
        print("Error: MAGNET_LINK not set!")
        sys.exit(1)
    
    print(f"Quality: {quality}\n")
    
    install_deps()
    
    workspace = os.getcwd()
    download_dir = os.path.join(workspace, "download")
    
    # Download torrent
    download_torrent(magnet, download_dir)
    
    # Prepare files
    print("Preparing files...")
    flatten_dir(download_dir)
    videos = find_videos(download_dir)
    
    if not videos:
        print(f"No video files found in {download_dir}")
        print("Contents:", list(Path(download_dir).iterdir()))
        sys.exit(1)
    
    print(f"Found {len(videos)} video file(s)\n")
    
    # Get quality params
    params = get_quality_params(quality)
    print(f"Settings: {params['description']} | CRF: {params['crf']} | Preset: {params['preset']} | Max FPS: {params['max_fps']}\n")
    
    # Convert videos
    used_names = set()
    for i, video in enumerate(videos, 1):
        clean = clean_name(video.stem)
        
        final_name = clean
        c = 1
        while final_name in used_names:
            final_name = f"{clean}_{c}"
            c += 1
        used_names.add(final_name)
        
        output = video.parent / f"{final_name}_converted.mkv"
        orig_size = format_size(video.stat().st_size)
        info = get_video_info(video)
        
        print(f"[{i}/{len(videos)}] {video.name}")
        print(f"  Size: {orig_size} | Duration: {int(info['duration']//60)}m{int(info['duration']%60)}s | FPS: {info['fps']:.2f}")
        
        # Show FPS action
        if info["fps"] > params["max_fps"]:
            print(f"  Capping FPS: {info['fps']:.2f} -> {params['max_fps']}")
        else:
            print(f"  Keeping original FPS: {info['fps']:.2f}")
        
        print(f"  Converting with {params['codec']}...")
        
        exit_code = convert_video(video, output, params)
        
        if exit_code == 0 and output.exists() and output.stat().st_size > 0:
            new_size = format_size(output.stat().st_size)
            print(f"  Done: {output.name} ({new_size})\n")
            video.unlink()
        else:
            print(f"  Failed to convert: {video.name}\n")
            sys.exit(1)
    
    # Create zip
    zip_path = os.path.join(workspace, f"{zip_name}.zip")
    print(f"Creating zip: {zip_name}.zip")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for f in Path(download_dir).iterdir():
            if f.is_file():
                zipf.write(f, f.name)
                print(f"  Added: {f.name}")
    
    zip_size = format_size(os.path.getsize(zip_path))
    print(f"Zip created: {zip_name}.zip ({zip_size})")
    
    print(f"\nAll conversions complete!")


if __name__ == "__main__":
    main()
