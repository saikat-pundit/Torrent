import os
import sys
import subprocess
import json
import re
import shutil
from pathlib import Path
from collections import defaultdict


def run_command(cmd, shell=False, capture_output=True):
    """Run a shell command and return result."""
    try:
        if isinstance(cmd, str) and not shell:
            shell = True
        
        result = subprocess.run(
            cmd,
            shell=shell,
            capture_output=capture_output,
            text=True,
            check=False
        )
        return result
    except Exception as e:
        print(f"❌ Command failed: {e}")
        sys.exit(1)


def install_dependencies():
    """Install required system packages."""
    print("📦 Installing dependencies...")
    run_command("sudo apt-get update")
    run_command("sudo apt-get install -y aria2 ffmpeg bc")


def download_torrent(magnet_link, download_dir):
    """Download torrent using aria2c."""
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🎯 STARTING TORRENT DOWNLOAD")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    # Create download directory if it doesn't exist
    os.makedirs(download_dir, exist_ok=True)
    
    cmd = [
        "aria2c",
        "--seed-time=0",
        "--max-connection-per-server=16",
        "--split=16",
        f"--dir={download_dir}",
        "--console-log-level=notice",
        "--summary-interval=1",
        "--show-console-readout=true",
        "--human-readable=true",
        magnet_link
    ]
    
    result = subprocess.run(cmd, check=False)
    
    if result.returncode != 0:
        print("❌ Torrent download failed!")
        sys.exit(1)
    
    print("")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("✅ DOWNLOAD COMPLETE")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("")


def get_quality_params(quality):
    """Get encoding parameters based on quality setting."""
    params = {
        "240p": {
            "scale_filter": "scale=426:-2",
            "crf_value": "28",
            "preset": "medium",
            "quality_name": "240p",
            "color_depth": "yuv420p",
            "x265_params": ""
        },
        "480p": {
            "scale_filter": "scale=854:-2",
            "crf_value": "24",
            "preset": "medium",
            "quality_name": "480p",
            "color_depth": "yuv420p10le",
            "x265_params": '-x265-params "psy-rd=2.0:psy-rdoq=5.0:aq-mode=3:deblock=-1,-1:no-sao=1"'
        },
        "720p": {
            "scale_filter": "scale=1280:-2",
            "crf_value": "23",
            "preset": "medium",
            "quality_name": "720p",
            "color_depth": "yuv420p10le",
            "x265_params": '-x265-params "psy-rd=2.0:psy-rdoq=5.0:aq-mode=3:deblock=-1,-1:no-sao=1"'
        }
    }
    
    return params.get(quality, params["480p"])


def flatten_directories(download_dir):
    """Move all files from subdirectories to current directory."""
    print("Flattening subdirectories...")
    
    download_path = Path(download_dir)
    for file in download_path.rglob("*"):
        if file.is_file() and file.parent != download_path:
            dest = download_path / file.name
            counter = 1
            while dest.exists():
                dest = download_path / f"{file.stem}_{counter}{file.suffix}"
                counter += 1
            shutil.move(str(file), str(dest))
    
    # Remove empty directories
    for dir_path in sorted(download_path.rglob("*"), reverse=True):
        if dir_path.is_dir() and dir_path != download_path:
            try:
                dir_path.rmdir()
            except OSError:
                pass


def find_video_files(download_dir):
    """Find all video files in download directory."""
    video_extensions = {".mp4", ".mkv", ".avi", ".mov", ".flv", 
                       ".webm", ".wmv", ".m4v", ".ts", ".mpeg"}
    
    video_files = []
    download_path = Path(download_dir)
    
    if not download_path.exists():
        print(f"❌ Download directory not found: {download_dir}")
        return video_files
    
    for file in download_path.iterdir():
        if file.is_file() and file.suffix.lower() in video_extensions:
            video_files.append(file)
    
    return video_files


def clean_filename(name):
    """Clean filename by removing special characters."""
    # Remove special characters
    cleaned = re.sub(r'[:\/\\?*<>|"\'\[\]{}()!@#$%^&+=→-]', '', name)
    # Replace multiple spaces with single space
    cleaned = re.sub(r'  +', ' ', cleaned)
    # Trim spaces
    cleaned = cleaned.strip()
    # Replace spaces with dots
    cleaned = cleaned.replace(' ', '.')
    
    if not cleaned:
        cleaned = "video"
    
    return cleaned


def get_video_info(file_path):
    """Get video file information using ffprobe."""
    try:
        # Get duration
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = float(result.stdout.strip().split('.')[0])
        
        # Get FPS
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        fps_str = result.stdout.strip()
        
        # Calculate FPS from fraction
        if '/' in fps_str:
            num, den = map(int, fps_str.split('/'))
            fps = num / den if den != 0 else 0
        else:
            fps = float(fps_str)
        
        # Get audio channels
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=channels",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        audio_channels = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 2
        
        return {
            "duration": duration,
            "fps": fps,
            "audio_channels": audio_channels
        }
    except Exception as e:
        print(f"⚠️  Warning: Could not get video info: {e}")
        return {
            "duration": 0,
            "fps": 24,
            "audio_channels": 2
        }


def convert_video(input_file, output_file, quality_params):
    """Convert video to H.265/HEVC."""
    info = get_video_info(input_file)
    
    # Build video filter
    if info["fps"] > 24:
        vf_filter = f"fps=24,{quality_params['scale_filter']}"
    else:
        vf_filter = quality_params["scale_filter"]
    
    # Build audio options
    if info["audio_channels"] > 2:
        audio_opts = "-c:a aac -b:a 128k -ac 2"
    else:
        audio_opts = "-c:a copy"
    
    # Build ffmpeg command
    cmd = (
        f"ffmpeg -nostdin -i \"{input_file}\" "
        f"-c:v libx265 "
        f"-vf \"{vf_filter}\" "
        f"-preset {quality_params['preset']} "
        f"-crf {quality_params['crf_value']} "
        f"-pix_fmt {quality_params['color_depth']} "
        f"{quality_params['x265_params']} "
        f"{audio_opts} "
        f"-c:s copy "
        f"-map 0:v:0 "
        f"-map 0:a:0 "
        f"-progress /tmp/progress.txt "
        f"-stats "
        f"\"{output_file}\""
    )
    
    # Run conversion
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    return result.returncode, result.stdout, result.stderr


