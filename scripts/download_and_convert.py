import os
import sys
import subprocess
import requests
import time
import zipfile
import tempfile
import shutil
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


def is_zip_file(filepath):
    """Check if file is a ZIP archive."""
    return zipfile.is_zipfile(filepath)


def extract_zip(zip_path, extract_to):
    """Extract ZIP file contents."""
    print(f"\nExtracting ZIP: {zip_path}")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
        file_list = zip_ref.namelist()
        print(f"Extracted {len(file_list)} files")
        return file_list


def find_video_files(directory):
    """Find all video files in a directory."""
    video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp'}
    video_files = []
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in video_extensions:
                video_files.append(os.path.join(root, file))
    
    return video_files


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
    
    print(f"Converting: {os.path.basename(input_file)} -> {os.path.basename(output_file)}")
    
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


def create_zip(zip_path, source_dir, base_name):
    """Create a ZIP file from directory contents."""
    print(f"\nCreating ZIP: {zip_path}")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, source_dir)
                zipf.write(file_path, arcname)
                print(f"  Added: {arcname}")
    
    print(f"ZIP created: {format_size(os.path.getsize(zip_path))}")


def format_size(size_bytes):
    """Convert bytes to human-readable size."""
    if size_bytes == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def process_videos_in_zip(temp_dir, quality, output_base_name):
    """Process videos found in extracted ZIP."""
    video_files = find_video_files(temp_dir)
    
    if not video_files:
        print("No video files found in the ZIP archive!")
        return False
    
    print(f"\nFound {len(video_files)} video file(s) in ZIP")
    
    # If only one video and quality is original, just rename it
    if quality == 'original' and len(video_files) == 1:
        # Single video, return it as is
        return video_files[0]
    
    # Get quality params
    params = get_quality_params(quality)
    if not params and quality != 'original':
        print(f"Error: Quality config not found for {quality}")
        return False
    
    # Create converted directory
    converted_dir = os.path.join(temp_dir, 'converted')
    os.makedirs(converted_dir, exist_ok=True)
    
    converted_files = []
    
    for idx, video_file in enumerate(video_files):
        # Get relative path to preserve structure
        rel_path = os.path.relpath(video_file, temp_dir)
        rel_dir = os.path.dirname(rel_path)
        
        # Create subdirectory structure in converted dir
        if rel_dir != '.':
            target_dir = os.path.join(converted_dir, rel_dir)
            os.makedirs(target_dir, exist_ok=True)
        else:
            target_dir = converted_dir
        
        # Get base filename without extension
        base_filename = os.path.splitext(os.path.basename(video_file))[0]
        
        if quality == 'original':
            # Keep original file
            ext = os.path.splitext(video_file)[1]
            output_file = os.path.join(target_dir, f"{base_filename}_original{ext}")
            shutil.copy2(video_file, output_file)
            converted_files.append(output_file)
            info = get_video_info(video_file)
            print(f"\nOriginal kept: {os.path.basename(output_file)}")
            print(f"  Size: {format_size(os.path.getsize(output_file))} | Duration: {int(info['duration']//60)}m{int(info['duration']%60)}s | FPS: {info['fps']:.2f}")
        else:
            # Convert video
            container = params.get('container', 'mkv')
            output_file = os.path.join(target_dir, f"{base_filename}.{container}")
            
            # Get source info
            info = get_video_info(video_file)
            print(f"\n[{idx+1}/{len(video_files)}] Processing: {os.path.basename(video_file)}")
            print(f"  Source: {format_size(os.path.getsize(video_file))} | Duration: {int(info['duration']//60)}m{int(info['duration']%60)}s | FPS: {info['fps']:.2f}")
            print(f"  Settings: {params['description']} | CRF: {params['crf']} | Preset: {params['preset']} | Max FPS: {params['max_fps']}")
            
            if info["fps"] > params["max_fps"]:
                print(f"  Capping FPS: {info['fps']:.2f} -> {params['max_fps']}")
            else:
                print(f"  Keeping original FPS: {info['fps']:.2f}")
            
            exit_code = convert_video(video_file, output_file, params, quality)
            
            if exit_code != 0:
                print(f"Error converting {os.path.basename(video_file)}")
                return False
            
            new_info = get_video_info(output_file)
            print(f"  Converted: {os.path.basename(output_file)}")
            print(f"  Size: {format_size(os.path.getsize(output_file))} | Duration: {int(new_info['duration']//60)}m{int(new_info['duration']%60)}s | FPS: {new_info['fps']:.2f}")
            converted_files.append(output_file)
    
    return converted_dir


