#!/usr/bin/env bash
# One-time (per cloud run) environment setup. Safe to re-run.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIP="pip install --quiet --break-system-packages"

# Python deps (voice, audio, encode, thumbnail)
$PIP kokoro-onnx soundfile librosa pyloudnorm imageio-ffmpeg pillow numpy fonttools

# Blender: apt first (cloud Linux), else the bpy wheel from PyPI
if ! command -v blender >/dev/null && [ ! -x /Applications/Blender.app/Contents/MacOS/Blender ]; then
  if command -v apt-get >/dev/null; then
    (sudo -n true 2>/dev/null && SUDO=sudo || SUDO="")
    $SUDO apt-get update -qq && $SUDO apt-get install -y -qq blender >/dev/null || true
  fi
  command -v blender >/dev/null || $PIP bpy || echo "WARNING: no Blender and no bpy wheel"
fi

# Kokoro model files: ONLY from the kokoro-onnx GitHub release (never Hugging Face)
mkdir -p "$ROOT/models"
REL=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
[ -s "$ROOT/models/kokoro-v1.0.onnx" ] || curl -sSLf -o "$ROOT/models/kokoro-v1.0.onnx" "$REL/kokoro-v1.0.onnx"
[ -s "$ROOT/models/voices-v1.0.bin" ]  || curl -sSLf -o "$ROOT/models/voices-v1.0.bin"  "$REL/voices-v1.0.bin"
echo "setup ok"
