#!/usr/bin/env python3
import os, subprocess, sys, re, time, shutil
from pathlib import Path

def get_fps(f):
    r = subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=r_frame_rate','-of','default=noprint_wrappers=1:nokey=1',f], capture_output=True, text=True)
    s = r.stdout.strip()
    if '/' in s:
        n,d = map(int, s.split('/'))
        return n/d if d else 24
    return float(s) if s else 24

def get_channels(f):
    r = subprocess.run(['ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=channels','-of','default=noprint_wrappers=1:nokey=1',f], capture_output=True, text=True)
    return int(r.stdout.strip()) if r.stdout.strip().isdigit() else 2

def get_duration(f):
    r = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',f], capture_output=True, text=True)
    return float(r.stdout.strip()) if r.stdout.strip() else 0

def format_time(s):
    return f"{int(s//60)}m {int(s%60)}s"

def download_torrent(magnet, out_dir):
    print(f"\n{'='*50}\n📥 DOWNLOADING\n{'='*50}")
    
    # Create temp dir for download
    temp_dir = Path(out_dir) / "temp_download"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    p = subprocess.Popen([
        'aria2c', '--seed-time=0',
        '--max-connection-per-server=16',
        '--split=16',
        '--summary-interval=1',
        '--console-log-level=error',
        '--dir', str(temp_dir),
        magnet
    ], stderr=subprocess.PIPE, universal_newlines=True, bufsize=1)
    
    last_percent = 0
    for line in p.stderr:
        # Parse download progress
        if '%' in line and ('#' in line or 'DL:' in line):
            try:
                # Get percentage
                percent_match = re.search(r'\((\d+)%\)', line)
                if percent_match:
                    percent = int(percent_match.group(1))
                    if percent != last_percent:
                        last_percent = percent
                        
                        # Progress bar
                        bar = '█' * int(40*percent/100) + '░' * (40 - int(40*percent/100))
                        
                        # Get downloaded/total size
                        size_match = re.search(r'(\d+(?:\.\d+)?[KMGT]?i?B)/(\d+(?:\.\d+)?[KMGT]?i?B)', line)
                        size_str = f" {size_match.group(1)}/{size_match.group(2)}" if size_match else ""
                        
                        # Get speed
                        speed_match = re.search(r'DL:(\d+(?:\.\d+)?[KMGT]?i?B/s)', line)
                        speed_str = f" | ⚡ {speed_match.group(1)}" if speed_match else ""
                        
                        # Get ETA
                        eta_match = re.search(r'ETA:? (\d+[hms]?)', line)
                        eta_str = f" | ⏱️ {eta_match.group(1)}" if eta_match else ""
                        
                        msg = f"\r📊 [{bar}] {percent}%{size_str}{speed_str}{eta_str}"
                        print(msg.ljust(80), end='', flush=True)
            except:
                pass
        
        elif 'complete' in line.lower():
            print(f"\n✅ Download complete!")
    
    p.wait()
    print()
    
    # Find and move video files
    download_path = Path(out_dir)
    video_files = []
    for ext in ['*.mkv', '*.mp4', '*.avi', '*.mov', '*.ts']:
        video_files.extend(temp_dir.rglob(ext))
    
    # Move files to main directory
    for f in video_files:
        dest = download_path / f.name
        shutil.move(str(f), str(dest))
    
    # Cleanup temp dir
    try:
        shutil.rmtree(temp_dir)
    except:
        pass
    
    # Find video file
    for ext in ['*.mkv', '*.mp4', '*.avi']:
        files = list(download_path.glob(ext))
        if files:
            return files[0]
    return None

def convert_video(inp, out, quality):
    src_fps = get_fps(inp)
    target_fps = 24 if src_fps > 24 else src_fps
    fps_filter = f"fps={target_fps}," if src_fps > 24 else ""
    width = 480 if quality == '480p' else 720
    scale = f"{fps_filter}scale={width}:-2:force_original_aspect_ratio=decrease"
    crf = 28 if quality == '480p' else 26
    channels = get_channels(inp)
    duration = get_duration(inp)
    
    print(f"\n{'='*50}\n🎬 CONVERTING\n{'='*50}")
    print(f"📹 {Path(inp).name} → {Path(out).name}")
    print(f"⚙️ {quality} | CRF:{crf} | {src_fps:.1f}→{target_fps:.1f}fps | {'🔊Stereo' if channels>2 else '🔊Original'}")
    print(f"⏱️ Duration: {format_time(duration)}\n")
    
    cmd = ['ffmpeg','-nostdin','-i',inp,'-c:v','libx265','-vf',scale,'-preset','medium','-crf',str(crf),'-pix_fmt','yuv420p','-map','0:v:0']
    if channels > 2:
        cmd.extend(['-c:a','aac','-b:a','96k','-af','aformat=channel_layouts=stereo'])
    else:
        cmd.extend(['-c:a','copy'])
    cmd.extend(['-c:s','copy','-map','0:s?',out])
    
    p = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True, bufsize=1)
    frames = 0
    last_progress = 0
    
    for line in p.stderr:
        if 'frame=' in line:
            try:
                fr_match = re.search(r'frame=\s*(\d+)', line)
                if fr_match:
                    fr = int(fr_match.group(1))
                    if fr > frames:
                        frames = fr
                        progress = min(100, int(frames / duration * 24)) if duration > 0 else 0
                        
                        if progress != last_progress:
                            last_progress = progress
                            bar = '█' * int(40*progress/100) + '░' * (40 - int(40*progress/100))
                            
                            time_elapsed = frames / 24 if src_fps else 0
                            time_left = max(0, duration - time_elapsed) if duration else 0
                            
                            # Get speed
                            speed_match = re.search(r'(\d+(?:\.\d+)?x)', line)
                            speed_str = f" | ⚡ {speed_match.group(1)}" if speed_match else ""
                            
                            msg = f"\r📊 [{bar}] {progress}% | [{format_time(time_elapsed)}/{format_time(duration)}]{speed_str} | ⏱️ ETA: {format_time(time_left)}"
                            print(msg.ljust(80), end='', flush=True)
            except:
                pass
    
    p.wait()
    print()
    
    if p.returncode == 0 and os.path.getsize(out) > 0:
        in_mb = os.path.getsize(inp) / 1048576
        out_mb = os.path.getsize(out) / 1048576
        saved = (in_mb - out_mb) / in_mb * 100 if in_mb > 0 else 0
        print(f"✅ Done! 📦 {out_mb:.1f}MB (saved {saved:.1f}%)\n")
        return True
    return False

def main():
    print(f"\n{'🚀'*25}\n   VIDEO CONVERTER\n{'🚀'*25}")
    if len(sys.argv) < 3:
        print("Usage: python converter.py <magnet_link> <480p|720p>")
        sys.exit(1)
    
    os.makedirs('./download', exist_ok=True)
    
    video = download_torrent(sys.argv[1], './download')
    if not video:
        print("❌ Download failed - no video file found")
        sys.exit(1)
    
    print(f"📹 Found: {video.name}")
    
    out_path = Path('./download') / f"{video.stem}_{sys.argv[2]}.mkv"
    if convert_video(str(video), str(out_path), sys.argv[2]):
        video.unlink()
        print(f"🎉 Complete! 📁 {out_path}")
    else:
        print("❌ Conversion failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