def main():
    video_url = os.environ.get('VIDEO_URL')
    output_filename = os.environ.get('OUTPUT_FILENAME', 'video')
    quality = os.environ.get('QUALITY', 'original')
    
    if not video_url:
        print("Error: VIDEO_URL environment variable not set")
        sys.exit(1)
    
    print("=" * 60)
    print("VIDEO DOWNLOAD AND CONVERTER (with ZIP support)")
    print("=" * 60)
    print(f"Base name: {output_filename}")
    print(f"Quality: {quality}\n")
    
    # Create a temporary directory for processing
    with tempfile.TemporaryDirectory() as temp_dir:
        # Download file
        temp_file = os.path.join(temp_dir, 'downloaded_file')
        
        if not download_video(video_url, temp_file):
            print("Download failed!")
            sys.exit(1)
        
        # Check if downloaded file is ZIP
        if is_zip_file(temp_file):
            print(f"\nDetected ZIP archive: {os.path.basename(temp_file)}")
            
            # Extract ZIP
            extract_dir = os.path.join(temp_dir, 'extracted')
            os.makedirs(extract_dir, exist_ok=True)
            extract_zip(temp_file, extract_dir)
            
            # Process videos in ZIP
            result = process_videos_in_zip(extract_dir, quality, output_filename)
            
            if not result:
                print("Failed to process videos in ZIP!")
                sys.exit(1)
            
            # Create final ZIP with converted videos
            if quality == 'original':
                final_zip_name = f"{output_filename}_original.zip"
            else:
                final_zip_name = f"{output_filename}_{quality}.zip"
            
            # Use the converted directory or the extracted directory
            source_dir = result if isinstance(result, str) else extract_dir
            final_zip_path = os.path.join(os.getcwd(), final_zip_name)
            
            create_zip(final_zip_path, source_dir, output_filename)
            
            print(f"\nCompleted! Output ZIP: {final_zip_name}")
            print(f"Size: {format_size(os.path.getsize(final_zip_path))}")
            
            output_file = final_zip_name
            
        else:
            # Handle single file (original behavior)
            print(f"\nSingle file detected (not ZIP)")
            
            # Determine file extension
            original_ext = os.path.splitext(temp_file)[1]
            if not original_ext:
                original_ext = '.mp4'  # Default
            
            if quality == 'original':
                final_filename = f"{output_filename}_original{original_ext}"
                shutil.copy2(temp_file, final_filename)
                info = get_video_info(final_filename)
                print(f"\nOriginal saved as: {final_filename}")
                print(f"Size: {format_size(os.path.getsize(final_filename))} | Duration: {int(info['duration']//60)}m{int(info['duration']%60)}s | FPS: {info['fps']:.2f}")
                output_file = final_filename
                
            else:
                params = get_quality_params(quality)
                if not params:
                    print(f"Error: Quality config not found for {quality}")
                    sys.exit(1)
                
                container = params.get('container', 'mkv')
                final_filename = f"{output_filename}_{quality}.{container}"
                
                info = get_video_info(temp_file)
                print(f"\nSource: {format_size(os.path.getsize(temp_file))} | Duration: {int(info['duration']//60)}m{int(info['duration']%60)}s | FPS: {info['fps']:.2f}")
                print(f"Settings: {params['description']} | CRF: {params['crf']} | Preset: {params['preset']} | Max FPS: {params['max_fps']} | Audio: {params['audio_bitrate']}")
                
                if info["fps"] > params["max_fps"]:
                    print(f"Capping FPS: {info['fps']:.2f} -> {params['max_fps']}")
                else:
                    print(f"Keeping original FPS: {info['fps']:.2f}")
                
                print(f"Output container: {container.upper()}")
                print(f"Converting with {params['codec']}...\n")
                
                exit_code = convert_video(temp_file, final_filename, params, quality)
                
                if exit_code != 0:
                    print(f"\nError converting to {quality}")
                    sys.exit(1)
                
                new_info = get_video_info(final_filename)
                print(f"\nConverted: {final_filename}")
                print(f"Size: {format_size(os.path.getsize(final_filename))} | Duration: {int(new_info['duration']//60)}m{int(new_info['duration']%60)}s | FPS: {new_info['fps']:.2f}")
                output_file = final_filename
    
    print("\n" + "=" * 60)
    print(f"Completed! Output: {output_file}")
    print("=" * 60)
    
    # Create a marker file with the output filename for the workflow to find
    with open('output_filename.txt', 'w') as f:
        f.write(output_file)


if __name__ == "__main__":
    main()
