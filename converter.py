import os, subprocess, sys, re, time
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

def format_size(b):
    for u in ['B','KB','MB','GB']:
        if b < 1024: return f"{b:.1f}{u}"
        b /= 1024
    return f"{b:.1f}TB"

def download_torrent(magnet, out_dir):
    print(f"\n{'='*50}\n📥 DOWNLOADING\n{'='*50}")
    p = subprocess.Popen(['aria2c','--seed-time=0','--max-connection-per-server=16','--split=16','--summary-interval=1','--dir',out_dir,magnet], stderr=subprocess.PIPE, universal_newlines=True, bufsize=1)
    for line in p.stderr:
        if '%' in line and '(' in line:
            try:
                percent = int(re.search(r'\((\d+)%', line).group(1))
                bar = '█' * int(40*percent/100) + '░' * (40 - int(40*percent/100))
                speed = re.search(r'DL:(\d+(?:\.\d+)?[KMGT]?i?B/s)', line)
                eta = re.search(r'ETA:? (\d+[hms]?)', line)
                size = re.search(r'(\d+(?:\.\d+)?[KMGT]?i?B)/(\d+(?:\.\d+)?[KMGT]?i?B)', line)
                msg = f"\r📊 [{bar}] {percent}%"
                if size: msg += f" | {size.group(1)}/{size.group(2)}"
                if speed: msg += f" | ⚡ {speed.group(1)}"
                if eta: msg += f" | ⏱️ {eta.group(1)}"
                print(msg.ljust(80), end='', flush=True)
            except: pass
        elif 'complete' in line.lower():
            print(f"\n✅ Download complete!")
    p.wait()
    print()
    path = Path(out_dir)
    for f in path.rglob('*'):
        if f.suffix in ['.mkv','.mp4','.avi','.mov','.ts']:
            if f.parent != path: shutil.move(str(f), str(path/f.name))
    return next((f for ext in ['.mkv','.mp4','.avi'] for f in path.glob(f'*{ext}')), None)

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
    for line in p.stderr:
        if 'frame=' in line:
            try:
                fr = int(re.search(r'frame=\s*(\d+)', line).group(1))
                if fr > frames:
                    frames = fr
                    progress = min(100, int(frames * 24 / duration)) if duration else 0
                    bar = '█' * int(40*progress/100) + '░' * (40 - int(40*progress/100))
                    speed = re.search(r'(\d+(?:\.\d+)?x)', line)
                    time_elapsed = frames / 24 if src_fps else 0
                    time_left = max(0, duration - time_elapsed) if duration else 0
                    msg = f"\r📊 [{bar}] {progress}% | [{format_time(time_elapsed)}/{format_time(duration)}]"
                    if speed: msg += f" | ⚡ {speed.group(1)}"
                    if time_left: msg += f" | ⏱️ ETA: {format_time(time_left)}"
                    print(msg.ljust(80), end='', flush=True)
            except: pass
    p.wait()
    print()
    if p.returncode == 0 and os.path.getsize(out):
        in_mb = os.path.getsize(inp)/1048576
        out_mb = os.path.getsize(out)/1048576
        print(f"✅ Done! 💾 {out_mb:.1f}MB (saved {(in_mb-out_mb)/in_mb*100:.1f}%)\n")
        return True
    return False

def main():
    print(f"\n{'🚀'*25}\n   VIDEO CONVERTER\n{'🚀'*25}")
    if len(sys.argv) < 3:
        print("Usage: python converter.py <magnet_link> <480p|720p>")
        sys.exit(1)
    os.makedirs('./download', exist_ok=True)
    video = download_torrent(sys.argv[1], './download')
    if not video: print("❌ Download failed"); sys.exit(1)
    out_path = Path('./download') / f"{video.stem}_{sys.argv[2]}.mkv"
    if convert_video(str(video), str(out_path), sys.argv[2]):
        video.unlink()
        print(f"🎉 Complete! 📁 {out_path}")
    else:
        print("❌ Conversion failed")

if __name__ == "__main__":
    main()
