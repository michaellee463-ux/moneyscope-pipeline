"""Narration: Kokoro TTS (am_puck, speed 1.0), one call per WHOLE sentence.

Rules (see docs/PRODUCTION_STANDARDS.md):
- never split a sentence at commas into separate synth calls
- never pitch-shift, never peak-normalize phrases
- lengthen the model's own comma silences (~0.22 s, ~0.12 s inside numbers)
- sentence gaps 0.30-0.45 s; 0.50-0.65 s after hook / questions / reveals
- level every sentence to the same loudness, then one compressor + limiter

Usage: python voice.py <episode_dir>
Reads  <episode_dir>/spec.json
Writes <episode_dir>/build/narration_raw.wav, timings.json, phonemes.txt
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import librosa
import pyloudnorm as pyln
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
VOICE = "am_puck"
SPEED = 1.0
SR = 24000

COMMA_PAUSE = 0.22
NUMBER_COMMA_PAUSE = 0.12
SENTENCE_LEVEL_LUFS = -20.0
PAUSE_BY_KIND = {"normal": 0.38, "hook": 0.60, "question": 0.58, "reveal": 0.62, "last": 0.0}

NUMBER_WORDS = set(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty "
    "sixty seventy eighty ninety hundred thousand million billion trillion point".split()
)
YES_NO_START = re.compile(
    r"^(is|are|was|were|do|does|did|can|could|will|would|should|have|has|had|am|isn't|aren't|don't|won't)\b",
    re.I,
)
WH_START = re.compile(r"^(why|what|where|which|how|who|when)\b", re.I)


def check_text(text):
    """Enforce the voice rules on the script itself."""
    problems = []
    if re.search(r"\d", text):
        problems.append("digits in spoken text (write numbers as words)")
    if re.search(r"[$%&@#]", text):
        problems.append("symbol in spoken text (write it as words)")
    if text.strip().endswith("?"):
        if not WH_START.match(text.strip()):
            problems.append("question is not a wh-question (rewrite as statement)")
        if YES_NO_START.match(text.strip()):
            problems.append("yes/no question")
        if re.search(r",\s*right\?$|,\s*\w+\?$", text.strip()):
            problems.append("tag question")
    return problems


def comma_targets(text):
    """Target pause length for each comma, in order."""
    words = re.findall(r"[A-Za-z'-]+|,", text)
    out = []
    for i, w in enumerate(words):
        if w != ",":
            continue
        prev = words[i - 1].lower().split("-")[-1] if i > 0 else ""
        nxt = words[i + 1].lower().split("-")[0] if i + 1 < len(words) else ""
        out.append(NUMBER_COMMA_PAUSE if prev in NUMBER_WORDS and nxt in NUMBER_WORDS else COMMA_PAUSE)
    return out


def fade(x, n, kind):
    n = min(n, len(x))
    if n <= 0:
        return x
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    x = x.copy()
    if kind == "in":
        x[:n] *= ramp
    else:
        x[-n:] *= ramp[::-1]
    return x


PHONE_SKIP = set(" ,.?!;:ˈˌː-")


def comma_estimates(ph):
    """Fraction of the way through the sentence at which each comma falls,
    estimated from the share of phoneme symbols before it."""
    total = sum(1 for c in ph if c not in PHONE_SKIP)
    out, seen = [], 0
    for c in ph:
        if c == ",":
            out.append(seen / max(total, 1))
        elif c not in PHONE_SKIP:
            seen += 1
    return out


def find_gaps(y, fracs):
    """For each estimated comma position, find the model's own pause: the
    quietest stretch within +/-0.4 s of the estimate. Returns (a, b) sample
    ranges of the quiet stretch around that point."""
    hop = 120  # 5 ms
    rms = librosa.feature.rms(y=y, frame_length=480, hop_length=hop)[0]
    db = 20 * np.log10(rms + 1e-9)
    quiet = db < (db.max() - 32)
    n = len(y)
    gaps = []
    for f in fracs:
        c = int(f * n / hop)
        w = int(0.4 * SR / hop)
        lo, hi = max(1, c - w), min(len(db) - 1, c + w)
        if hi <= lo:
            continue
        # smooth so we land in a pause, not a single quiet frame
        sm = np.convolve(db, np.ones(9) / 9, mode="same")
        k = lo + int(np.argmin(sm[lo:hi]))
        a = k
        while a > 0 and quiet[a - 1]:
            a -= 1
        b = k
        while b < len(quiet) - 1 and quiet[b + 1]:
            b += 1
        gaps.append((a * hop, (b + 1) * hop))
    return gaps


def lengthen_commas(y, targets, ph):
    """Stretch the model's own pause at each clause comma to the target
    length by inserting silence at its centre, with short fades so nothing
    clicks. Never shortens a pause."""
    if not targets:
        return y, []
    longest = find_gaps(y, comma_estimates(ph))
    longest = sorted(set(longest))
    nf = int(0.006 * SR)
    pieces, last, log = [], 0, []
    for (a, b), tgt in zip(longest, targets):
        cur = (b - a) / SR
        add = int(round(max(0.0, tgt - cur) * SR))
        log.append({"at_s": round((a + b) / 2 / SR, 3), "was_s": round(cur, 3),
                    "now_s": round(max(cur, tgt), 3)})
        if add == 0:
            continue
        mid = (a + b) // 2
        seg = y[last:mid]
        if last > 0:
            seg = fade(seg, nf, "in")
        pieces += [fade(seg, nf, "out"), np.zeros(add, dtype=np.float32)]
        last = mid
    tail = y[last:]
    pieces.append(fade(tail, nf, "in") if last > 0 else tail)
    return np.concatenate(pieces), log


def trim_edges(y):
    iv = librosa.effects.split(y, top_db=40, frame_length=512, hop_length=128)
    if len(iv) == 0:
        return y
    a = max(0, iv[0][0] - int(0.03 * SR))
    b = min(len(y), iv[-1][1] + int(0.05 * SR))
    y = y[a:b]
    return fade(fade(y, int(0.008 * SR), "in"), int(0.012 * SR), "out")


def main(ep):
    ep = Path(ep)
    spec = json.loads((ep / "spec.json").read_text())
    build = ep / "build"
    build.mkdir(parents=True, exist_ok=True)

    from kokoro_onnx import Kokoro

    k = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
    meter = pyln.Meter(SR)

    errors, phon_lines, clips = [], [], []
    for i, s in enumerate(spec["sentences"]):
        text = s["say"]
        for p in check_text(text):
            errors.append(f"sentence {i}: {p}: {text!r}")
        ph = k.tokenizer.phonemize(text, "en-us")
        phon_lines.append(f"[{i}] {text}\n    {ph}")
        batches = k._split_phonemes(" ".join(ph.split()))
        if len(batches) != 1:
            errors.append(f"sentence {i}: would be split into {len(batches)} synth calls; shorten it")
    if errors:
        raise SystemExit("VOICE RULES FAILED:\n" + "\n".join(errors))
    (build / "phonemes.txt").write_text("\n".join(phon_lines) + "\n")

    for i, s in enumerate(spec["sentences"]):
        # one call per whole sentence; no extra pauses added by the library
        y, sr = k.create(s["say"], voice=VOICE, speed=SPEED, lang="en-us",
                         trim=True, sentence_pause=0.0, clause_pause=0.0)
        assert sr == SR
        y = trim_edges(y.astype(np.float32))
        ph = k.tokenizer.phonemize(s["say"], "en-us")
        y, comma_log = lengthen_commas(y, comma_targets(s["say"]), ph)
        lufs = meter.integrated_loudness(np.pad(y, (0, max(0, int(0.45 * SR) - len(y)))))
        gain_db = float(np.clip(SENTENCE_LEVEL_LUFS - lufs, -12, 12))
        y = (y * 10 ** (gain_db / 20)).astype(np.float32)
        clips.append((y, comma_log, lufs, gain_db))

    out, timings, t = [], [], 0.0
    n = len(clips)
    for i, ((y, comma_log, lufs, gain_db), s) in enumerate(zip(clips, spec["sentences"])):
        kind = s.get("kind", "normal")
        if i == n - 1:
            kind = "last"
        pause = s.get("pause_after", PAUSE_BY_KIND.get(kind, 0.38))
        start = t
        out.append(y)
        t += len(y) / SR
        timings.append({"i": i, "start": round(start, 3), "end": round(t, 3),
                        "kind": s.get("kind", "normal"), "pause_after": pause,
                        "raw_lufs": round(lufs, 2), "gain_db": round(gain_db, 2),
                        "commas": comma_log})
        out.append(np.zeros(int(round(pause * SR)), dtype=np.float32))
        t += pause

    audio = np.concatenate(out)
    sf.write(build / "narration_raw.wav", audio, SR, subtype="PCM_24")
    (build / "timings.json").write_text(json.dumps({"sr": SR, "duration": round(t, 3),
                                                    "sentences": timings}, indent=1))
    print(f"narration {t:.2f}s, {n} sentences")


if __name__ == "__main__":
    main(sys.argv[1])
