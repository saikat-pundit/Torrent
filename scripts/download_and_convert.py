import os
import sys
import subprocess
import requests

def download_video(url, output_filename):
    print(f"Downloading video from: {url}")
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
    print(f"Converting to {resolution}p...")
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
        '-y'
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✓ Converted to {resolution}p: {output_file}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Error converting to {resolution}p: {e.stderr}")
        return False

def main():
    video_url = os.environ.get('VIDEO_URL')
    output_filename = os.environ.get('OUTPUT_FILENAME', 'video')
    quality = os.environ.get('QUALITY', 'original')
    
    if not video_url:
        print("Error: VIDEO_URL environment variable not set")
        sys.exit(1)
    
    if not output_filename.endswith('.mp4'):
        output_filename += '.mp4'
    
    print("=" * 60)
    print("VIDEO DOWNLOAD AND CONVERTER")
    print("=" * 60)
    
    temp_filename = f"temp_{output_filename}"
    if not download_video(video_url, temp_filename):
        sys.exit(1)
    
    if quality == 'original':
        final_filename = output_filename.replace('.mp4', '_original.mp4')
        os.rename(temp_filename, final_filename)
        print(f"✓ Original saved as: {final_filename}")
    elif quality == '480p':
        final_filename = output_filename.replace('.mp4', '_480p.mp4')
        if not convert_video(temp_filename, final_filename, '480'):
            sys.exit(1)
    elif quality == '720p':
        final_filename = output_filename.replace('.mp4', '_720p.mp4')
        if not convert_video(temp_filename, final_filename, '720'):
            sys.exit(1)
    else:
        print(f"✗ Unknown quality: {quality}")
        sys.exit(1)
    
    # Cleanup temp file
    if os.path.exists(temp_filename) and temp_filename != final_filename:
        os.remove(temp_filename)
    
    print("=" * 60)
    print(f"✓ Completed! Output: {final_filename}")
    print("=" * 60)

if __name__ == "__main__":
    main()
