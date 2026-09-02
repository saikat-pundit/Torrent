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
    print(f"\nExtracting ZIP: {os.path.basename(zip_path)}")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
        file_list = zip_ref.namelist()
        print(f"Extracted {len(file_list)} files")
        return file_list


def find_video_files(directory):
    """Find all video files in a directory."""
    video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.mpeg', '.mpg'}
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
            "pix_fmt": "yuv420p",
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
        vf_parts.append(f"fps={int(params['max_fps'])}")
    
    vf_parts.append(params["scale"])
    vf_filter = ",".join(vf_parts)
    
    # Build ffmpeg command
    cmd = (
        f'ffmpeg -nostdin -i "{input_file}" '
        f'-map 0:v -map 0:a '
        f'-c:v {params["codec"]} -vf "{vf_filter}" '
        f'-crf {params["crf"]} -preset {params["preset"]} '
        f'-pix_fmt {params["pix_fmt"]} '
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


def create_zip(zip_path, source_dir):
    """Create a ZIP file from directory contents."""
    print(f"\nCreating ZIP: {os.path.basename(zip_path)}")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, source_dir)
                zipf.write(file_path, arcname)
                print(f"  Added: {arcname}")
    
    size = os.path.getsize(zip_path)
    print(f"ZIP created: {format_size(size)}")
    return zip_path


def process_zip_contents(zip_path, quality, output_base_name):
    """Process videos inside a ZIP file."""
    # Create temporary directory for extraction
    with tempfile.TemporaryDirectory() as temp_dir:
        # Extract ZIP
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        extract_zip(zip_path, extract_dir)
        
        # Find video files
        video_files = find_video_files(extract_dir)
        
        if not video_files:
            print("No video files found in the ZIP archive!")
            return None
        
        print(f"\nFound {len(video_files)} video file(s) in ZIP")
        
        # If quality is original and only one video, just rename the ZIP
        if quality == 'original':
            # Keep original files, just repack with _original suffix
            final_zip_name = f"{output_base_name}_original.zip"
            # Copy and rename the original ZIP
            shutil.copy2(zip_path, final_zip_name)
            print(f"\nOriginal ZIP preserved as: {final_zip_name}")
            return final_zip_name
        
        # Get quality params
        params = get_quality_params(quality)
        if not params:
            print(f"Error: Quality config not found for {quality}")
            return None
        
        # Create converted directory
        converted_dir = os.path.join(temp_dir, 'converted')
        os.makedirs(converted_dir, exist_ok=True)
        
        print(f"\nConverting {len(video_files)} video(s) to {params['description']}...")
        
        for idx, video_file in enumerate(video_files):
            # Get relative path to preserve structure
            rel_path = os.path.relpath(video_file, extract_dir)
            rel_dir = os.path.dirname(rel_path)
            
            # Create subdirectory structure in converted dir
            if rel_dir != '.':
                target_dir = os.path.join(converted_dir, rel_dir)
                os.makedirs(target_dir, exist_ok=True)
            else:
                target_dir = converted_dir
            
            # Get base filename without extension
            base_filename = os.path.splitext(os.path.basename(video_file))[0]
            
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
                return None
            
            new_info = get_video_info(output_file)
            print(f"  Converted: {os.path.basename(output_file)}")
            print(f"  Size: {format_size(os.path.getsize(output_file))} | Duration: {int(new_info['duration']//60)}m{int(new_info['duration']%60)}s | FPS: {new_info['fps']:.2f}")
        
        # Create final ZIP with converted videos
        final_zip_name = f"{output_base_name}_{quality}.zip"
        final_zip_path = os.path.join(os.getcwd(), final_zip_name)
        
        create_zip(final_zip_path, converted_dir)
        return final_zip_name


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
    
    print("=" * 60)
    print("VIDEO DOWNLOAD AND CONVERTER")
    print("=" * 60)
    print(f"Base name: {base_name}")
    print(f"Quality: {quality}\n")
    
    # Download file (could be video or ZIP)
    temp_filename = f"temp_{base_name}"
    
    if not download_video(video_url, temp_filename):
        print("Download failed!")
        sys.exit(1)
    
    # Check if downloaded file is a ZIP
    if is_zip_file(temp_filename):
        print(f"\nDetected ZIP archive: {temp_filename}")
        
        # Process ZIP contents
        result = process_zip_contents(temp_filename, quality, base_name)
        
        if not result:
            print("Failed to process ZIP contents!")
            sys.exit(1)
        
        output_file = result
        
        # Cleanup temp file
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
    
    else:
        # Handle single video file (original behavior)
        print(f"\nSingle file detected (not ZIP)")
        
        # Determine file extension
        original_ext = os.path.splitext(temp_filename)[1]
        if not original_ext:
            original_ext = '.mp4'  # Default
        
        # Handle original quality
        if quality == 'original':
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
