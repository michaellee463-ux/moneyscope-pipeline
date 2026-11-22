"""Music generation, narration processing, final mix and audio QC.

Usage: python audio.py <episode_dir>
Reads  build/narration_raw.wav, build/timings.json
Writes build/music.wav, build/narration.wav, build/mix.wav, build/audio_qc.json
Exits non-zero if any QC check fails (do not post).
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
import imageio_ffmpeg

SR = 48000
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
TARGET_LUFS = -16.0
PEAK_LIMIT_DB = -1.5        # limiter ceiling; spec requires <= -1 dBFS
MUSIC_BELOW_VOICE_DB = 17.0  # music sits well under the narration
TAIL_S = 1.6                 # music outro after last word


def ff(*args):
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


# ---------------------------------------------------------------- music
def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def env_adsr(n, a, r):
    e = np.ones(n, dtype=np.float32)
    na, nr = min(n, int(a * SR)), min(n, int(r * SR))
    if na:
        e[:na] = np.linspace(0, 1, na)
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def make_music(duration, seed):
    """Original calm-but-driving bed: pad chords, sub bass, soft pluck
    arpeggio, light hats and a soft kick. Deterministic per seed."""
    rng = np.random.default_rng(seed)
    bpm = 92
    beat = 60 / bpm
    bar = 4 * beat
    n = int(duration * SR)
    out = np.zeros((n, 2), dtype=np.float32)
    t_all = np.arange(n) / SR
    # progressions (MIDI roots + minor/major triads), chosen per seed
    progs = [
        [(57, "m"), (53, "M"), (48, "M"), (55, "M")],   # Am F C G
        [(50, "m"), (58, "M"), (53, "M"), (48, "M")],   # Dm Bb F C
        [(52, "m"), (48, "M"), (55, "M"), (50, "M")],   # Em C G D
    ]
    prog = progs[seed % len(progs)]
    nbars = int(np.ceil(duration / bar))
    for b in range(nbars):
        root, q = prog[b % 4]
        third = 3 if q == "m" else 4
        notes = [root, root + third, root + 7, root + 12]
        s0 = int(b * bar * SR)
        s1 = min(n, int((b + 1) * bar * SR))
        if s0 >= n:
            break
        seg = np.arange(s1 - s0) / SR
        e = env_adsr(s1 - s0, 0.4, 0.5)
        pad = np.zeros(s1 - s0, dtype=np.float32)
        for k, m in enumerate(notes):
            f = midi(m)
            for det in (-0.08, 0.08):
                ff_ = f * 2 ** (det / 12)
                pad += (np.sin(2 * np.pi * ff_ * seg) + 0.25 * np.sin(4 * np.pi * ff_ * seg)).astype(np.float32)
        pad *= e * 0.045
        out[s0:s1, 0] += pad
        out[s0:s1, 1] += pad
        # sub bass, pulsing on beats
        fb = midi(root - 24)
        for bt in range(4):
            a = s0 + int(bt * beat * SR)
            z = min(n, a + int(beat * 0.9 * SR))
            if a >= n:
                break
            tt = np.arange(z - a) / SR
            bass = np.sin(2 * np.pi * fb * tt) * np.exp(-tt * 3.0) * 0.16
            out[a:z, 0] += bass
            out[a:z, 1] += bass
        # pluck arpeggio on eighths
        arp = [notes[0] + 12, notes[1] + 12, notes[2] + 12, notes[3] + 12,
               notes[2] + 12, notes[1] + 12, notes[2] + 12, notes[3] + 12]
        for j, m in enumerate(arp):
            a = s0 + int(j * beat / 2 * SR)
            z = min(n, a + int(0.35 * SR))
            if a >= n:
                break
            tt = np.arange(z - a) / SR
            f = midi(m)
            pl = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(6 * np.pi * f * tt)) * np.exp(-tt * 9) * 0.035
            pan = 0.35 if j % 2 else -0.35
            out[a:z, 0] += pl * (1 - pan)
            out[a:z, 1] += pl * (1 + pan)
        # kick on 1 and 3, hats on off-beats
        for bt in (0, 2):
            a = s0 + int(bt * beat * SR)
            z = min(n, a + int(0.25 * SR))
            if a >= n:
                break
            tt = np.arange(z - a) / SR
            kick = np.sin(2 * np.pi * (50 + 70 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 14) * 0.22
            out[a:z] += kick[:, None]
        for j in range(8):
            if j % 2 == 0:
                continue
            a = s0 + int(j * beat / 2 * SR)
            z = min(n, a + int(0.05 * SR))
            if a >= n:
                break
            tt = np.arange(z - a) / SR
            hat = rng.standard_normal(z - a).astype(np.float32)
            hat = np.diff(hat, prepend=0) * np.exp(-tt * 80) * 0.02
            out[a:z] += hat[:, None]
    # intro fade + outro fade
    fi, fo = int(0.3 * SR), int(1.4 * SR)
    out[:fi] *= np.linspace(0, 1, fi)[:, None]
    out[-fo:] *= np.linspace(1, 0, fo)[:, None]
    return out


# ---------------------------------------------------------------- helpers
def lufs(x):
    return pyln.Meter(SR).integrated_loudness(x)


def true_peak_db(path):
    p = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", str(path), "-af",
                        "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    lines = [l for l in p.stderr.splitlines() if "Peak:" in l]
    return float(lines[-1].split("Peak:")[1].split("dBFS")[0])


def main(ep):
    ep = Path(ep)
    b = ep / "build"
    tim = json.loads((b / "timings.json").read_text())
    duration = tim["duration"] + TAIL_S

    # 1) narration: resample, one compressor + one limiter on the whole track
    ff("-i", str(b / "narration_raw.wav"), "-ar", str(SR), "-ac", "1",
       "-af", "acompressor=threshold=-20dB:ratio=2.5:attack=10:release=150:makeup=1,"
              "alimiter=limit=-3dB:attack=5:release=50:level=false",
       "-c:a", "pcm_s24le", str(b / "narration.wav"))
    voice, _ = sf.read(b / "narration.wav", dtype="float32")
    voice = np.pad(voice, (0, max(0, int(duration * SR) - len(voice))))[: int(duration * SR)]

    # 2) music
    seed = sum(map(ord, ep.name))
    music = make_music(duration, seed)
    v_l = lufs(np.stack([voice, voice], 1))
    m_l = lufs(music)
    music *= 10 ** ((v_l - MUSIC_BELOW_VOICE_DB - m_l) / 20)
    sf.write(b / "music.wav", music, SR, subtype="PCM_24")

    # 3) mix, gain to target loudness, limiter, re-measure
    mix = music + voice[:, None]
    mix *= 10 ** ((TARGET_LUFS - lufs(mix)) / 20)
    sf.write(b / "mix_pre.wav", mix, SR, subtype="FLOAT")
    ff("-i", str(b / "mix_pre.wav"), "-af",
       f"alimiter=limit={PEAK_LIMIT_DB}dB:attack=5:release=60:level=false",
       "-c:a", "pcm_s24le", str(b / "mix.wav"))
    final, _ = sf.read(b / "mix.wav", dtype="float32")

    # ------------------------------------------------------------ QC
    qc = {"checks": {}, "sentences": []}
    meter = pyln.Meter(SR, block_size=0.4)
    sent_l = []
    for s in tim["sentences"]:
        a, z = int(s["start"] * SR), int(s["end"] * SR)
        seg = voice[a:z]
        if len(seg) < int(0.45 * SR):
            seg = np.pad(seg, (0, int(0.45 * SR) - len(seg)))
        L = meter.integrated_loudness(seg)
        sent_l.append(L)
        qc["sentences"].append({"i": s["i"], "kind": s["kind"], "lufs": round(L, 2)})
    q_fail = []
    for i, s in enumerate(tim["sentences"]):
        if s["kind"] != "question":
            continue
        nb = [sent_l[j] for j in (i - 1, i + 1) if 0 <= j < len(sent_l)]
        diff = sent_l[i] - max(nb)
        if diff > 1.0:
            q_fail.append(f"sentence {i} is {diff:.2f} dB louder than its neighbours")
    qc["checks"]["question_loudness"] = {"ok": not q_fail, "detail": q_fail}

    spread = max(sent_l) - min(sent_l)
    qc["checks"]["sentence_level_spread_db"] = {"ok": spread <= 3.0, "value": round(spread, 2)}

    clipped = int(np.sum(np.abs(final) >= 0.999))
    qc["checks"]["clipping"] = {"ok": clipped == 0, "clipped_samples": clipped}

    sp = 20 * np.log10(np.max(np.abs(final)) + 1e-12)
    tp = true_peak_db(b / "mix.wav")
    qc["checks"]["peak"] = {"ok": sp <= -1.0 and tp <= -1.0, "sample_peak_dbfs": round(sp, 2),
                            "true_peak_dbfs": round(tp, 2)}

    L = lufs(final)
    qc["checks"]["integrated_lufs"] = {"ok": abs(L - TARGET_LUFS) <= 1.0, "value": round(L, 2)}

    # clicks: look for sharp jumps in the narration around every pause edge
    d = np.abs(np.diff(voice))
    edges = []
    for s in tim["sentences"]:
        edges += [s["start"], s["end"]]
        for c in s["commas"]:
            edges.append(s["start"] + c["at_s"])
    clicks = []
    for e in edges:
        a, z = max(0, int((e - 0.02) * SR)), min(len(d), int((e + 0.02) * SR))
        if z > a:
            # a click = a jump much larger than the local signal level
            local = np.abs(voice[a:z]).max() + 1e-6
            m = d[a:z].max()
            if m > 0.25 and m > 0.9 * local:
                clicks.append(round(e, 3))
    qc["checks"]["clicks_at_pauses"] = {"ok": not clicks, "at_s": clicks}

    dur = len(final) / SR
    qc["checks"]["duration_61_90"] = {"ok": 61.0 <= dur <= 90.0, "value": round(dur, 2)}
    qc["ok"] = all(c["ok"] for c in qc["checks"].values())
    qc["duration"] = dur
    (b / "audio_qc.json").write_text(json.dumps(qc, indent=1, default=lambda o: o.item()))
    (b / "mix_pre.wav").unlink(missing_ok=True)
    print(json.dumps(qc["checks"], indent=1, default=lambda o: o.item()))
    if not qc["ok"]:
        raise SystemExit("AUDIO QC FAILED - do not post")


if __name__ == "__main__":
    main(sys.argv[1])
