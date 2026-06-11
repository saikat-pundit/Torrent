import os
import subprocess
import sys
import shutil
from pathlib import Path
import time

def get_video_fps(input_file):
    """Get video FPS using ffprobe"""
    cmd = [
        'ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=r_frame_rate', '-of', 'default=noprint_wrappers=1:nokey=1',
        input_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    fps_str = result.stdout.strip()
    
    if '/' in fps_str:
        num, den = map(int, fps_str.split('/'))
        fps = num / den if den != 0 else 24
    else:
        fps = float(fps_str) if fps_str else 24
    
    return fps

def get_audio_channels(input_file):
    """Get audio channel count"""
    cmd = [
        'ffprobe', '-v', 'error', '-select_streams', 'a:0',
        '-show_entries', 'stream=channels', '-of', 'default=noprint_wrappers=1:nokey=1',
        input_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    channels = result.stdout.strip()
    return int(channels) if channels and channels.isdigit() else 2

def get_video_duration(input_file):
    """Get video duration in seconds"""
    cmd = [
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', input_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    duration = result.stdout.strip()
    return float(duration) if duration else 0

def convert_video(input_file, output_file, quality):
    """Convert video with optimal settings"""
    
    # Get source FPS
    source_fps = get_video_fps(input_file)
    
    # Determine target FPS (only reduce if above 24)
    if source_fps > 24:
        target_fps = 24
        fps_filter = f"fps={target_fps}"
    else:
        target_fps = source_fps
        fps_filter = ""
    
    # Set scaling based on quality
    if quality == "480p":
        scale_filter = "scale=480:-2:force_original_aspect_ratio=decrease"
        crf = 28
    else:
        scale_filter = "scale=720:-2:force_original_aspect_ratio=decrease"
        crf = 26
    
    # Combine filters
    if fps_filter:
        vf = f"{fps_filter},{scale_filter}"
    else:
        vf = scale_filter
    
    # Get audio channel config
    source_channels = get_audio_channels(input_file)
    if source_channels > 2:
        audio_filter = "aformat=channel_layouts=stereo"
        audio_codec = "aac"
        audio_bitrate = "96k"
    else:
        audio_filter = ""
        audio_codec = "copy"
        audio_bitrate = ""
    
    # Get duration for progress display
    duration = get_video_duration(input_file)
    
    print(f"\n{'='*50}")
    print(f"🎬 CONVERTING VIDEO")
    print(f"{'='*50}")
    print(f"📹 Input: {Path(input_file).name}")
    print(f"📺 Output: {Path(output_file).name}")
    print(f"⚙️  Quality: {quality} | CRF: {crf}")
    print(f"🎞️  Source FPS: {source_fps:.2f} → Target FPS: {target_fps:.2f}")
    print(f"🔊 Audio: {'Stereo ' + audio_bitrate if audio_filter else 'Original (no change)'}")
    print(f"⏱️  Duration: {duration//60:.0f}m {duration%60:.0f}s")
    print(f"{'='*50}\n")
    
    # Build ffmpeg command with progress
    cmd = [
        'ffmpeg', '-nostdin', '-i', input_file,
        '-c:v', 'libx265',
        '-vf', vf,
        '-preset', 'medium',
        '-crf', str(crf),
        '-pix_fmt', 'yuv420p',
        '-x265-params', 'aq-mode=3',
        '-map', '0:v:0'
    ]
    
    # Add audio
    if audio_filter:
        cmd.extend(['-c:a', audio_codec, '-b:a', audio_bitrate, '-af', audio_filter])
    else:
        cmd.extend(['-c:a', 'copy'])
    
    # Add subtitles
    cmd.extend(['-c:s', 'copy', '-map', '0:s?', output_file])
    
    # Run with progress display
    process = subprocess.Popen(
        cmd, 
        stderr=subprocess.PIPE, 
        stdout=subprocess.DEVNULL,
        universal_newlines=True
    )
    
    # Monitor progress
    last_progress = 0
    for line in process.stderr:
        if 'frame=' in line:
            # Extract frame number
            frame_part = line.split('frame=')[1].split(' ')[0].strip()
            if frame_part.isdigit():
                frames = int(frame_part)
                # Estimate progress (assuming 24 fps)
                current_time = frames / 24
                if duration > 0:
                    percent = min(100, int((current_time / duration) * 100))
                    if percent != last_progress:
                        last_progress = percent
                        bar_length = 40
                        filled = int(bar_length * percent / 100)
                        bar = '█' * filled + '░' * (bar_length - filled)
                        print(f"\r📊 Progress: [{bar}] {percent}% ({int(current_time//60)}m {int(current_time%60)}s / {int(duration//60)}m {int(duration%60)}s)     ", end='', flush=True)
    
    process.wait()
    print()  # New line after progress
    
    # Verify conversion
    if process.returncode == 0 and os.path.getsize(output_file) > 0:
        input_size = os.path.getsize(input_file) / (1024 * 1024)
        output_size = os.path.getsize(output_file) / (1024 * 1024)
        saved = ((input_size - output_size) / input_size) * 100
        print(f"\n✅ Successfully converted!")
        print(f"   📦 Original size: {input_size:.1f} MB")
        print(f"   💾 Converted size: {output_size:.1f} MB")
        print(f"   🎯 Saved: {saved:.1f}%\n")
        return True
    else:
        print(f"\n❌ Conversion failed!\n")
        return False

def download_torrent(magnet_link, output_dir):
    """Download torrent with visual progress"""
    print(f"\n{'='*50}")
    print(f"📥 DOWNLOADING TORRENT")
    print(f"{'='*50}")
    print(f"🔗 Magnet link received")
    print(f"📁 Download directory: {output_dir}\n")
    
    cmd = [
        'aria2c', '--seed-time=0',
        '--max-connection-per-server=16',
        '--split=16',
        '--console-log-level=error',
        '--summary-interval=1',
        '--dir', output_dir,
        magnet_link
    ]
    
    process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, universal_newlines=True, bufsize=1)
    
    last_percent = 0
    for line in process.stderr:
        # Look for download progress pattern like [#257e37 45MiB/5.8GiB(1%)]
        if '(#' in line or '#' in line:
            # Try to extract percentage
            if '%' in line:
                # Find percentage value
                percent_start = line.find('(')
                percent_end = line.find('%')
                if percent_start != -1 and percent_end != -1:
                    percent_str = line[percent_start+1:percent_end]
                    # Extract numeric part
                    import re
                    percent_match = re.search(r'(\d+)', percent_str)
                    if percent_match:
                        percent = int(percent_match.group(1))
                        if percent != last_percent and percent <= 100:
                            last_percent = percent
                            bar_length = 40
                            filled = int(bar_length * percent / 100)
                            bar = '█' * filled + '░' * (bar_length - filled)
                            
                            # Try to extract downloaded and total
                            download_match = re.search(r'(\d+\.?\d*)([KMGT]?i?B)', line)
                            total_match = re.search(r'/(\d+\.?\d*)([KMGT]?i?B)', line)
                            
                            if download_match and total_match:
                                downloaded = download_match.group(0)
                                total = total_match.group(0)
                                print(f"\r📊 Download: [{bar}] {percent}% ({downloaded} / {total})     ", end='', flush=True)
                            else:
                                print(f"\r📊 Download: [{bar}] {percent}%     ", end='', flush=True)
        
        # Look for ETA
        elif 'ETA' in line and '%' in line:
            eta_match = re.search(r'ETA:? (\d+[hms]?)', line)
            if eta_match:
                eta = eta_match.group(1)
                print(f" ⏱️ ETA: {eta}", end='', flush=True)
        
        # Check for download complete
        elif 'Download complete' in line:
            print(f"\n✅ Download completed!")
    
    process.wait()
    
    # Find downloaded video files
    download_path = Path(output_dir)
    video_files = []
    for ext in ['*.mkv', '*.mp4', '*.avi', '*.mov', '*.ts']:
        video_files.extend(download_path.rglob(ext))
    
    # Flatten subdirectories
    for file in video_files:
        if file.parent != download_path:
            shutil.move(str(file), str(download_path / file.name))
    
    # Remove empty subdirectories
    for subdir in download_path.iterdir():
        if subdir.is_dir():
            try:
                subdir.rmdir()
            except:
                pass
    
    video_files = []
    for ext in ['*.mkv', '*.mp4', '*.avi', '*.mov', '*.ts']:
        video_files.extend(download_path.glob(ext))
    
    if video_files:
        return video_files[0]
    else:
        return None

def main():
    print(f"\n{'🚀'*25}")
    print(f"   VIDEO CONVERSION TOOL")
    print(f"{'🚀'*25}\n")
    
    if len(sys.argv) < 3:
        print("❌ Usage: python converter.py <magnet_link> <quality>")
        print("   Quality: 480p or 720p")
        sys.exit(1)
    
    magnet_link = sys.argv[1]
    quality = sys.argv[2]
    
    download_dir = "./download"
    os.makedirs(download_dir, exist_ok=True)
    
    # Download torrent
    video_file = download_torrent(magnet_link, download_dir)
    
    if not video_file:
        print("❌ Download failed! No video files found.")
        sys.exit(1)
    
    print(f"📹 Found video: {video_file.name}\n")
    
    # Convert video
    output_name = f"{video_file.stem}_{quality}.mkv"
    output_path = Path(download_dir) / output_name
    
    if convert_video(str(video_file), str(output_path), quality):
        # Remove original
        video_file.unlink()
        print(f"🎉 CONVERSION COMPLETE!")
        print(f"📁 Output: {output_path}\n")
    else:
        print("❌ Conversion failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
