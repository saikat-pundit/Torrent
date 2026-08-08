import os
import sys
import subprocess
import requests
import time
from pathlib import Path


def download_video(url, output_filename):
    """Download video with progress logging every 10 seconds."""
    print(f"Downloading from: {url}")
    
    try:
        response = requests.get(url, stream=True, allow_redirects=True, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Failed to download: {e}")
        return False
    
    total_size = int(response.headers.get('content-length', 0))
    downloaded = 0
    start_time = time.time()
    last_print = start_time
    
    with open(output_filename, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                
                current_time = time.time()
                if current_time - last_print >= 10:
                    elapsed = current_time - start_time
                    speed = downloaded / elapsed if elapsed > 0 else 0
                    
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"  {format_size(downloaded)} / {format_size(total_size)} ({percent:.1f}%) - {format_size(speed)}/s")
                    else:
                        print(f"  {format_size(downloaded)} downloaded - {format_size(speed)}/s")
                    
                    last_print = current_time
    
    elapsed = time.time() - start_time
    speed = downloaded / elapsed if elapsed > 0 else 0
    print(f"Download complete: {format_size(downloaded)} in {elapsed:.1f}s ({format_size(speed)}/s)")
    return True


def get_quality_params(quality):
    """Return encoding parameters with FPS caps for each quality."""
    configs = {       
        "480p-av1": {
            "scale": "scale=854:-2",
            "crf": "37",
            "preset": "7",
            "pix_fmt": "yuv420p10le",
            "max_fps": 25,
            "codec": "libsvtav1",
            "description": "AV1 480p",
            "container": "mkv",
            "audio_bitrate": "96k"
        },
        "720p-av1": {
            "scale": "scale=1280:-2",
            "crf": "34",
            "preset": "8",
            "pix_fmt": "yuv420p",
            "max_fps": 27,
            "codec": "libsvtav1",
            "description": "AV1 720p",
            "container": "mkv",
            "audio_bitrate": "128k"
        }
    }
    return configs.get(quality)


def get_video_info(filepath):
    """Extract video metadata using ffprobe."""
    try:
        # Get duration
        r = subprocess.run(
            f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{filepath}"',
            shell=True, capture_output=True, text=True, timeout=10
        )
        duration = float(r.stdout.strip().split('.')[0]) if r.stdout.strip() else 0

        # Get FPS
        r = subprocess.run(
            f'ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=noprint_wrappers=1:nokey=1 "{filepath}"',
            shell=True, capture_output=True, text=True, timeout=10
        )
        fps_str = r.stdout.strip()
        if '/' in fps_str:
            num, den = map(int, fps_str.split('/'))
            fps = num / den if den != 0 else 0
        else:
            fps = float(fps_str) if fps_str else 0

        return {"duration": duration, "fps": fps}
    except:
        return {"duration": 0, "fps": 0}


def convert_video(input_file, output_file, params, quality):
    """Convert video with real-time stderr output."""
    info = get_video_info(input_file)
    
    # Build video filter with FPS cap
    vf_parts = []
    
    if info["fps"] > 0 and info["fps"] > params["max_fps"]:
        vf_parts.append(f"fps={params['max_fps']}")
    
    vf_parts.append(params["scale"])
    vf_filter = ",".join(vf_parts)
    
    # Build ffmpeg command
    cmd = (
        f'ffmpeg -nostdin -i "{input_file}" '
        f'-map 0:v -map 0:a '
        f'-c:v {params["codec"]} -vf "{vf_filter}" '
        f'-crf {params["crf"]} -preset {params["preset"]} '
        f'-pix_fmt {params["pix_fmt"]} '
        f'-svtav1-params "tune=0:enable-overlays=1" '
        f'-c:a aac -b:a {params["audio_bitrate"]} '
        f'-stats_period 10 -stats '
        f'"{output_file}" -y'
    )
    
    # Run with stderr piped for real-time display
    process = subprocess.Popen(
        cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, bufsize=1
    )
    
    # Print stderr in real-time
    for line in process.stderr:
        print(line, end='', flush=True)
    
    process.wait()
    return process.returncode


def format_size(size_bytes):
    """Convert bytes to human-readable size."""
    if size_bytes == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def main():
    video_url = os.environ.get('VIDEO_URL')
    output_filename = os.environ.get('OUTPUT_FILENAME', 'video')
    quality = os.environ.get('QUALITY', 'original')
    
    if not video_url:
        print("Error: VIDEO_URL environment variable not set")
        sys.exit(1)
    
    # Use the user-provided filename as the base name (preserve dots)
    base_name = output_filename
    
    # Create temporary filename for download
    temp_filename = f"temp_{base_name}.mp4"
    
    print("=" * 60)
    print("VIDEO DOWNLOAD AND CONVERTER")
    print("=" * 60)
    print(f"Base name: {base_name}")
    print(f"Quality: {quality}\n")
    
    # Download
    if not download_video(video_url, temp_filename):
        print("Download failed!")
        sys.exit(1)
    
    # Handle original quality
    if quality == 'original':
        # Get original extension from temp file
        original_ext = os.path.splitext(temp_filename)[1]
        final_filename = f"{base_name}_original{original_ext}"
        os.rename(temp_filename, final_filename)
        info = get_video_info(final_filename)
        print(f"\nOriginal saved as: {final_filename}")
        print(f"Size: {format_size(os.path.getsize(final_filename))} | Duration: {int(info['duration']//60)}m{int(info['duration']%60)}s | FPS: {info['fps']:.2f}")
        output_file = final_filename
    
    # Handle conversion
    elif quality in ['480p-av1', '720p-av1']:
        params = get_quality_params(quality)
        if not params:
            print(f"Error: Quality config not found for {quality}")
            sys.exit(1)
            
        # Get container from params
        container = params.get('container', 'mkv')
        final_filename = f"{base_name}_{quality}.{container}"
        
        info = get_video_info(temp_filename)
        print(f"\nSource: {format_size(os.path.getsize(temp_filename))} | Duration: {int(info['duration']//60)}m{int(info['duration']%60)}s | FPS: {info['fps']:.2f}")
        
        print(f"Settings: {params['description']} | CRF: {params['crf']} | Preset: {params['preset']} | Max FPS: {params['max_fps']} | Audio: {params['audio_bitrate']}")
        
        if info["fps"] > params["max_fps"]:
            print(f"Capping FPS: {info['fps']:.2f} -> {params['max_fps']}")
        else:
            print(f"Keeping original FPS: {info['fps']:.2f}")
        
        print(f"Output container: {container.upper()}")
        print(f"Converting with {params['codec']}...\n")
        
        exit_code = convert_video(temp_filename, final_filename, params, quality)
        
        if exit_code != 0:
            print(f"\nError converting to {quality}")
            sys.exit(1)
        
        new_info = get_video_info(final_filename)
        print(f"\nConverted: {final_filename}")
        print(f"Size: {format_size(os.path.getsize(final_filename))} | Duration: {int(new_info['duration']//60)}m{int(new_info['duration']%60)}s | FPS: {new_info['fps']:.2f}")
        output_file = final_filename
    
    else:
        print(f"Unknown quality: {quality}")
        sys.exit(1)
    
    # Cleanup temp file
    if os.path.exists(temp_filename) and temp_filename != output_file:
        os.remove(temp_filename)
    
    print("\n" + "=" * 60)
    print(f"Completed! Output: {output_file}")
    print("=" * 60)
    
    # Create a marker file with the output filename for the workflow to find
    with open('output_filename.txt', 'w') as f:
        f.write(output_file)

if __name__ == "__main__":
    main()
