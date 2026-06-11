#!/usr/bin/env python3
import os
import subprocess
import sys
import shutil
from pathlib import Path

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

def get_video_bit_depth(input_file):
    """Get video bit depth using ffprobe"""
    cmd = [
        'ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=bits_per_raw_sample', '-of', 'default=noprint_wrappers=1:nokey=1',
        input_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    bit_depth = result.stdout.strip()
    return int(bit_depth) if bit_depth and bit_depth.isdigit() else 8

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
        scale_filter = "scale=854:-2:force_original_aspect_ratio=decrease"
        crf = 28
    else:
        scale_filter = "scale=1280:-2:force_original_aspect_ratio=decrease"
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
    
    # Build ffmpeg command
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
    
    print(f"Converting: {input_file}")
    print(f"  Source FPS: {source_fps:.2f} -> Target FPS: {target_fps:.2f}")
    print(f"  Audio: {'Stereo ' + audio_bitrate if audio_filter else 'Original'}")

    result = subprocess.run(cmd)
    return result.returncode == 0 and os.path.getsize(output_file) > 0

def split_download(magnet_link, output_dir, num_parts=5):
    """Download torrent in multiple parts for faster speed"""
    print(f"Downloading torrent in {num_parts} parts...")
    
    # Create temp directory for parts
    temp_dir = Path(output_dir) / "temp_parts"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate different peer IDs for each part
    part_files = []
    for i in range(num_parts):
        part_file = temp_dir / f"part_{i}"
        cmd = [
            'aria2c', '--seed-time=0',
            '--max-connection-per-server=16',
            '--split=16',
            '--dir', str(temp_dir),
            '--out', f"part_{i}",
            '--peer-id-prefix', f"-AR{str(i).zfill(2)}-",
            magnet_link
        ]
        subprocess.Popen(cmd)
        part_files.append(part_file)
    
    # Wait for all downloads
    for part_file in part_files:
        while not any(part_file.parent.glob("*.mkv")) and not any(part_file.parent.glob("*.mp4")):
            import time
            time.sleep(5)
    
    # Merge parts
    print("Merging downloaded parts...")
    video_files = list(temp_dir.glob("*.mkv")) + list(temp_dir.glob("*.mp4"))
    
    if len(video_files) > 1:
        # Create concat file
        concat_file = temp_dir / "concat.txt"
        with open(concat_file, 'w') as f:
            for vf in sorted(video_files):
                f.write(f"file '{vf.absolute()}'\n")
        
        # Merge
        output_file = Path(output_dir) / "merged_video.mkv"
        subprocess.run([
            'ffmpeg', '-f', 'concat', '-safe', '0',
            '-i', str(concat_file), '-c', 'copy', str(output_file)
        ])
        
        # Cleanup
        shutil.rmtree(temp_dir)
        return output_file
    elif video_files:
        # Single file, just move it
        output_file = Path(output_dir) / video_files[0].name
        shutil.move(str(video_files[0]), str(output_file))
        shutil.rmtree(temp_dir)
        return output_file
    
    return None

def main():
    if len(sys.argv) < 3:
        print("Usage: python converter.py <magnet_link> <quality>")
        sys.exit(1)
    
    magnet_link = sys.argv[1]
    quality = sys.argv[2]
    
    download_dir = "./download"
    os.makedirs(download_dir, exist_ok=True)
    
    # Download with splitting
    video_file = split_download(magnet_link, download_dir)
    
    if not video_file:
        print("Download failed!")
        sys.exit(1)
    
    # Convert video
    output_name = f"converted_{video_file.stem}_480p.mkv" if quality == "480p" else f"converted_{video_file.stem}_720p.mkv"
    output_path = Path(download_dir) / output_name
    
    if convert_video(str(video_file), str(output_path), quality):
        print(f"✅ Successfully converted: {output_path}")
        # Remove original
        video_file.unlink()
    else:
        print("❌ Conversion failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
