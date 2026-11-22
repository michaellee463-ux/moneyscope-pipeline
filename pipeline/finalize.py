"""Encode frames + mix into the final MP4 and check it.

Usage: python finalize.py <episode_dir>
Writes <episode_dir>/video.mp4 and build/video_qc.json; exits non-zero on failure.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

FF = imageio_ffmpeg.get_ffmpeg_exe()


def main(ep):
    ep = Path(ep)
    b = ep / "build"
    frames = sorted((b / "frames").glob("*.png"))
    qc = json.loads((b / "audio_qc.json").read_text())
    expected = int(-(-qc["duration"] * 30 // 1))
    from PIL import Image
    empty = []
    for f in frames:
        try:
            with Image.open(f) as im:
                im.load()
        except Exception:
            empty.append(f.name)
            f.unlink()  # delete so a re-run of render.py redraws only this frame
    if len(frames) < expected or empty:
        raise SystemExit(f"RENDER INCOMPLETE: {len(frames)} of {expected} frames, {len(empty)} unreadable (deleted; re-run render.py to redraw them): {empty[:10]}")
    out = ep / "video.mp4"
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y",
                    "-framerate", "30", "-start_number", "1", "-i", str(b / "frames" / "%04d.png"),
                    "-i", str(b / "mix.wav"),
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-profile:v", "high", "-r", "30",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-shortest", "-movflags", "+faststart", str(out)], check=True)
    info = subprocess.run([FF, "-hide_banner", "-i", str(out)], capture_output=True, text=True).stderr
    v = re.search(r"Video: (\w+).*?, (\d+)x(\d+).*?, ([\d.]+) fps", info)
    a = re.search(r"Audio: (\w+)", info)
    d = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
    dur = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3))
    size_mb = out.stat().st_size / 1e6
    checks = {
        "h264": v and v.group(1) == "h264",
        "1080x1920": v and (v.group(2), v.group(3)) == ("1080", "1920"),
        "30fps": v and abs(float(v.group(4)) - 30) < 0.01,
        "aac": a and a.group(1) == "aac",
        "duration_61_90": 61 <= dur <= 90,
        "under_100mb": size_mb < 100,
    }
    res = {"ok": all(checks.values()), "checks": {k: bool(x) for k, x in checks.items()},
           "duration": round(dur, 2), "size_mb": round(size_mb, 1)}
    (b / "video_qc.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    if not res["ok"]:
        raise SystemExit("VIDEO QC FAILED - do not post")


if __name__ == "__main__":
    main(sys.argv[1])