def format_size(size_bytes):
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def main():
    """Main function."""
    # Get inputs from environment variables
    magnet_link = os.environ.get('MAGNET_LINK')
    quality = os.environ.get('QUALITY', '480p')
    zip_name = os.environ.get('ZIP_NAME', 'converted_videos')
    upload_to = os.environ.get('UPLOAD_TO', 'artifacts')
    
    if not magnet_link:
        print("❌ MAGNET_LINK environment variable not set!")
        sys.exit(1)
    
    print("=" * 70)
    print("TORRENT DOWNLOAD AND CONVERT TO H.265")
    print("=" * 70)
    print(f"Quality: {quality}")
    print(f"Upload to: {upload_to}")
    print("=" * 70)
    print()
    
    # Install dependencies
    install_dependencies()
    
    # Define download directory (absolute path)
    workspace_dir = os.getcwd()
    download_dir = os.path.join(workspace_dir, "download")
    
    # Download torrent
    download_torrent(magnet_link, download_dir)
    
    # Get quality parameters
    quality_params = get_quality_params(quality)
    
    # Prepare files
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📁 PREPARING FILES")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    flatten_directories(download_dir)
    video_files = find_video_files(download_dir)
    
    if not video_files:
        print("❌ No video files found!")
        print(f"Contents of {download_dir}:")
        for item in Path(download_dir).iterdir():
            print(f"  - {item.name}")
        sys.exit(1)
    
    print(f"✅ Found {len(video_files)} video file(s)")
    print()
    
    # Convert videos
    used_names = {}
    current_file = 0
    
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🎬 STARTING VIDEO CONVERSION")
    print(f"📊 Quality: {quality_params['quality_name']} | CRF: {quality_params['crf_value']} | Preset: {quality_params['preset']}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    
    for input_video in video_files:
        current_file += 1
        basename = input_video.name
        basename_wo_ext = input_video.stem
        
        # Clean filename
        clean_name = clean_filename(basename_wo_ext)
        
        # Handle duplicate names
        final_name = clean_name
        counter = 1
        while final_name in used_names:
            final_name = f"{clean_name}_{counter}"
            counter += 1
        used_names[final_name] = True
        
        output_file = input_video.parent / f"{final_name}_converted.mkv"
        
        # Get file info
        orig_size = format_size(input_video.stat().st_size)
        info = get_video_info(input_video)
        duration_min = int(info["duration"] // 60)
        duration_sec = int(info["duration"] % 60)
        
        # Print file info
        print("┌──────────────────────────────────────────────────────────────────┐")
        print(f"│ 📹 [{current_file}/{len(video_files)}] Processing: {basename[:54]:<54} │")
        print("├──────────────────────────────────────────────────────────────────┤")
        print(f"│ 💾 Original size: {orig_size:<52} │")
        print(f"│ ⏱️  Duration: {duration_min} min {duration_sec} sec{'':<41} │")
        print(f"│ 🎯 Target quality: {quality_params['quality_name']:<50} │")
        print("├──────────────────────────────────────────────────────────────────┤")
        print("│ 🔄 Conversion in progress...                                      │")
        print("└──────────────────────────────────────────────────────────────────┘")
        print()
        print("🔄 Running FFmpeg conversion with real-time stats...")
        print()
        
        # Run conversion
        exit_code, stdout, stderr = convert_video(input_video, output_file, quality_params)
        
        print(f"✅ FFmpeg process completed with exit code: {exit_code}")
        print()
        print("📝 Last few lines of FFmpeg output:")
        for line in stdout.split('\n')[-10:]:
            if line.strip():
                print(f"   {line}")
        print()
        
        if exit_code == 0 and output_file.exists() and output_file.stat().st_size > 0:
            new_size = format_size(output_file.stat().st_size)
            print("┌──────────────────────────────────────────────────────────────────┐")
            print("│ ✅ CONVERSION SUCCESSFUL!                                         │")
            print("├──────────────────────────────────────────────────────────────────┤")
            print(f"│ 📁 Output: {output_file.name[:55]:<55} │")
            print(f"│ 💾 New size: {new_size:<52} │")
            print("└──────────────────────────────────────────────────────────────────┘")
            print()
            
            # Remove original file
            input_video.unlink()
        else:
            print("┌──────────────────────────────────────────────────────────────────┐")
            print("│ ❌ CONVERSION FAILED!                                             │")
            print("├──────────────────────────────────────────────────────────────────┤")
            print(f"│ 📹 File: {basename[:57]:<57} │")
            print("└──────────────────────────────────────────────────────────────────┘")
            print()
            print("❌ FFmpeg error details:")
            print(stderr)
            sys.exit(1)
    
    # Cleanup
    for temp_file in ["/tmp/videos.list", "/tmp/ffmpeg_output.txt", "/tmp/progress.txt"]:
        try:
            os.remove(temp_file)
        except OSError:
            pass
    
    # Final summary
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🎉 ALL CONVERSIONS COMPLETE!")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    print("📊 Final files:")
    
    for file in Path(download_dir).glob("*.mkv"):
        size = format_size(file.stat().st_size)
        print(f"  • {file.name} ({size})")
    print()


if __name__ == "__main__":
    main()
