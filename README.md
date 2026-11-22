# MONEYSCOPE pipeline

Daily personal-finance Shorts / TikToks: "money math you can see".
A scheduled Claude task runs once a day, writes one episode spec, builds the video with the scripts here, commits it, and schedules it for 4:00 PM ET.

**Read [`docs/PRODUCTION_STANDARDS.md`](docs/PRODUCTION_STANDARDS.md) first. Every run follows it.**

## Layout
| Path | What |
|---|---|
| `pipeline/setup.sh` | Installs Python deps, Blender (apt) or `bpy`, Kokoro model (GitHub release only) |
| `pipeline/run.sh episodes/<slug>` | Builds one episode: verify → voice → audio → render → encode → thumbnail |
| `pipeline/verify.py` | Accuracy gate: every number must be sourced, computed in code, or explained |
| `pipeline/moneymath.py` | Money-math helpers (payoff, compounding, …). Add new ones here |
| `pipeline/voice.py` | Kokoro am_puck narration, one call per sentence, comma pauses, levelling |
| `pipeline/audio.py` | Generated music, compressor + limiter, −16 LUFS mix, audio QC |
| `pipeline/render.py` | Headless Blender (Cycles) 1080×1920 graphics + burned-in captions |
| `pipeline/finalize.py` | H.264/AAC encode + video QC |
| `pipeline/thumbnail.py` | 1280×720 thumbnail |
| `config/publish.json` | The only accounts the task may post to (+ forbidden Explorer Man IDs) |
| `episodes/<date>-<slug>/` | `spec.json` (script, scenes, facts, checks, post text), `video.mp4`, `thumbnail.jpg` |
| `posted.md` | Every posted video: date, topic, numbers, sources, post IDs. Never repeat a topic |
| `runs/` | Failure notes from daily runs |

`build/` folders and `models/` are not committed.

## Episode spec (short version)
`spec.json` has `sentences` (`say` = spoken words, numbers as words; `caption` = on-screen text; `kind` = hook/question/reveal), `scenes` (start at a sentence index), `facts` (value + source + URL), `checks` (math expressions re-run by `verify.py`), `allowed_numbers` (constants with a reason), `thumbnail`, and `metadata` (title, description, tags, TikTok caption). Copy the newest episode as a template.

## Build locally
```bash
bash pipeline/setup.sh
bash pipeline/run.sh episodes/2026-11-24-real-cost-black-friday
```
On a Mac with Blender.app, run.sh uses it automatically (GPU render ≈ 15–20 min). In the cloud it uses `blender` from apt or the `bpy` wheel (CPU render, slower).
