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
    print(f"\n{'='*50}\n📥 DOWNLOADING TORRENT\n{'='*50}")
    
    p = subprocess.Popen([
        'aria2c', '--seed-time=0',
        '--max-connection-per-server=16',
        '--split=16',
        '--summary-interval=1',
        '--console-log-level=error',
        '--dir', out_dir,
        magnet
    ], stderr=subprocess.PIPE, universal_newlines=True, bufsize=1)
    
    last_update = 0
    last_percent = 0
    
    for line in p.stderr:
        now = time.time()
        
        if '%' in line and ('#' in line or 'DL:' in line):
            try:
                if now - last_update < 5:
                    continue
                last_update = now
                
                percent_match = re.search(r'\((\d+)%\)', line)
                if percent_match:
                    percent = int(percent_match.group(1))
                    if percent != last_percent:
                        last_percent = percent
                        
                        bar = '█' * int(40*percent/100) + '░' * (40 - int(40*percent/100))
                        
                        size_match = re.search(r'(\d+(?:\.\d+)?[KMGT]?i?B)/(\d+(?:\.\d+)?[KMGT]?i?B)', line)
                        size_str = f" {size_match.group(1)}/{size_match.group(2)}" if size_match else ""
                        
                        speed_match = re.search(r'DL:(\d+(?:\.\d+)?[KMGT]?i?B/s)', line)
                        speed_str = f" | ⚡ {speed_match.group(1)}" if speed_match else ""
                        
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
    
    # Find video file
    path = Path(out_dir)
    for ext in ['*.mkv', '*.mp4', '*.avi', '*.mov', '*.ts']:
        for f in path.rglob(ext):
            if f.parent != path:
                dest = path / f.name
                shutil.move(str(f), str(dest))
            return path / f.name if f.parent == path else dest
    
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
    
    print(f"\n{'='*50}\n🎬 CONVERTING VIDEO\n{'='*50}")
    print(f"📹 Input: {Path(inp).name}")
    print(f"📺 Output: {Path(out).name}")
    print(f"⚙️  Quality: {quality} | CRF: {crf}")
    print(f"🎞️  FPS: {src_fps:.1f} → {target_fps:.1f}")
    print(f"🔊 Audio: {'Stereo 96kbps' if channels > 2 else 'Original (copy)'}")
    print(f"⏱️  Duration: {format_time(duration)}\n")
    
    cmd = ['ffmpeg','-nostdin','-i',inp,'-c:v','libx265','-vf',scale,'-preset','medium','-crf',str(crf),'-pix_fmt','yuv420p']
    cmd.extend(['-map','0:v:0'])
    if channels > 2:
        cmd.extend(['-c:a','aac','-b:a','96k','-af','aformat=channel_layouts=stereo','-map','0:a:0'])
    else:
        cmd.extend(['-c:a','copy','-map','0:a:0'])
    cmd.extend(['-c:s','copy','-map','0:s','-ignore_unknown'])
    cmd.append(out)
    
    p = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True, bufsize=1)
    
    frames = 0
    last_update = 0
    last_progress = 0
    
    for line in p.stderr:
        if 'frame=' in line:
            try:
                fr_match = re.search(r'frame=\s*(\d+)', line)
                if fr_match:
                    fr = int(fr_match.group(1))
                    if fr > frames:
                        frames = fr
                        
                        now = time.time()
                        if now - last_update < 5:
                            continue
                        last_update = now
                        
                        time_elapsed = frames / src_fps if src_fps > 0 else 0
                        progress = min(100, int((time_elapsed / duration) * 100)) if duration > 0 else 0
                        
                        if progress != last_progress:
                            last_progress = progress
                            bar = '█' * int(40*progress/100) + '░' * (40 - int(40*progress/100))
                            time_left = max(0, duration - time_elapsed)
                            
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
        saved = ((in_mb - out_mb) / in_mb) * 100 if in_mb > 0 else 0
        print(f"✅ Conversion complete!")
        print(f"   📦 Original: {in_mb:.1f} MB")
        print(f"   💾 Converted: {out_mb:.1f} MB")
        print(f"   🎯 Saved: {saved:.1f}%\n")
        return True
    return False

def main():
    print(f"\n{'🚀'*25}\n   VIDEO CONVERSION TOOL\n{'🚀'*25}")
    
    if len(sys.argv) < 3:
        print("❌ Usage: python converter.py <magnet_link> <480p|720p>")
        sys.exit(1)
    
    magnet_link = sys.argv[1]
    quality = sys.argv[2]
    
    download_dir = "./download"
    os.makedirs(download_dir, exist_ok=True)
    
    video_file = download_torrent(magnet_link, download_dir)
    if not video_file:
        print("❌ Download failed - no video file found")
        sys.exit(1)
    
    output_name = f"{Path(video_file).stem}_{quality}.mkv"
    output_path = Path(download_dir) / output_name
    
    if convert_video(str(video_file), str(output_path), quality):
        os.remove(video_file)
        print(f"🎉 Complete! Output: {output_path}")
    else:
        print("❌ Conversion failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
