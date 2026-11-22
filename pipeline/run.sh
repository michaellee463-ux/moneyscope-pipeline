#!/usr/bin/env bash
# Build one episode end to end:  pipeline/run.sh episodes/<slug>
# Steps stop at the first failure (set -e). Nothing here posts anything.
set -euo pipefail
EP="${1:?usage: pipeline/run.sh episodes/<slug>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PY="${PY:-python3}"

# Blender: prefer a blender binary (apt / Blender.app); fall back to `python -c import bpy`.
if [ -n "${BLENDER:-}" ]; then :;
elif command -v blender >/dev/null; then BLENDER=blender;
elif [ -x /Applications/Blender.app/Contents/MacOS/Blender ]; then BLENDER=/Applications/Blender.app/Contents/MacOS/Blender;
else BLENDER=""; fi

echo "== 1/6 verify numbers";  "$PY" "$HERE/verify.py" "$EP"
echo "== 2/6 narration";       "$PY" "$HERE/voice.py" "$EP"
echo "== 3/6 music + mix + audio QC"; "$PY" "$HERE/audio.py" "$EP"
echo "== 4/6 render";
rm -rf "$EP/build/frames"
JOBS="${RENDER_JOBS:-2}"   # parallel renderer processes sharing the frames folder
: > "$EP/build/render.log"
for j in $(seq 1 "$JOBS"); do
  if [ -n "$BLENDER" ]; then
    "$BLENDER" -b --factory-startup -P "$HERE/render.py" -- "$EP" > "$EP/build/render.$j.log" 2>&1 &
  else
    "$PY" "$HERE/render.py" "$EP" > "$EP/build/render.$j.log" 2>&1 &
  fi
  sleep 20
done
wait || true
cat "$EP"/build/render.*.log >> "$EP/build/render.log"
grep -q "RENDER DONE" "$EP/build/render.log" || { tail -30 "$EP/build/render.log"; echo "render failed"; exit 1; }
echo "== 5/6 encode + video QC"; "$PY" "$HERE/finalize.py" "$EP"
echo "== 6/6 thumbnail";        "$PY" "$HERE/thumbnail.py" "$EP"
echo "BUILD OK: $EP/video.mp4  $EP/thumbnail.jpg"
