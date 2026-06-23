import os
import sys
import subprocess
import requests
from urllib.parse import unquote

def download_video(url, output_filename):
    """
    Download video from Google Drive URL
    """
    print(f"Downloading video from: {url}")
    
    # Handle Google Drive direct download
    response = requests.get(url, stream=True, allow_redirects=True)
    
    if response.status_code == 200:
        with open(output_filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"✓ Video downloaded as: {output_filename}")
        return True
    else:
        print(f"✗ Failed to download. Status code: {response.status_code}")
        return False

def convert_video(input_file, output_file, resolution):
    """
    Convert video using ffmpeg
    """
    print(f"Converting to {resolution}p...")
    
    # ffmpeg command for conversion
    cmd = [
        'ffmpeg',
        '-i', input_file,
        '-vf', f'scale=-2:{resolution}',
        '-c:v', 'libx264',
        '-preset', 'medium',
        '-crf', '23',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-movflags', '+faststart',
        output_file,
        '-y'  # Overwrite output file
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✓ Converted to {resolution}p: {output_file}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Error converting to {resolution}p: {e.stderr}")
        return False

def main():
    # Get inputs from GitHub Actions or command line
    if len(sys.argv) < 2:
        print("Usage: python download_and_convert.py <video_url> [output_filename]")
        sys.exit(1)
    
    video_url = sys.argv[1]
    output_filename = sys.argv[2] if len(sys.argv) > 2 else 'downloaded_video.mp4'
    
    # Ensure output has .mp4 extension
    if not output_filename.endswith('.mp4'):
        output_filename += '.mp4'
    
    print("=" * 60)
    print("VIDEO DOWNLOAD AND CONVERTER")
    print("=" * 60)
    
    # Step 1: Download video
    if not download_video(video_url, output_filename):
        sys.exit(1)
    
    # Step 2: Convert to 480p
    output_480p = f'video_480p_{output_filename}'
    convert_video(output_filename, output_480p, '480')
    
    # Step 3: Convert to 720p
    output_720p = f'video_720p_{output_filename}'
    convert_video(output_filename, output_720p, '720')
    
    print("=" * 60)
    print("✓ All conversions completed!")
    print(f"  - Original: {output_filename}")
    print(f"  - 480p: {output_480p}")
    print(f"  - 720p: {output_720p}")
    print("=" * 60)

if __name__ == "__main__":
    main()
